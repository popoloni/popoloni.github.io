#!/usr/bin/env python3
"""Compare two independent publication rebuilds with the current delivered tree."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "source/automation"))
from atlas_cli import files, safe_extract
from atlas_validate import artifact_sha256

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def compared(root):
    return {name: info for name, info in files(root).items()
            if not name.startswith("verification/") and name != "SHA256SUMS.txt"}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    meta = load(ROOT / "source/book_publications.json")
    if sha(args.baseline) != meta["baseline_package_sha256"]:
        p.error("Published baseline archive SHA-256 does not match the reviewed input.")
    inputs = {"source/book_publications.json"}
    # Source code and editorial instructions are frozen build inputs. Generated
    # graph templates, config, manuscript metadata and exports come from baseline.
    for path in (ROOT / "source").rglob("*"):
        if path.is_file() and path.suffix in {".py", ".js", ".md", ".txt"} and "__pycache__" not in path.parts:
            inputs.add(path.relative_to(ROOT).as_posix())
    for entry in [meta["series"], *meta["books"]]:
        if entry.get("cover_image"):
            relative = Path(entry["cover_image"])
            if relative.is_absolute() or ".." in relative.parts or relative.parts[:2] != ("assets", "books"):
                p.error("Cover input must be a local assets/books/ file.")
            inputs.add(relative.as_posix())
    initial_identity = artifact_sha256(ROOT)
    input_hashes = {name: sha(ROOT / name) for name in sorted(inputs)}
    expected = compared(ROOT)
    inventories = []
    failures = []
    logs = []
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"}
    with tempfile.TemporaryDirectory(prefix="atlas132-reproduce-") as temp:
        for number in (1, 2):
            site = Path(temp) / ("rebuild-" + str(number))
            safe_extract(args.baseline, site)
            for name in sorted(inputs):
                target = site / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            done = subprocess.run([sys.executable, "-B", str(site / "source/update_publications.py")],
                                  cwd=site, env=env, text=True, capture_output=True, timeout=180)
            logs.append({"rebuild": number, "returncode": done.returncode, "output": (done.stdout + done.stderr)[-4000:]})
            if done.returncode:
                failures.append("Rebuild " + str(number) + " did not complete.")
            inventories.append(compared(site))
        mismatches = sorted(name for name in set(expected) | set(inventories[0]) | set(inventories[1])
                            if expected.get(name) != inventories[0].get(name) or expected.get(name) != inventories[1].get(name))
    if artifact_sha256(ROOT) != initial_identity or compared(ROOT) != expected:
        failures.append("Candidate files changed during reproducibility verification.")
    if {name: sha(ROOT / name) for name in sorted(inputs)} != input_hashes:
        failures.append("Frozen build inputs changed during reproducibility verification.")
    report = {
        "complete": not failures, "passed": max(0, len(expected) - len(mismatches)),
        "failed": len(mismatches) + len(failures), "outputs_tested": len(expected),
        "artifact_sha256": initial_identity,
        "method": "Two independent extractions of the exact published ZIP, amended only by frozen source code, publication registry and original image inputs; compare all delivered non-verification files by SHA-256.",
        "baseline_sha256": sha(args.baseline),
        "frozen_inputs": input_hashes,
        "mismatches": mismatches, "failures": failures, "runs": logs
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("complete", "passed", "failed", "outputs_tested", "mismatches", "failures")}, indent=2))
    raise SystemExit(1 if report["failed"] else 0)

if __name__ == "__main__":
    main()
