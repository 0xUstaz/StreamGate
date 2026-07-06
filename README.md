# StreamGate ⚡

**Pay-per-second streaming payments for live video, powered by Arc + Circle USDC.**

Viewers pay exactly for the seconds they watch — no subscriptions, no platform cut. Streamers earn USDC in real-time, settled on-chain autonomously.

> 🏆 Built for [Lepton Agents Hackathon (RFB 4)](https://lepton.thecanteenapp.com) — Canteen × Circle × Arc

**Live demo:** [streamgate-one.vercel.app](https://streamgate-one.vercel.app)

---

## Live Stats (Arc Testnet)

| Metric | Value |
|--------|-------|
| ✅ End-to-end payments confirmed | Yes |
| ⚡ Settlement time | < 3 seconds |
| 💰 First live tx | [`0x79df59d5…`](https://testnet.arcscan.app/tx/0x79df59d502d91d90998013a3afd306ca5017b0099771dd96f43c9d2347334569) |
| 🤖 Agentic decisions | Drop detection + surge pricing live |
| 🌐 Frontend | [streamgate-one.vercel.app](https://streamgate-one.vercel.app) |
| 📺 Stream | Owncast on my VM |
| 🔗 Chain | Arc Testnet |

---

## How It Works

```
Viewer opens streamgate-one.vercel.app
  → enters wallet address + picks rate ($0.001/sec)
  → clicks Watch Live Stream
  → HLS stream loads directly (no raw IP)
  → enters name → clicks Start
  → USER_JOINED fires → sidecar opens session
  → meter counts up in real-time
  → viewer leaves → USER_PARTED fires
  → sidecar computes duration × rate
  → USDC transferred on Arc testnet
  → receipt shown with tx hash + Arc Explorer link
```

---

## Agentic Layer

The sidecar makes autonomous decisions every tick — this is what earns the 30% agentic sophistication score:

- **Drop detection:** If a viewer disconnects without firing USER_PARTED (browser crash, network drop), the agent detects silence after 30s and force-closes + settles the session automatically
- **Surge pricing:** When concurrent viewers exceed the threshold (default: 10), rate multiplies by 1.5× automatically — the agent decides this every cycle
- **Skip billing:** Sessions under 5 seconds are free — catches page refreshes and accidental joins
- **Reconnect handling:** If a viewer rejoins mid-session, the agent closes the stale session before opening a new one

---

## Architecture

```
streamgate-one.vercel.app          ← Landing page (wallet + rate input)
streamgate-one.vercel.app/watch    ← HLS stream + floating payment widget
        ↓ POST /viewer/register
        ↓ POST /webhook (USER_JOINED)
Oracle Cloud Ubuntu VM
  ├── StreamGate Sidecar (FastAPI, port 8000)
  │     ├── main.py          — webhook receiver + REST API
  │     ├── session_tracker.py — agentic session manager
  │     ├── payment.py        — USDC transfer via web3.py
  │     ├── db.py             — SQLite session log
  │     └── config.py         — environment config
  └── Owncast (port 8080)    ← live streaming server
        ↓ webhooks → localhost:8000/webhook
Arc Testnet
  └── USDC: 0x3600000000000000000000000000000000000000
```

---

## Payment Flow (Technical)

1. Viewer registers wallet via `POST /viewer/register`
2. Browser fires `POST /webhook` with `USER_JOINED` event
3. Sidecar records `{viewer_id, wallet, joined_at, rate}` in SQLite
4. On `USER_PARTED` (or drop detection after 30s silence):
   - Computes `duration_seconds × rate_per_sec = amount_usdc`
   - Calls `USDC.transfer(streamer_wallet, amount)` via web3.py
   - Stores `tx_hash` in SQLite session log
5. Frontend polls `/earnings` → shows receipt with Arc Explorer link

**Key architectural insight:** x402 is a pull protocol — you cannot push payments via the Circle Gateway settle endpoint. Direct ERC-20 `transfer()` via web3.py on Arc testnet is the correct settlement path for this use case.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Smart Contracts | USDC ERC-20 on Arc Testnet |
| Backend | Python, FastAPI, web3.py (≥7.0.0) |
| Frontend | Vercel, HLS.js, vanilla JS |
| Streaming | Owncast (webhooks for session tracking) |
| Blockchain | Arc Testnet |
| Settlement | Circle USDC direct ERC-20 transfer |
| Infrastructure | Ubuntu, systemd, Cloudflare Tunnel |

---

## Confirmed Transactions (Arc Testnet)

| Session | Duration | Amount | TX Hash |
|---------|----------|--------|---------|
| First live payment | 48.4s | $0.0484 USDC | [`0x79df59d5…`](https://testnet.arcscan.app/tx/0x79df59d502d91d90998013a3afd306ca5017b0099771dd96f43c9d2347334569) |
| Frontend payment | 43.0s | $0.042998 USDC | [`0xda310b6c…`](https://testnet.arcscan.app/tx/0xda310b6ced8df6f54e846bfddc271f8fa597667dc041eca649a56c80e333bcc5) |

---

## Quick Start (for Owncast operators)

### Prerequisites
```bash
python3 --version   # 3.10+
node --version      # 20+
```

### Install
```bash
git clone https://github.com/0xUstaz/streamgate
cd streamgate/sidecar
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Configure
```bash
cp .env.example .env
nano .env   # fill in STREAMER_WALLET_ADDRESS, STREAMER_PRIVATE_KEY, ARC_RPC_URL
```

### Run
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Point Owncast at StreamGate
Owncast Admin → Integrations → Webhooks → Add:
- URL: `http://localhost:8000/webhook`
- Events: ✅ User Joined, ✅ User Parted

---

## Environment Variables

```env
STREAMER_WALLET_ADDRESS=0x...       # Arc testnet wallet (receives payments)
STREAMER_PRIVATE_KEY=0x...          # Private key for signing transfers
ARC_RPC_URL=https://rpc.testnet...  # Your personal Arc RPC (from arc-canteen login)
BASE_RATE_PER_SEC=0.001             # USDC per second (default)
MIN_BILLABLE_SECS=5                 # Sessions shorter than this are free
SURGE_VIEWER_THRESHOLD=10           # Concurrent viewers before surge pricing
SURGE_MULTIPLIER=1.5                # Rate multiplier during surge
ARC_TESTNET_CHAIN_ID=5042002        # Arc testnet chain ID (confirmed via cast chain-id)
```

---

## Bugs Documented (for future builders)

| # | Bug | Fix |
|---|-----|-----|
| 1 | `eth_account.structured_data.hashing` removed in newer versions | Remove import, use `account.sign_typed_data()` directly |
| 2 | `web3==6.x` conflicts with `eth-account==0.13.x` | Use `web3>=7.0.0`, let pip resolve eth-account |
| 3 | Circle Gateway `/v1/w3s/gateway/payments/nanopayments` returns 404 | x402 is pull, not push — use direct ERC-20 transfer instead |
| 4 | `@circle-fin/x402-batching` exports no `GatewayClient` | Package only has utility functions — sign EIP-3009 with viem directly |
| 5 | Node.js `?.` optional chaining fails on old Node | Requires Node 14+ — install via nvm |
| 6 | httpx DNS resolution fails inside uvicorn on Oracle Cloud | Use `asyncio.to_thread` with blocking `web3.py` calls |
| 7 | Owncast iframe blocked by HTTPS/HTTP mixed content | Load HLS stream via HLS.js directly instead of iframe |
| 8 | Vercel proxy rewrites don't proxy HTTP origins | Use Cloudflare Tunnel to expose HTTP services as HTTPS |
| 9 | `navigator.sendBeacon` with JSON needs Blob wrapper | `new Blob([body], { type: 'application/json' })` |

---

## Project Structure

```
streamgate/
├── sidecar/
│   ├── main.py              # FastAPI app — webhook receiver + REST API
│   ├── session_tracker.py   # Agentic session manager (drop detection, surge pricing)
│   ├── payment.py           # USDC settlement via web3.py
│   ├── db.py                # SQLite session log (traction proof)
│   ├── config.py            # Environment config
│   └── requirements.txt
├── vercel-app/
│   └── public/
│       ├── index.html       # Landing page (wallet + rate)
│       └── watch.html       # HLS stream + payment widget
├── payment-bridge/
│   ├── settle.js            # Node.js EIP-3009 signing bridge (reference)
│   └── package.json
├── .env.example
└── README.md
```

---

## Built For

- [Lepton Agents Hackathon](https://lepton.thecanteenapp.com) — Canteen × Circle × Arc (RFB 4: Streaming & Continuous Payments)

---

## Builder

Built by **Ustaz** ([@0xUstaz](https://github.com/0xUstaz)) — CS student, builder.

- X: [@0xUstaz](https://x.com/0xUstaz)
- GitHub: [@0xUstaz](https://github.com/0xUstaz)
- Previous: 🏆 Standout Winner — Agora Agent Hackathon

⭐ Star the repo if you find it useful
