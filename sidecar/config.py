"""
config.py — StreamGate configuration
Loads all settings from environment variables (.env file).
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Streamer wallet (the one that receives payments) ──────────────────────────
STREAMER_WALLET_ADDRESS = os.getenv("STREAMER_WALLET_ADDRESS", "")
STREAMER_PRIVATE_KEY    = os.getenv("STREAMER_PRIVATE_KEY", "")   # needed to sign settle calls

# ── Viewer payment settings ───────────────────────────────────────────────────
BASE_RATE_PER_SEC = float(os.getenv("BASE_RATE_PER_SEC", "0.001"))   # USDC per second
MIN_BILLABLE_SECS = int(os.getenv("MIN_BILLABLE_SECS", "5"))          # ignore sessions < 5 sec
SURGE_VIEWER_THRESHOLD = int(os.getenv("SURGE_VIEWER_THRESHOLD", "10")) # viewers before surge
SURGE_MULTIPLIER  = float(os.getenv("SURGE_MULTIPLIER", "1.5"))       # rate × this at surge

# ── Circle / Arc testnet ──────────────────────────────────────────────────────
CIRCLE_API_KEY         = os.getenv("CIRCLE_API_KEY", "")
CIRCLE_GATEWAY_URL     = os.getenv(
    "CIRCLE_GATEWAY_URL",
    "https://api.circle.com/v1/w3s"          # base; nanopayments endpoint appended in payment.py
)
ARC_TESTNET_CHAIN_ID   = int(os.getenv("ARC_TESTNET_CHAIN_ID", "1516"))  # Arc testnet chain ID
ARC_RPC_URL            = os.getenv(
    "ARC_RPC_URL",
    "https://rpc.arc-testnet.canteen.dev"     # Canteen-hosted Arc testnet RPC
)

# Gateway Wallet contract address on Arc testnet (where viewers deposit USDC)
GATEWAY_WALLET_CONTRACT = os.getenv(
    "GATEWAY_WALLET_CONTRACT",
    ""  # fill in after checking arc-nanopayments reference
)

# ── Owncast webhook security ──────────────────────────────────────────────────
OWNCAST_WEBHOOK_SECRET = os.getenv("OWNCAST_WEBHOOK_SECRET", "")  # optional but recommended

# ── App settings ──────────────────────────────────────────────────────────────
PORT      = int(os.getenv("PORT", "8000"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DB_PATH   = os.getenv("DB_PATH", "streamgate.db")

# ── Validation: warn loudly if critical values are missing ───────────────────
def validate():
    missing = []
    for name, val in [
        ("STREAMER_WALLET_ADDRESS", STREAMER_WALLET_ADDRESS),
        ("STREAMER_PRIVATE_KEY",    STREAMER_PRIVATE_KEY),
        ("CIRCLE_API_KEY",          CIRCLE_API_KEY),
    ]:
        if not val:
            missing.append(name)
    if missing:
        print(f"⚠️  WARNING: Missing required env vars: {', '.join(missing)}")
        print("   Copy .env.example to .env and fill in the values.")
    return len(missing) == 0

