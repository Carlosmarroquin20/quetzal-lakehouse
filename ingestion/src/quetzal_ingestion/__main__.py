"""Run an ingestion job by name: ``python -m quetzal_ingestion <job> [options]``."""

import sys

from quetzal_ingestion import budget_execution, contracting_processes, exchange_rates

JOBS = {
    "exchange-rates": exchange_rates.main,
    "contracting-processes": contracting_processes.main,
    "budget-execution": budget_execution.main,
}


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in JOBS:
        sys.exit(f"usage: python -m quetzal_ingestion {{{' | '.join(JOBS)}}} [options]")
    JOBS[argv[0]](argv[1:])


if __name__ == "__main__":
    main()
