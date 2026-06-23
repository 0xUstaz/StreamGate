"""
payment.py — StreamGate USDC settlement via direct ERC-20 transfer

Flow:
  1. Session ends → compute duration × rate = amount_usdc
  2. Sign raw USDC transfer() tx with streamer's private key
  3. Send to Arc testnet via web3.py
  4. Return tx hash

"""

import asyncio
import logging
import time
from typing import Tuple

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_account import Account

import config

logger = logging.getLogger("streamgate.payment")

# ── USDC contract (ERC-20 minimal ABI — only transfer needed) ─────────────────
USDC_ABI = [
    {
        "name": "transfer",
        "type": "function",
        "inputs": [
            {"name": "recipient", "type": "address"},
            {"name": "amount",    "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
    },
    {
        "name": "balanceOf",
        "type": "function",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    },
    {
        "name": "decimals",
        "type": "function",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
    },
]

USDC_ADDRESS  = Web3.to_checksum_address("0x3600000000000000000000000000000000000000")
USDC_DECIMALS = 6


def _get_web3() -> Web3:
    """Create a Web3 instance connected to Arc testnet."""
    w3 = Web3(Web3.HTTPProvider(config.ARC_RPC_URL, request_kwargs={"timeout": 30}))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3


def _usdc_to_int(amount: float) -> int:
    """Convert $0.001 → 1000 (6-decimal integer)."""
    return int(round(amount * (10 ** USDC_DECIMALS)))


async def settle_payment(
    viewer_wallet: str,
    amount_usdc: float,
) -> Tuple[str, bool]:
    """
    Transfer USDC from streamer wallet to itself as settlement proof.

    NOTE on architecture:
    In a full production system, the VIEWER's wallet would pre-deposit USDC
    into a smart contract escrow, and the streamer would claim from it.
    For the hackathon, we demonstrate the settlement mechanic by transferring
    from the streamer's own funded wallet — proving the on-chain flow works.
    The viewer wallet is logged for audit purposes.

    Returns (tx_hash, success).
    """
    if not config.STREAMER_PRIVATE_KEY:
        logger.warning("No STREAMER_PRIVATE_KEY — DRY RUN mode")
        return f"dryrun-{int(time.time())}", True

    if amount_usdc < 0.000001:
        logger.warning(f"Amount too small: ${amount_usdc} — skipping")
        return "", False

    try:
        tx_hash = await asyncio.to_thread(_send_usdc_transfer, amount_usdc, viewer_wallet)
        return tx_hash, True
    except Exception as e:
        logger.error(f"❌ Settlement failed: {e}")
        return "", False


def _send_usdc_transfer(amount_usdc: float, viewer_wallet: str) -> str:
    """
    Blocking function — runs in thread via asyncio.to_thread.
    Signs and broadcasts a USDC transfer on Arc testnet.
    """
    w3      = _get_web3()
    account = Account.from_key(config.STREAMER_PRIVATE_KEY)
    usdc    = w3.eth.contract(address=USDC_ADDRESS, abi=USDC_ABI)

    amount_int = _usdc_to_int(amount_usdc)

    # Check balance first
    balance = usdc.functions.balanceOf(account.address).call()
    if balance < amount_int:
        bal_usdc = balance / (10 ** USDC_DECIMALS)
        raise ValueError(
            f"Insufficient USDC balance: have ${bal_usdc:.6f}, need ${amount_usdc:.6f}"
        )

    # Build transaction
    nonce    = w3.eth.get_transaction_count(account.address)
    gas_price = w3.eth.gas_price

    recipient = Web3.to_checksum_address(config.STREAMER_WALLET_ADDRESS)

    tx = usdc.functions.transfer(recipient, amount_int).build_transaction({
        "chainId":  config.ARC_TESTNET_CHAIN_ID,
        "nonce":    nonce,
        "gas":      100_000,
        "gasPrice": gas_price,
        "from":     account.address,
    })

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

    if receipt.status != 1:
        raise RuntimeError(f"Transaction reverted: {tx_hash.hex()}")

    logger.info(
        f"✅ USDC transfer confirmed | "
        f"tx={tx_hash.hex()} | "
        f"${amount_usdc:.6f} | "
        f"viewer={viewer_wallet[:10]}…"
    )
    return tx_hash.hex()


async def get_gateway_balance() -> float:
    """Return streamer's current USDC balance on Arc testnet."""
    if not config.STREAMER_WALLET_ADDRESS:
        return 0.0
    try:
        balance_int = await asyncio.to_thread(_fetch_balance)
        return round(balance_int / (10 ** USDC_DECIMALS), 6)
    except Exception as e:
        logger.warning(f"Could not fetch balance: {e}")
        return 0.0


def _fetch_balance() -> int:
    w3   = _get_web3()
    usdc = w3.eth.contract(address=USDC_ADDRESS, abi=USDC_ABI)
    addr = Web3.to_checksum_address(config.STREAMER_WALLET_ADDRESS)
    return usdc.functions.balanceOf(addr).call()

