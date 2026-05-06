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
from .run_cycle import run_orca_cycle
from .persist import load_memory
from .present import print_history, print_start_banner

MODE = get_orca_env("ORCA_MODE", "MORNING")
LLM_REQUIRED_MODES = {"MORNING", "EVENING", "DAWN", "AFTERNOON", "WEEKLY", "MONTHLY"}


def _check_llm_credentials(mode):
    if mode in LLM_REQUIRED_MODES and not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            f"ANTHROPIC_API_KEY missing - mode={mode} requires LLM access. "
            "Check GitHub Secrets or local .env"
        )


def main():
    parser = argparse.ArgumentParser(description=ORCA_NAME + " — " + ORCA_FULL_NAME)
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()

    memory = load_memory()

    if args.history:
        print_history(memory)
        return

    _check_llm_credentials(MODE)
    print_start_banner(MODE)
    run_orca_cycle(mode=MODE, memory=memory)


if __name__ == "__main__":
    main()
