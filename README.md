# StreamGate 🎙️⚡

**Pay-per-second streaming payments for Owncast, powered by Arc + Circle.**

Viewers pay exactly for the seconds they watch. Streamers earn USDC in real-time,
settled on Arc via Circle Gateway nanopayments — no subscription, no platform cut.

Built for [Lepton Agents Hackathon (RFB 4)](https://lepton.thecanteenapp.com) · Canteen × Circle.

---

## How it works

```
Viewer joins stream → meter starts (e.g. $0.001/sec)
Viewer leaves       → sidecar computes duration × rate
                    → EIP-3009 authorization signed offchain
                    → Circle Gateway settles USDC to streamer on Arc
                    → Sub-500ms, zero gas
```

**Agentic layer:** The sidecar makes autonomous decisions every tick:
- Drop detection (no userParted? force-close after 30s silence)
- Surge pricing (>10 concurrent viewers → rate × 1.5×)
- Skip billing (sessions < 5s are free — catches page refreshes)
- Auto-reconnect handling (closes stale session before opening new one)

---

## Quick Start (Oracle Cloud / any Linux server)

### 1. Clone and install

```bash
git clone https://github.com/0xUstaz/streamgate
cd streamgate/sidecar
pip3 install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
nano .env   # fill in your wallet address, Circle API key, etc.
```

Get your Circle API key at: https://console.circle.com (free, testnet)

### 3. Run

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 4. Point Owncast at your sidecar

In Owncast admin → **Integrations → Webhooks → Add webhook:**
- URL: `http://YOUR_SERVER_IP:8000/webhook`
- Events: ✅ User Joined, ✅ User Parted

### 5. Open the viewer UI

Open `viewer-ui/index.html` in a browser (or host it statically).
Viewers connect their wallet, pick a rate, and start watching.

---

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /webhook` | Owncast sends events here |
| `GET /status` | Health check + live sessions |
| `GET /earnings` | Streamer dashboard: total earned, recent sessions |
| `GET /sessions/live` | Live viewer list |
| `POST /viewer/register` | Viewer links their wallet before watching |

---

## Environment Variables

See `.env.example` for full documentation.

Key vars:
- `STREAMER_WALLET_ADDRESS` — your Arc testnet wallet
- `CIRCLE_API_KEY` — from console.circle.com
- `BASE_RATE_PER_SEC` — default $0.001 USDC/sec
- `SURGE_VIEWER_THRESHOLD` — viewers before surge pricing kicks in

---

## Architecture

```
streamgate/
├── sidecar/
│   ├── main.py            # FastAPI webhook receiver + REST API
│   ├── session_tracker.py # Agentic session manager (drop detection, surge pricing)
│   ├── payment.py         # Circle Gateway / EIP-3009 settlement
│   ├── db.py              # SQLite session log (traction proof)
│   ├── config.py          # Environment config
│   └── requirements.txt
└── viewer-ui/
    └── index.html         # Viewer wallet UI (self-contained)
```

---

## Hackathon notes

- Settlement uses Arc testnet USDC (test funds only)
- The viewer UI is intentionally minimal — one HTML file, no framework
- In production, the **viewer** would sign the EIP-3009 authorization with their
  own private key (MetaMask / WalletConnect). The hackathon demo simplifies this
  by using a server-side signer.
- Jellyfin VOD support is planned next: same settlement core, different event source

---

## License

MIT

