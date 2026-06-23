/**
 * balance.js — Check streamer's Circle Gateway balance
 * Called by Python: node balance.js <wallet_address>
 * Prints JSON: { available: "0.01", total: "0.01" }
 */

const { GatewayClient } = require("@circle-fin/x402-batching");

const arcTestnet = {
  id: 5042002,
  name: "Arc Testnet",
  nativeCurrency: { name: "USDC", symbol: "USDC", decimals: 6 },
  rpcUrls: { default: { http: ["https://rpc.testnet.arc.network"] } },
};

const GATEWAY_WALLET = "0x0077777d7EBA4688BDeF3E311b846F25870A19B9";
const USDC_ADDRESS   = "0x3600000000000000000000000000000000000000";

async function main() {
  const address = process.argv[2];
  if (!address) {
    console.log(JSON.stringify({ available: "0", total: "0" }));
    process.exit(0);
  }

  try {
    const client = new GatewayClient({
      usdcAddress: USDC_ADDRESS,
      gatewayWalletAddress: GATEWAY_WALLET,
      chain: arcTestnet,
    });

    const bal = await client.getBalance(address);
    console.log(JSON.stringify({
      available: bal.available?.toString() || "0",
      total:     bal.total?.toString()     || "0",
    }));
    process.exit(0);
  } catch (e) {
    console.log(JSON.stringify({ available: "0", total: "0", error: e.message }));
    process.exit(0);  // non-fatal
  }
}

main();

