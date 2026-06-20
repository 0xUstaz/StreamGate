#!/usr/bin/env bash
# setup.sh — StreamGate one-command setup for Oracle Cloud (Ubuntu)
# Run from the repo root: bash setup.sh

set -e
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

info()    { echo -e "${CYAN}[StreamGate]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
error()   { echo -e "${RED}[✗]${NC} $1"; exit 1; }

echo ""
echo -e "${CYAN}╔═══════════════════════════════════════╗${NC}"
echo -e "${CYAN}║     StreamGate — Setup Script         ║${NC}"
echo -e "${CYAN}║  Pay-per-second streaming on Arc      ║${NC}"
echo -e "${CYAN}╚═══════════════════════════════════════╝${NC}"
echo ""

# ── 1. Python version check ───────────────────────────────────────────────────
info "Checking Python version..."
PY=$(python3 --version 2>&1 | awk '{print $2}')
PY_MAJOR=$(echo $PY | cut -d. -f1)
PY_MINOR=$(echo $PY | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || [ "$PY_MINOR" -lt 10 ]; then
  error "Python 3.10+ required, found $PY"
fi
success "Python $PY found"

# ── 2. Install system deps ────────────────────────────────────────────────────
info "Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq git curl python3-pip python3-venv 2>/dev/null
success "System packages ready"

# ── 3. Create virtualenv ──────────────────────────────────────────────────────
info "Creating Python virtual environment..."
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
success "Virtual environment active at .venv/"

# ── 4. Install Python deps ────────────────────────────────────────────────────
info "Installing Python dependencies..."
cd sidecar
pip install --upgrade pip -q
pip install -r requirements.txt -q
success "Python dependencies installed"
cd ..

# ── 5. Node.js / npm check (for Circle CLI and Arc CLI) ──────────────────────
info "Checking Node.js..."
if ! command -v node &> /dev/null; then
  warn "Node.js not found — installing via nvm..."
  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
  export NVM_DIR="$HOME/.nvm"
  source "$NVM_DIR/nvm.sh"
  nvm install --lts
fi
NODE_VER=$(node --version)
success "Node.js $NODE_VER found"

# ── 6. Install Circle CLI ─────────────────────────────────────────────────────
info "Installing Circle CLI..."
if ! command -v circle &> /dev/null; then
  npm install -g @circle-fin/circle-cli 2>/dev/null || \
  npm install -g circle-cli 2>/dev/null || \
  warn "Circle CLI install failed — install manually: npm install -g @circle-fin/circle-cli"
else
  success "Circle CLI already installed: $(circle --version 2>/dev/null || echo 'ok')"
fi

# ── 7. Install Arc / Canteen CLI ─────────────────────────────────────────────
info "Installing Arc (Canteen) CLI..."
if ! command -v arc &> /dev/null && ! command -v canteen &> /dev/null; then
  npm install -g @thecanteenapp/arc-cli 2>/dev/null || \
  npm install -g canteen-cli 2>/dev/null || \
  warn "Arc CLI install failed — check https://lepton.thecanteenapp.com for install command"
else
  success "Arc CLI already installed"
fi

# ── 8. .env setup ─────────────────────────────────────────────────────────────
info "Setting up environment config..."
if [ ! -f "sidecar/.env" ]; then
  cp sidecar/.env.example sidecar/.env
  echo ""
  warn "Created sidecar/.env from template."
  warn "You MUST fill in these values before running:"
  echo ""
  echo "  STREAMER_WALLET_ADDRESS  — your Arc testnet wallet (already funded ✓)"
  echo "  STREAMER_PRIVATE_KEY     — private key for that wallet"
  echo "  CIRCLE_API_KEY           — get from https://console.circle.com (free)"
  echo "  GATEWAY_WALLET_CONTRACT  — USDC contract on Arc testnet"
  echo ""
  echo -e "  ${CYAN}Run:${NC} nano sidecar/.env"
else
  success ".env already exists — skipping"
fi

# ── 9. Open port 8000 reminder ────────────────────────────────────────────────
echo ""
warn "ORACLE CLOUD REMINDER: Open port 8000 in your security list:"
echo "  Oracle Console → Networking → VCN → Security Lists → Ingress Rules"
echo "  Add: TCP port 8000 from 0.0.0.0/0"
echo ""
warn "Also allow it in Ubuntu firewall:"
echo "  sudo ufw allow 8000"
echo ""

# ── 10. Done ──────────────────────────────────────────────────────────────────
echo -e "${GREEN}╔═══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         Setup complete! 🚀             ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════╝${NC}"
echo ""
echo "Next steps:"
echo "  1. Fill in your .env:   nano sidecar/.env"
echo "  2. Activate venv:       source .venv/bin/activate"
echo "  3. Start the sidecar:   cd sidecar && uvicorn main:app --host 0.0.0.0 --port 8000"
echo "  4. Test it:             curl http://localhost:8000/status"
echo ""

