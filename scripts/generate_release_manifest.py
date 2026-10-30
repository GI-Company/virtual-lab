"""Generate a release-readiness snapshot from pytest JUnit XML and a built wheel.

Example:
  python scripts/generate_release_manifest.py --junit test-results.xml \\
      --wheel dist/virtual_lab-1.0.0b1-py3-none-any.whl
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import runpy
import sys
import xml.etree.ElementTree as ET


def summarize_junit(path: Path) -> dict:
    root = ET.parse(path).getroot()
    cases = root.findall(".//testcase")
    if not cases:
        raise ValueError(f"No test cases in {path}")
    result = {"tests_total": len(cases), "tests_passed": 0,
              "tests_failed": 0, "tests_errors": 0,
              "tests_skipped": 0, "tests_xfailed": 0}
    skipped_cases = []
    for case in cases:
        if case.find("failure") is not None:
            result["tests_failed"] += 1
        elif case.find("error") is not None:
            result["tests_errors"] += 1
        elif (skipped := case.find("skipped")) is not None:
            skipped_cases.append({"test": f"{case.get('classname')}.{case.get('name')}",
                                  "reason": skipped.get("message", "")})
            if skipped.get("type") == "pytest.xfail":
                result["tests_xfailed"] += 1
            else:
                result["tests_skipped"] += 1
        else:
            result["tests_passed"] += 1
    assert sum(value for key, value in result.items() if key != "tests_total") == result["tests_total"]
    result["skipped_cases"] = skipped_cases
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("release_manifest.json"))
    parser.add_argument("--suite", default="release regression suite")
    args = parser.parse_args()
    version = runpy.run_path(str(Path(__file__).resolve().parents[1] / "virtual_lab/version.py"))["__version__"]
    counts = summarize_junit(args.junit)
    if counts['tests_failed'] or counts['tests_errors']:
        parser.error('Refusing release manifest: test suite contains failures or errors')
    if counts['tests_passed'] == 0:
        parser.error('Refusing release manifest: no tests passed')
    wheel = args.wheel.resolve()
    if not wheel.is_file():
        parser.error(f"Wheel not found: {wheel}")
    import zipfile
    from email.parser import BytesParser
    from packaging.version import Version
    try:
        with zipfile.ZipFile(wheel) as archive:
            metadata = [name for name in archive.namelist() if name.endswith('.dist-info/METADATA')]
            if len(metadata) != 1:
                raise ValueError('Expected exactly one wheel METADATA record')
            wheel_version = BytesParser().parsebytes(archive.read(metadata[0]))['Version']
            if Version(wheel_version) != Version(version):
                raise ValueError('Wheel version does not match the source version')
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        parser.error(str(exc))
    manifest = {
        "version": version,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "test_suite": args.suite,
        "test_result_source": "pytest JUnit XML",
        **counts,
        "tests_not_run": [
            "live cloud API / external-service acceptance",
            "MLX/Metal hardware tests",
        ],
        "python_version": platform.python_version(),
        "platform": platform.system(),
        "architecture": platform.machine(),
        "build": {
            "status": "passed",
            "artifact": wheel.name,
            "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        },
    }
    args.output.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {args.output}: {counts}")


if __name__ == "__main__":
    main()
