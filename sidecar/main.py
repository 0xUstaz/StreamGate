"""
main.py — StreamGate FastAPI sidecar

Endpoints:
  POST /webhook          ← Owncast sends userJoined / userParted here
  GET  /status           ← Health check + live session count
  GET  /earnings         ← Streamer dashboard: total earned, recent sessions
  GET  /sessions/live    ← Live session list (for viewer UI polling)
  POST /viewer/register  ← Viewer registers their wallet address before watching

Run with:
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import asyncio
import hashlib
import hmac
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import config
import session_tracker
from db import init_db, get_stats, get_recent_sessions, count_active_sessions
from payment import get_gateway_balance

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("streamgate.main")


# ── App startup / shutdown ────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    config.validate()
    await init_db()
    # Start the background drop-detection agent
    task = asyncio.create_task(session_tracker.drop_detection_loop())
    logger.info(f"🚀 StreamGate sidecar running on port {config.PORT}")
    logger.info(f"   Streamer wallet : {config.STREAMER_WALLET_ADDRESS or 'NOT SET'}")
    logger.info(f"   Base rate       : ${config.BASE_RATE_PER_SEC}/sec")
    logger.info(f"   Surge threshold : {config.SURGE_VIEWER_THRESHOLD} viewers")
    yield
    task.cancel()


app = FastAPI(
    title="StreamGate",
    description="Pay-per-second streaming payments for Owncast, powered by Arc + Circle",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow the viewer UI (any origin for hackathon, tighten for prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Webhook security ──────────────────────────────────────────────────────────
def _verify_owncast_signature(body: bytes, signature: str) -> bool:
    """
    Owncast signs webhook payloads with HMAC-SHA256.
    If no secret is configured, we skip verification (dev mode).
    """
    if not config.OWNCAST_WEBHOOK_SECRET:
        return True  # dev mode — accept everything
    expected = hmac.new(
        config.OWNCAST_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


# ── Viewer wallet registration ────────────────────────────────────────────────
# Maps viewer_id → wallet_address (in-memory; resets on restart, fine for hackathon)
_viewer_wallets: dict[str, str] = {}


class ViewerRegister(BaseModel):
    viewer_id:     str
    wallet_address: str


@app.post("/viewer/register")
async def register_viewer(body: ViewerRegister):
    """
    Viewer calls this BEFORE they join the stream to link their wallet.
    The viewer UI (index.html) does this automatically on wallet-connect.
    """
    if not body.wallet_address.startswith("0x") or len(body.wallet_address) != 42:
        raise HTTPException(status_code=400, detail="Invalid wallet address")
    _viewer_wallets[body.viewer_id] = body.wallet_address
    logger.info(f"📝 Registered wallet for {body.viewer_id[:8]}… → {body.wallet_address[:10]}…")
    return {"status": "ok", "viewer_id": body.viewer_id}


# ── Owncast webhook receiver ──────────────────────────────────────────────────
@app.post("/webhook")
async def owncast_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Owncast POSTs all stream events here.
    We care about: userJoined, userParted.
    Everything else is acknowledged and ignored.

    Owncast webhook payload shape:
    {
      "eventData": {
        "id": "abc123",          ← viewer_id
        "timestamp": "...",
        "user": { "id": "abc123", "displayName": "..." }
      },
      "type": "USER_JOINED"      ← or "USER_PARTED"
    }
    """
    body = await request.body()

    # Verify Owncast signature
    sig = request.headers.get("X-Owncast-Signature", "")
    if not _verify_owncast_signature(body, sig):
        logger.warning("⛔ Webhook signature mismatch — rejected")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = data.get("type", "").upper()
    event_data = data.get("eventData", {})
    viewer_id  = (event_data.get("id") or event_data.get("user", {}).get("id", ""))

    logger.debug(f"Webhook: type={event_type} viewer={viewer_id[:8] if viewer_id else '?'}…")

    # ── Handle events ─────────────────────────────────────────────────────────
    if event_type == "USER_JOINED":
        if not viewer_id:
            return JSONResponse({"status": "ignored", "reason": "no viewer_id"})

        # Look up pre-registered wallet (or use empty string — DRY RUN mode)
        wallet = _viewer_wallets.get(viewer_id, "")
        rate   = await session_tracker.on_viewer_joined(viewer_id, wallet)
        return JSONResponse({
            "status": "tracking",
            "viewer_id": viewer_id,
            "rate_per_sec": rate,
        })

    elif event_type == "USER_PARTED":
        if not viewer_id:
            return JSONResponse({"status": "ignored", "reason": "no viewer_id"})

        result = await session_tracker.on_viewer_parted(viewer_id)
        if result:
            return JSONResponse({"status": "settled", **result})
        return JSONResponse({"status": "skipped"})

    else:
        # STREAM_STARTED, STREAM_STOPPED, CHAT_MESSAGE, etc. — ignore
        return JSONResponse({"status": "ignored", "type": event_type})


# ── Status / health ───────────────────────────────────────────────────────────
@app.get("/status")
async def status():
    """Health check. Shows live session count and config summary."""
    active = await count_active_sessions()
    return {
        "status":              "ok",
        "streamer_wallet":     config.STREAMER_WALLET_ADDRESS[:10] + "…"
                               if config.STREAMER_WALLET_ADDRESS else "NOT SET",
        "base_rate_per_sec":  config.BASE_RATE_PER_SEC,
        "surge_threshold":    config.SURGE_VIEWER_THRESHOLD,
        "surge_multiplier":   config.SURGE_MULTIPLIER,
        "active_sessions":    active,
        "live_sessions":      session_tracker.get_active_sessions(),
    }


# ── Streamer earnings dashboard ───────────────────────────────────────────────
@app.get("/earnings")
async def earnings():
    """
    Streamer calls this to see their totals.
    The viewer UI also polls this to show the live meter.
    """
    stats    = await get_stats()
    recent   = await get_recent_sessions(limit=10)
    balance  = await get_gateway_balance()
    active   = session_tracker.get_active_sessions()

    return {
        "total_earned_usdc":   round(stats.get("total_earned", 0), 6),
        "total_sessions":      stats.get("total_sessions", 0),
        "gateway_balance_usdc": balance,
        "active_viewers":      len(active),
        "live_sessions":       active,
        "recent_settled":      recent,
    }


# ── Live session list (viewer UI polls this) ──────────────────────────────────
@app.get("/sessions/live")
async def live_sessions():
    return {"sessions": session_tracker.get_active_sessions()}


# ── Run directly ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=config.PORT, reload=True)

