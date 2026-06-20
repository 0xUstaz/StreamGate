"""
payment.py — Circle Gateway / x402 settlement

How it works:
  The official Circle x402 SDK is TypeScript. For Python, we use:
  1. web3.py to sign the EIP-3009 authorization offchain (zero gas)
  2. Circle's REST API to submit the signed authorization for settlement
  3. Arc testnet as the settlement chain

EIP-3009 is: "I authorize Circle to move $X from viewer_wallet to streamer_wallet,
valid between now and now+5min." The signature is the payment — no blockchain tx needed.
Circle batches many of these and settles in bulk later.
"""

import logging
import time
import httpx
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_account.structured_data.hashing import hash_domain, hash_message
import json

import config

logger = logging.getLogger("streamgate.payment")

# ── ABI for EIP-3009 transferWithAuthorization ────────────────────────────────
# This is the USDC contract method we sign against
EIP3009_TYPES = {
    "EIP712Domain": [
        {"name": "name",              "type": "string"},
        {"name": "version",           "type": "string"},
        {"name": "chainId",           "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
    "TransferWithAuthorization": [
        {"name": "from",        "type": "address"},
        {"name": "to",          "type": "address"},
        {"name": "value",       "type": "uint256"},
        {"name": "validAfter",  "type": "uint256"},
        {"name": "validBefore", "type": "uint256"},
        {"name": "nonce",       "type": "bytes32"},
    ],
}

# USDC on Arc testnet has 6 decimals
USDC_DECIMALS = 6


def _usdc_to_wei(amount: float) -> int:
    """Convert $0.001 → 1000 (6-decimal integer)."""
    return int(round(amount * (10 ** USDC_DECIMALS)))


def _build_eip3009_payload(
    viewer_wallet: str,
    amount_usdc: float,
    usdc_contract: str,
    nonce: bytes,
) -> dict:
    """
    Build the EIP-712 typed data structure for TransferWithAuthorization.
    viewer_wallet pays → streamer_wallet receives.
    Valid for 5 minutes from now.
    """
    now = int(time.time())
    return {
        "types": EIP3009_TYPES,
        "primaryType": "TransferWithAuthorization",
        "domain": {
            "name":              "USD Coin",
            "version":           "2",
            "chainId":           config.ARC_TESTNET_CHAIN_ID,
            "verifyingContract": usdc_contract,
        },
        "message": {
            "from":        viewer_wallet,
            "to":          config.STREAMER_WALLET_ADDRESS,
            "value":       _usdc_to_wei(amount_usdc),
            "validAfter":  now - 60,      # allow 60s clock skew
            "validBefore": now + 300,     # expires in 5 minutes
            "nonce":       "0x" + nonce.hex(),
        },
    }


async def settle_payment(
    viewer_wallet: str,
    amount_usdc: float,
) -> tuple[str, bool]:
    """
    Sign an EIP-3009 authorization and submit to Circle Gateway for settlement.

    Returns (tx_hash, success).
    tx_hash is the Circle payment ID (not an onchain hash — settlement is batched).

    NOTE: In production the VIEWER signs, not us.
    For the hackathon demo, we sign on behalf of the viewer using a
    pre-authorized session key they provide at wallet-connect time.
    This is noted as a simplification in the README.
    """
    if not config.STREAMER_PRIVATE_KEY:
        logger.warning("No STREAMER_PRIVATE_KEY set — running in DRY RUN mode")
        fake_hash = f"dryrun-{int(time.time())}"
        return fake_hash, True

    if not viewer_wallet or not viewer_wallet.startswith("0x"):
        logger.warning(f"Invalid viewer wallet: {viewer_wallet!r} — skipping settlement")
        return "", False

    try:
        # Generate a fresh nonce for this authorization
        import os
        nonce = os.urandom(32)

        # TODO: replace with actual USDC contract address on Arc testnet
        # Find it at: https://docs.arc.network/arc/references/contract-addresses
        usdc_contract = config.GATEWAY_WALLET_CONTRACT or "0x0000000000000000000000000000000000000000"

        payload = _build_eip3009_payload(
            viewer_wallet=viewer_wallet,
            amount_usdc=amount_usdc,
            usdc_contract=usdc_contract,
            nonce=nonce,
        )

        # Sign with the streamer's key (demo simplification)
        account = Account.from_key(config.STREAMER_PRIVATE_KEY)
        signed  = account.sign_typed_data(full_message=payload)
        sig_hex = signed.signature.hex()

        # Submit to Circle Gateway nanopayments endpoint
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{config.CIRCLE_GATEWAY_URL}/gateway/payments/nanopayments",
                headers={
                    "Authorization": f"Bearer {config.CIRCLE_API_KEY}",
                    "Content-Type":  "application/json",
                },
                json={
                    "chain":     "ARC-TESTNET",
                    "from":      viewer_wallet,
                    "to":        config.STREAMER_WALLET_ADDRESS,
                    "value":     str(_usdc_to_wei(amount_usdc)),
                    "validAfter":  payload["message"]["validAfter"],
                    "validBefore": payload["message"]["validBefore"],
                    "nonce":       payload["message"]["nonce"],
                    "signature":   sig_hex,
                },
            )

        if resp.status_code in (200, 201, 202):
            data     = resp.json()
            tx_id    = data.get("id") or data.get("paymentId") or "submitted"
            logger.info(f"✅ Payment submitted | id={tx_id} | ${amount_usdc:.6f} USDC")
            return tx_id, True
        else:
            logger.error(
                f"❌ Gateway rejected payment | status={resp.status_code} | {resp.text[:200]}"
            )
            return "", False

    except Exception as e:
        logger.exception(f"Payment error: {e}")
        return "", False


async def get_gateway_balance() -> float:
    """
    Fetch the streamer's current Gateway balance from Circle API.
    Used by the dashboard endpoint.
    """
    if not config.CIRCLE_API_KEY:
        return 0.0
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{config.CIRCLE_GATEWAY_URL}/gateway/balances",
                headers={"Authorization": f"Bearer {config.CIRCLE_API_KEY}"},
                params={"address": config.STREAMER_WALLET_ADDRESS, "chain": "ARC-TESTNET"},
            )
        if resp.status_code == 200:
            data = resp.json()
            # Circle returns balance in USDC string
            bal = data.get("data", {}).get("available", "0")
            return float(bal)
    except Exception as e:
        logger.warning(f"Could not fetch balance: {e}")
    return 0.0

