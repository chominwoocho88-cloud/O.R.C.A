"""Report installed-package drift against requirements.txt.

The default mode is advisory: version drift is a warning, not a failing check.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from importlib import metadata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REQ_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*([=<>!~]{1,2})?\s*([^;\s#]+)?")


def _normalize_name(name: str) -> str:
    return name.replace("_", "-").lower()


def _parse_requirement_line(line: str) -> dict[str, Any] | None:
    clean = line.split("#", 1)[0].strip()
    if not clean or clean.startswith(("-r ", "--")):
        return None
    match = REQ_RE.match(clean)
    if not match:
        return {"raw": clean, "name": clean, "operator": None, "expected": None, "parse_warning": True}
    name, operator, expected = match.groups()
    return {
        "raw": clean,
        "name": name,
        "normalized_name": _normalize_name(name),
        "operator": operator,
        "expected": expected,
        "parse_warning": False,
    }


def _version_satisfies(installed: str, operator: str | None, expected: str | None) -> bool:
    if not operator or not expected:
        return True
    if operator == "==":
        return installed == expected
    try:
        from packaging.version import Version

        current_v = Version(installed)
        expected_v = Version(expected)
    except Exception:
        if operator == ">=":
            return installed >= expected
        if operator == "<=":
            return installed <= expected
        if operator == ">":
            return installed > expected
        if operator == "<":
            return installed < expected
        return installed == expected
    if operator == ">=":
        return current_v >= expected_v
    if operator == "<=":
        return current_v <= expected_v
    if operator == ">":
        return current_v > expected_v
    if operator == "<":
        return current_v < expected_v
    if operator in {"!=", "<>"}:
        return current_v != expected_v
    if operator == "~=":
        return current_v >= expected_v
    return True


def collect_requirements_drift(requirements_path: Path | None = None) -> dict[str, Any]:
    path = requirements_path or (ROOT / "requirements.txt")
    if not path.exists():
        return {
            "status": "warn",
            "requirements_path": str(path),
            "checked": 0,
            "drift_count": 0,
            "missing_count": 0,
            "parse_warning_count": 0,
            "items": [],
            "reason": "requirements_file_missing",
        }

    items: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_requirement_line(line)
        if not parsed:
            continue
        try:
            installed = metadata.version(parsed["name"])
        except metadata.PackageNotFoundError:
            installed = None
        status = "pass"
        reason = "ok"
        if parsed.get("parse_warning"):
            status = "warn"
            reason = "unparsed_requirement"
        elif installed is None:
            status = "warn"
            reason = "package_not_installed"
        elif not _version_satisfies(installed, parsed.get("operator"), parsed.get("expected")):
            status = "warn"
            reason = "version_drift"
        items.append(
            {
                **parsed,
                "installed": installed,
                "status": status,
                "reason": reason,
            }
        )

    drift_count = sum(1 for item in items if item["reason"] == "version_drift")
    missing_count = sum(1 for item in items if item["reason"] == "package_not_installed")
    parse_warning_count = sum(1 for item in items if item["reason"] == "unparsed_requirement")
    status = "warn" if drift_count or missing_count or parse_warning_count else "pass"
    return {
        "status": status,
        "requirements_path": str(path),
        "checked": len(items),
        "drift_count": drift_count,
        "missing_count": missing_count,
        "parse_warning_count": parse_warning_count,
        "items": items,
        "reason": "ok" if status == "pass" else "requirements_drift_detected",
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Requirements Drift",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Checked: `{report.get('checked')}`",
        f"- Drift: `{report.get('drift_count')}`",
        f"- Missing: `{report.get('missing_count')}`",
        "",
        "| Package | Requirement | Installed | Status | Reason |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in report.get("items", []):
        requirement = f"{item.get('operator') or ''}{item.get('expected') or ''}" or "unpinned"
        lines.append(
            f"| {item.get('name')} | {requirement} | {item.get('installed') or 'n/a'} | "
            f"{item.get('status')} | {item.get('reason')} |"
        )
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], *, output_json: Path | None, output_md: Path | None) -> None:
    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(render_markdown(report), encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Check requirements.txt against installed versions.")
    parser.add_argument("--requirements", default=str(ROOT / "requirements.txt"))
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on drift.")
    args = parser.parse_args(argv)

    report = collect_requirements_drift(Path(args.requirements))
    write_outputs(
        report,
        output_json=Path(args.output_json) if args.output_json else None,
        output_md=Path(args.output_md) if args.output_md else None,
    )
    print(render_markdown(report))
    if args.strict and report["status"] != "pass":
        sys.exit(1)


if __name__ == "__main__":
    main()
