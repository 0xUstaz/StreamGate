/**
 * settle.js — StreamGate payment bridge
 * Corrected using AgoraFX bug log (github.com/MusaAis/agorafx)
 *
 * Key fixes from Musa's bug docs:
 *   Bug #4: endpoint is /v1/x402/settle NOT /v1/payments/settle
 *   Bug #6: maxTimeoutSeconds minimum is 7 days (608400), not 60
 *   Bug #5: resource must be object {url, description, mimeType}
 */

const { getVerifyingContract } = require("@circle-fin/x402-batching");
const { createWalletClient, http, parseUnits, toHex } = require("viem");
const { privateKeyToAccount } = require("viem/accounts");

// ── Arc Testnet ───────────────────────────────────────────────────────────────
const arcTestnet = {
  id: 5042002,
  name: "Arc Testnet",
  nativeCurrency: { name: "USDC", symbol: "USDC", decimals: 6 },
  rpcUrls: { default: { http: ["https://rpc.testnet.arc.network"] } },
};

const USDC_ADDRESS   = "0x3600000000000000000000000000000000000000";
const GATEWAY_WALLET = "0x0077777d7EBA4688BDeF3E311b846F25870A19B9";

// Bug #4 fix: correct endpoint
const SETTLE_URL = "https://api.circle.com/v1/x402/settle";

async function settle(fromWallet, toWallet, amountUsdc, privateKey) {
  const key     = privateKey.startsWith("0x") ? privateKey : `0x${privateKey}`;
  const account = privateKeyToAccount(key);

  const value       = parseUnits(amountUsdc.toString(), 6);
  const nonce       = toHex(crypto.getRandomValues(new Uint8Array(32)));
  const now         = Math.floor(Date.now() / 1000);
  const validAfter  = BigInt(now - 60);
  // Bug #6 fix: minimum validBefore is 7 days from now
  const validBefore = BigInt(now + 608400);

  const domain = {
    name:              "USD Coin",
    version:           "2",
    chainId:           BigInt(arcTestnet.id),
    verifyingContract: USDC_ADDRESS,
  };

  const types = {
    TransferWithAuthorization: [
      { name: "from",        type: "address" },
      { name: "to",          type: "address" },
      { name: "value",       type: "uint256" },
      { name: "validAfter",  type: "uint256" },
      { name: "validBefore", type: "uint256" },
      { name: "nonce",       type: "bytes32" },
    ],
  };

  const message = {
    from:        fromWallet,
    to:          toWallet,
    value:       value,
    validAfter:  validAfter,
    validBefore: validBefore,
    nonce:       nonce,
  };

  const walletClient = createWalletClient({
    account,
    chain: arcTestnet,
    transport: http(),
  });

  const signature = await walletClient.signTypedData({
    domain,
    types,
    primaryType: "TransferWithAuthorization",
    message,
  });

  // Bug #5 fix: resource must be an object, not a string
  const payload = {
    chainId: arcTestnet.id,
    from:    fromWallet,
    payment: {
      scheme:            "exact",
      networkId:         `eip155:${arcTestnet.id}`,
      value:             value.toString(),
      resource: {
        url:         "https://streamgate.local/stream",
        description: "StreamGate pay-per-second stream payment",
        mimeType:    "application/json",
      },
      maxAmountRequired:  value.toString(),
      maxTimeoutSeconds:  608400,          // Bug #6 fix: 7 days minimum
      asset:              USDC_ADDRESS,
      payTo:              toWallet,
      extra: {
        name:             "GatewayWalletBatched",
        verifyingContract: GATEWAY_WALLET,
      },
    },
    signature: {
      type:  "eip712",
      value: signature,
    },
  };

  const res = await fetch(SETTLE_URL, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(payload),
  });

  const text = await res.text();
  let data;
  try { data = JSON.parse(text); } catch { data = { raw: text }; }

  if (res.ok || res.status === 201 || res.status === 202) {
    return {
      success: true,
      txHash:  data?.id || data?.paymentId || data?.data?.id || "submitted",
      status:  res.status,
      amount:  amountUsdc,
    };
  }

  return {
    success:  false,
    error:    data?.message || text,
    status:   res.status,
    response: data,
  };
}

// ── Main ──────────────────────────────────────────────────────────────────────
const [,, fromWallet, toWallet, amountUsdc, privateKey] = process.argv;

if (!fromWallet || !toWallet || !amountUsdc || !privateKey) {
  console.log(JSON.stringify({ success: false, error: "Usage: node settle.js <from> <to> <amount_usdc> <private_key>" }));
  process.exit(1);
}

settle(fromWallet, toWallet, parseFloat(amountUsdc), privateKey)
  .then(r  => { console.log(JSON.stringify(r)); process.exit(r.success ? 0 : 1); })
  .catch(e => { console.log(JSON.stringify({ success: false, error: e.message })); process.exit(1); });
