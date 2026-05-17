from pathlib import Path

_repo_package = Path(__file__).resolve().parents[2] / "shared"
if str(_repo_package) not in __path__:
    __path__.append(str(_repo_package))
