"""
ORCA main orchestrator.
Hunter -> Analyst -> Devil -> Reporter
"""
import os
import sys
import argparse

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from .brand import ORCA_FULL_NAME, ORCA_NAME
from .compat import get_orca_env
from .run_cycle import HealthTracker, run_orca_cycle
from .persist import (
    load_memory,
    save_memory,
    save_report,
    get_todays_analyses,
)
from .present import print_report, print_history, print_start_banner
from .postprocess import (
    sanitize_korea_claims,
    compact_probability_summary as _compact_probability_summary,
    collect_jackal_news as _collect_jackal_news,
)

MODE = get_orca_env("ORCA_MODE", "MORNING")


def main():
    parser = argparse.ArgumentParser(description=ORCA_NAME + " — " + ORCA_FULL_NAME)
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()

    memory = load_memory()

    if args.history:
        print_history(memory)
        return

    print_start_banner(MODE)
    run_orca_cycle(mode=MODE, memory=memory)


if __name__ == "__main__":
    main()
