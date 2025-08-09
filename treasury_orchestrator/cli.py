import sys
from decimal import Decimal

from .engine import DecisionEngine


def main():
    if len(sys.argv) != 2:
        print("Usage: python -m treasury_orchestrator.cli <balance_usd>")
        sys.exit(1)

    balance = Decimal(sys.argv[1])
    order = DecisionEngine().decide(balance)
    print(order.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
