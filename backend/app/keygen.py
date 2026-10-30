"""Generate a fresh Hyperliquid TESTNET master wallet for the backend.

    python -m app.keygen

Prints the address and the private key once. Put the key in backend/.env as HL_MASTER_PRIVATE_KEY,
fund the address with testnet USDC from the Hyperliquid testnet faucet, and set ARENA_MODE=testnet.
Never reuse a mainnet key here.
"""
from eth_account import Account


def main() -> None:
    acct = Account.create()
    print("address:          ", acct.address)
    print("HL_MASTER_PRIVATE_KEY=", acct.key.hex())
    print("\nFund it: https://app.hyperliquid-testnet.xyz/drip  (testnet USDC faucet)")


if __name__ == "__main__":
    main()
