"""Write shared/addresses.json: agent name -> address, derived from the seeds in .env.

Addresses are public, so the JSON is committed; the seeds stay in .env.
Run: .venv/bin/python -m scripts.print_addresses
"""
import json

from shared import config
from uagents.crypto import Identity

AGENTS = [
    "coordinator", "space_builder",
    "elder", "baby", "transformer", "claim",
    "product_finder", "cart", "payment_verifier", "insurance_filer",
    "recovery",
]


def main():
    addresses = {name: Identity.from_seed(config.seed(name), 0).address for name in AGENTS}
    path = config.ROOT / "shared" / "addresses.json"
    path.write_text(json.dumps(addresses, indent=2) + "\n")
    for name, address in addresses.items():
        print(f"{name:17} {address}")


if __name__ == "__main__":
    main()
