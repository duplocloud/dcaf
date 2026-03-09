#!/usr/bin/env python3
"""
Code health checks using radon.

Checks:
  - Maintainability Index (MI): minimum grade B
  - Cyclomatic Complexity (CC): max grade C per function
  - Source Lines of Code (SLOC): max 500 per file
  - Aggregate file complexity (agg-cc): max 160 per file

Usage:
  python scripts/check_code_health.py                        # all checks
  python scripts/check_code_health.py --check mi cc sloc     # specific checks
  python scripts/check_code_health.py --sloc-max 400         # override threshold
  python scripts/check_code_health.py --agg-cc-max 120       # override threshold
"""

import argparse
import subprocess
import sys

SCAN_PATH = "dcaf"
EXCLUDE_DIRS = {"__pycache__", "build", "dist", ".venv", "migrations", "vendor"}

# Thresholds
DEFAULT_SLOC_MAX = 500
DEFAULT_AGG_CC_MAX = 160
MI_FAIL_GRADES = {"C"}  # grade C or worse fails
CC_FAIL_GRADES = {"D", "E", "F"}  # grade D or worse per function


def run(cmd: list[str]) -> tuple[int, str]:
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def check_mi() -> bool:
    """Maintainability Index: fail if any file scores grade C or worse."""
    print("\n── Maintainability Index (MI) ──")
    _, output = run(["radon", "mi", SCAN_PATH, "-s"])
    failures = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        # radon mi output: "path/file.py - A (72.34)"
        parts = line.split(" - ")
        if len(parts) < 2:
            continue
        filepath = parts[0]
        grade = parts[1].strip()[0]
        if grade in MI_FAIL_GRADES:
            failures.append(line)

    if failures:
        print(f"FAIL: {len(failures)} file(s) below MI grade B:")
        for f in failures:
            print(f"  {f}")
        return False

    print("PASS: all files meet MI grade B or better")
    return True


def check_cc() -> bool:
    """Cyclomatic Complexity: fail if any function/method scores grade D or worse."""
    print("\n── Cyclomatic Complexity (CC) ──")
    _, output = run(["radon", "cc", SCAN_PATH, "-s", "-a"])
    failures = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Function-level lines start with a letter grade in parens, e.g.:
        # "    D (21): MyClass.my_method - 21"
        for grade in CC_FAIL_GRADES:
            if stripped.startswith(f"{grade} ("):
                failures.append(stripped)
                break

    if failures:
        print(f"FAIL: {len(failures)} function(s) exceed CC grade C:")
        for f in failures:
            print(f"  {f}")
        return False

    print("PASS: all functions within CC grade C or better")
    return True


def check_sloc(sloc_max: int) -> bool:
    """SLOC: fail if any source file exceeds the threshold."""
    print(f"\n── Source Lines of Code (SLOC ≤ {sloc_max}) ──")
    _, output = run(["radon", "raw", SCAN_PATH, "-s"])
    failures = []
    current_file = None
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # File header lines don't start with whitespace
        if not line.startswith(" ") and stripped.endswith(":"):
            current_file = stripped.rstrip(":")
        elif stripped.startswith("SLOC:") and current_file:
            sloc_val = int(stripped.split(":")[1].strip())
            if sloc_val > sloc_max:
                failures.append(f"{current_file}: {sloc_val} SLOC")

    if failures:
        print(f"FAIL: {len(failures)} file(s) exceed {sloc_max} SLOC:")
        for f in failures:
            print(f"  {f}")
        return False

    print(f"PASS: all files within {sloc_max} SLOC")
    return True


def check_agg_cc(agg_max: int) -> bool:
    """Aggregate CC: fail if sum of all function complexities in a file exceeds threshold."""
    print(f"\n── Aggregate File Complexity (agg-cc ≤ {agg_max}) ──")
    _, output = run(["radon", "cc", SCAN_PATH, "-s", "-a", "--show-closures"])
    failures = []
    current_file = None
    current_total = 0

    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            if current_file and current_total > agg_max:
                failures.append(f"{current_file}: aggregate CC = {current_total}")
            current_file = None
            current_total = 0
            continue

        # File header: no leading whitespace, ends with " ()"  or just the path
        if not line.startswith(" ") and not line.startswith("\t"):
            if current_file and current_total > agg_max:
                failures.append(f"{current_file}: aggregate CC = {current_total}")
            current_file = stripped
            current_total = 0
        elif " - " in stripped:
            # Complexity entries end with " - <number>"
            parts = stripped.rsplit(" - ", 1)
            if len(parts) == 2 and parts[1].isdigit():
                current_total += int(parts[1])

    if current_file and current_total > agg_max:
        failures.append(f"{current_file}: aggregate CC = {current_total}")

    if failures:
        print(f"FAIL: {len(failures)} file(s) exceed aggregate CC {agg_max}:")
        for f in failures:
            print(f"  {f}")
        return False

    print(f"PASS: all files within aggregate CC {agg_max}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Run code health checks with radon.")
    parser.add_argument(
        "--check",
        nargs="+",
        choices=["mi", "cc", "sloc", "agg-cc"],
        default=["mi", "cc", "sloc", "agg-cc"],
        help="Which checks to run (default: all)",
    )
    parser.add_argument("--sloc-max", type=int, default=DEFAULT_SLOC_MAX)
    parser.add_argument("--agg-cc-max", type=int, default=DEFAULT_AGG_CC_MAX)
    args = parser.parse_args()

    checks = set(args.check)
    results: list[bool] = []

    if "mi" in checks:
        results.append(check_mi())
    if "cc" in checks:
        results.append(check_cc())
    if "sloc" in checks:
        results.append(check_sloc(args.sloc_max))
    if "agg-cc" in checks:
        results.append(check_agg_cc(args.agg_cc_max))

    print()
    if all(results):
        print("✓ All code health checks passed.")
        return 0
    else:
        failed = results.count(False)
        print(f"✗ {failed} check(s) failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
