#!/usr/bin/env python3
"""Repackage an already verified release against a pinned published baseline.

This read-only consumer of atlas_cli runs never builds, changes a candidate,
marks checks successful, or deploys. The standard full ZIP is copied unchanged.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import stat
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from atlas_cli import (archive_site, check_inputs, date_value, files,
                       final_inventory_sha256, get_run, graph_at, load,
                       release_value, save, sha)
from atlas_validate import validate_site

SCHEMA = "knowledge-atlas-cumulative-release/1"
SOURCE_COLLECTIONS = {"W", "O", "P", "F"}
BOOK_FIELDS = {"new_manuscript_citation", "book_citation_status",
               "manuscript_citation_status", "manuscript_citation_basis"}
FROZEN_CONTENT_FILES = ("source/ndse2_book.json", "source/book_publications.json",
                        "source/practices_review.json")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def filename(value):
    require(isinstance(value, str) and value not in {"", ".", ".."}
            and PurePosixPath(value).name == value and "\\" not in value
            and ":" not in value, "Package metadata contains an unsafe filename")
    return value


def extract_exact(archive, target):
    """Use the standard extractor and reject entries its inventory would ignore."""
    from atlas_cli import safe_extract
    with zipfile.ZipFile(archive) as z:
        names = []
        seen = set()
        for item in z.infolist():
            name = item.filename
            path = PurePosixPath(name)
            require(bool(name) and path.as_posix() == name.rstrip("/")
                    and not path.is_absolute() and ".." not in path.parts
                    and "\\" not in name and ":" not in path.parts[0],
                    "Unsafe or noncanonical archive path: " + name)
            require(name not in seen, "Duplicate archive entry: " + name)
            require(not stat.S_ISLNK(item.external_attr >> 16) and not item.flag_bits & 1,
                    "Symbolic links or encrypted archive entries are unsupported")
            seen.add(name)
            if not item.is_dir():
                names.append(name)
    result = safe_extract(archive, target)
    require(set(names) == set(result), "Archive contains entries omitted by the site inventory")
    return result


def inventory_delta(baseline, current):
    removed = sorted(set(baseline) - set(current))
    require(not removed, "Copy-only cumulative delta cannot delete files: " + ", ".join(removed[:12]))
    changed = sorted(p for p in baseline if baseline[p] != current[p])
    added = sorted(set(current) - set(baseline))
    unchanged = sorted(p for p in baseline if baseline[p] == current[p])
    return changed, added, unchanged


def preserved_content(baseline, current, old_files, new_files):
    """Permit reviewed source edits while retaining original book/practice data."""
    old_nodes, new_nodes = baseline["nodes"], current["nodes"]
    require([n["id"] for n in new_nodes[:len(old_nodes)]] == [n["id"] for n in old_nodes],
            "Published node IDs must remain the original ordered prefix")
    require(current["edges"][:len(baseline["edges"])] == baseline["edges"],
            "Published historical keyed edges must remain the identical ordered prefix")
    protected_nodes = 0
    for old, new in zip(old_nodes, new_nodes):
        nid = old["id"]
        for field in ("kind", "collection", "actual", "printed"):
            require(old.get(field) == new.get(field), "Protected node field changed: " + nid + "." + field)
        # All non-source nodes include the original books, chapters, sections,
        # reader files, practice descriptors, occurrences and historical claims.
        if old.get("collection") not in SOURCE_COLLECTIONS:
            require(old == new, "Original book/practice/context node changed: " + nid)
            protected_nodes += 1
        def protected(attrs):
            return {k: v for k, v in attrs.items() if k in BOOK_FIELDS
                    or k.startswith(("ndse2_", "manuscript_", "book_citation_"))}
        require(protected(old.get("attributes", {})) == protected(new.get("attributes", {})),
                "Original book citation fields changed: " + nid)
    for section in (None, "graphAttributes"):
        old = baseline["meta"] if section is None else baseline["meta"].get(section, {})
        new = current["meta"] if section is None else current["meta"].get(section, {})
        def book_meta(value):
            return {k: v for k, v in value.items() if "book" in k.lower() or "practice" in k.lower()}
        require(book_meta(old) == book_meta(new), "Original book/practice graph metadata changed")
    frozen = []
    for name in FROZEN_CONTENT_FILES:
        if name in old_files:
            require(old_files[name] == new_files.get(name), "Original book/practice source bytes changed: " + name)
            frozen.append(name)
    return {"original_node_id_prefix": True, "historical_keyed_edge_prefix": True,
            "original_node_count": len(old_nodes), "original_edge_count": len(baseline["edges"]),
            "book_practice_and_context_nodes_unchanged": protected_nodes,
            "original_citation_fields_unchanged": True,
            "book_practice_metadata_unchanged": True, "frozen_content_files": frozen}


def verified_stage(run):
    root, state = get_run(run)
    require(state.get("phase") == "packaged", "Run must finish the standard build/check/package workflow first")
    check_inputs(root, state)
    for field in ("verified_artifact_sha256", "verified_graph_html_sha256", "verified_files_sha256"):
        require(bool(re.fullmatch(r"[0-9a-f]{64}", state.get(field, ""))), "Missing verified binding: " + field)
    candidate = root / "candidate"
    require(final_inventory_sha256(candidate) == state["verified_files_sha256"],
            "Candidate or verification files changed after checks; rerun the standard workflow")
    require(sha(candidate / "swe_knowledge_graph.html") == state["verified_graph_html_sha256"],
            "Graph HTML no longer matches the verified stage")
    release, date = release_value(state["release"]), date_value(state["date"])
    prefix, suffix = "Knowledge_Atlas_v" + release.replace(".", "_"), date.replace("-", "")
    stage_out = Path(state["output"]).resolve()
    manifest_path = stage_out / (prefix + "_Manifest_" + suffix + ".json")
    manifest = load(manifest_path)
    require(manifest.get("schema") == "knowledge-atlas-release/1"
            and manifest.get("release") == release and manifest.get("date") == date,
            "Standard package manifest does not identify this run")
    require(manifest.get("baseline", {}).get("sha256") == state["baseline_sha256"],
            "Standard manifest has a different working baseline")
    binding = manifest.get("verification", {})
    require(binding.get("artifact_sha256") == state["verified_artifact_sha256"]
            and binding.get("baseline_plus_delta_equals_full") is True
            and binding.get("delta_only_changed_or_added_files") is True
            and binding.get("deployed") is False,
            "Standard package manifest lacks the required verification binding")
    require(manifest.get("full") == state.get("full") and manifest.get("delta") == state.get("delta"),
            "Run and standard package manifest disagree about their archives")
    full = stage_out / filename(manifest["full"]["name"])
    require(full.is_file() and not full.is_symlink(), "Verified stage full archive is missing or is a symbolic link")
    require(sha(full) == manifest["full"]["sha256"] and full.stat().st_size == manifest["full"]["size"],
            "Stage full archive does not match the standard run manifest")
    reports = {}
    for name, relative in (("structure", "reports/structure.json"),
                           ("browser", "reports/browser/browser_checks.json"),
                           ("reproducibility", "reports/reproducibility.json")):
        report_path = root / relative
        report = load(report_path)
        require(report.get("complete") is True and report.get("failed") == 0
                and report.get("artifact_sha256") == state["verified_artifact_sha256"],
                "Missing, failed or stale standard verification report: " + name)
        reports[name] = {k: report[k] for k in ("complete", "passed", "failed", "artifact_sha256")}
        reports[name]["report_sha256"] = sha(report_path)
    fresh = validate_site(candidate, baseline_payload=load(root / "baseline_payload.json"),
                          expected_changes={**load(root / "update_audit.json"),
                                            "baseline_html": str(root / "baseline/swe_knowledge_graph.html")},
                          book=load(candidate / "source/ndse2_book.json")
                          if (candidate / "source/ndse2_book.json").is_file() else None)
    require(fresh.get("complete") is True and fresh.get("failed") == 0
            and fresh.get("artifact_sha256") == state["verified_artifact_sha256"],
            "Fresh structural verification does not match the packaged candidate")
    return root, state, manifest_path, manifest, full, reports


def cumulative_package(args):
    expected_sha = args.published_sha256.lower()
    commit = args.published_commit.lower()
    require(bool(re.fullmatch(r"[0-9a-f]{64}", expected_sha)), "--published-sha256 must be a complete SHA-256")
    require(bool(re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", commit)), "--published-commit must be a complete Git commit hash")
    published_zip = args.published_baseline.resolve()
    require(sha(published_zip) == expected_sha, "Published baseline ZIP does not match --published-sha256")
    root, state, stage_manifest_path, stage_manifest, stage_full, reports = verified_stage(args.run)
    output = args.output.resolve()
    require(not args.output.is_symlink(), "Output must not be a symbolic link")
    require(not output.is_relative_to(root) and not root.is_relative_to(output),
            "Cumulative output must be separate from the standard run directory")
    stage_out = stage_full.parent
    require(output != stage_out and not output.is_relative_to(stage_out) and not stage_out.is_relative_to(output),
            "Cumulative output must be separate from the standard package output")
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())),
            "Cumulative output directory must be new or empty")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="atlas-cumulative-check-") as work:
        work = Path(work)
        published, complete = work / "published", work / "complete"
        baseline_files = extract_exact(published_zip, published)
        full_files = extract_exact(stage_full, complete)
        require((published / "index.html").is_file() and (published / "swe_knowledge_graph.html").is_file(),
                "Published baseline must be a complete site ZIP, not a delta")
        require(full_files == files(root / "candidate"), "Stage full ZIP does not contain the exact verified candidate bytes")
        require(len(full_files) == stage_manifest["full"]["files"], "Stage full file count differs from its manifest")
        changed, added, unchanged = inventory_delta(baseline_files, full_files)
        preservation = preserved_content(graph_at(published), graph_at(complete), baseline_files, full_files)
        published_release = release_value(load(published / "source/site_config.json")["site_version"])
        release = release_value(state["release"])
        prefix = "Knowledge_Atlas_v" + release.replace(".", "_")
        suffix = state["date"].replace("-", "")
        full_name = stage_manifest["full"]["name"]
        delta_name = prefix + "_Delta_from_v" + published_release.replace(".", "_") + "_" + suffix + ".zip"
        manifest_name = prefix + "_Cumulative_Manifest_" + suffix + ".json"
        instruction_name = prefix + "_Update_Instructions_" + suffix + ".txt"
        # Prepare outside the run and commit outputs only after archive overlay proof.
        with tempfile.TemporaryDirectory(prefix=".atlas-cumulative-output-", dir=output.parent) as prepared:
            prepared = Path(prepared)
            shutil.copyfile(stage_full, prepared / full_name)
            require(sha(prepared / full_name) == stage_manifest["full"]["sha256"], "Full archive copy changed bytes")
            archive_site(prepared / delta_name, complete, changed + added, state["date"])
            delta_files = extract_exact(prepared / delta_name, work / "delta")
            require(delta_files == {p: full_files[p] for p in changed + added}, "Delta contains unexpected or missing paths")
            patched = work / "published-plus-delta"
            extract_exact(published_zip, patched)
            # Standard extraction allows a deliberate overlay of changed files.
            from atlas_cli import safe_extract
            safe_extract(prepared / delta_name, patched)
            require(files(patched) == full_files, "Published baseline plus the actual delta does not equal the verified full")
            working = work / "working-plus-delta"
            extract_exact(root / "baseline.zip", working)
            safe_extract(prepared / delta_name, working)
            working_files = files(working)
            working_mismatches = sorted(p for p in set(working_files) | set(full_files)
                                        if working_files.get(p) != full_files.get(p))
            # Detect a concurrent change instead of stamping an outdated candidate.
            require(files(root / "candidate") == full_files
                    and sha(stage_full) == stage_manifest["full"]["sha256"],
                    "Candidate or stage archive changed while cumulative packaging was running")
            counts = {"overwrite":len(changed),"add":len(added),"unchanged":len(unchanged),"remove":0}
            manifest = {
                "schema":SCHEMA,"date":state["date"],"release":release,
                "content_release":stage_manifest.get("content_release",release),"deployed":False,
                "published_baseline":{"release":published_release,"name":published_zip.name,
                                      "sha256":expected_sha,"commit":commit,"files":len(baseline_files),
                                      "selection_basis":"Caller-pinned published archive and Git commit; this utility performs no network publication check"},
                "internal_verified_working_checkpoint":{"release":state["baseline_release"],
                    "name":state["baseline_name"],"sha256":state["baseline_sha256"],
                    "files":state["baseline_files"],
                    "same_as_published_baseline":state["baseline_sha256"]==expected_sha,
                    "note":"Build/check input checkpoint, not a declaration that this version was deployed"},
                "standard_stage_package":{"schema":stage_manifest["schema"],"phase":"packaged",
                    "manifest_name":stage_manifest_path.name,"manifest_sha256":sha(stage_manifest_path),
                    "review_sha256":state["review_sha256"],"verified_artifact_sha256":state["verified_artifact_sha256"],
                    "verified_files_sha256":state["verified_files_sha256"],
                    "verified_graph_html_sha256":state["verified_graph_html_sha256"]},
                "full":{**stage_manifest["full"],"copied_byte_for_byte_from_verified_stage":True},
                "delta":{"name":delta_name,"sha256":sha(prepared/delta_name),
                         "size":(prepared/delta_name).stat().st_size,"files":len(delta_files)},
                "counts":counts,
                "verification":{"standard_checks":reports,"fresh_structure_passed":True,
                    "stage_full_matches_verified_candidate":True,"full_archive_bytes_preserved":True,
                    "published_baseline_plus_delta_equals_full":True,
                    "delta_only_changed_or_added_files":True,
                    "working_checkpoint_plus_cumulative_delta_equals_full":not working_mismatches,
                    "working_checkpoint_overlay_mismatches":working_mismatches,
                    "published_preservation":preservation,"deployed":False},
                "files":[{"path":p,"action":"overwrite" if p in baseline_files else "add",
                          "old_sha256":baseline_files.get(p,{}).get("sha256"),"new_sha256":full_files[p]["sha256"],
                          "old_size":baseline_files.get(p,{}).get("size"),"new_size":full_files[p]["size"]}
                         for p in sorted(changed+added)],
                "packaging_utility_sha256":sha(Path(__file__))
            }
            save(prepared / manifest_name, manifest)
            compatibility = ("The same delta also reconstructs the full site when applied to the verified working checkpoint v"
                             + str(state["baseline_release"]) + ".\n") if not working_mismatches else (
                             "Do not apply this delta to the working checkpoint. Use the published baseline or replace it with the full site.\n")
            instructions = (f"KNOWLEDGE ATLAS v{release} — {state['date']}\n\n"
                f"Published baseline: v{published_release}\nCommit: {commit}\nArchive SHA-256: {expected_sha}\n\n"
                f"Full site: {full_name}\nFull SHA-256: {manifest['full']['sha256']}\n"
                f"Cumulative delta: {delta_name}\nDelta SHA-256: {manifest['delta']['sha256']}\n\n"
                f"Overlay the extracted delta onto the published site directory containing index.html. Preserve paths.\n"
                f"Overwrite {len(changed)} files and add {len(added)} files. No deletions are required.\n"
                "The actual archive overlay was verified to reproduce every full-site file byte-for-byte.\n"
                + compatibility + "\nThe full archive is an unchanged copy of the standard verified stage package.\n"
                "Nothing has been deployed. Publish through the existing GitHub Pages workflow after review.\n")
            (prepared / instruction_name).write_text(instructions,encoding="utf-8")
            if output.exists(): output.rmdir()  # It was required to be empty.
            prepared.rename(output)
    return {"status":"cumulative_packaged","output":str(output),"manifest":manifest_name,
            "full":manifest["full"],"delta":manifest["delta"],"counts":counts,
            "published_baseline_plus_delta_equals_full":True,
            "working_checkpoint_plus_cumulative_delta_equals_full":not working_mismatches,"deployed":False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",type=Path,required=True,help="Already packaged standard atlas_cli run")
    parser.add_argument("--published-baseline",type=Path,required=True,help="Complete published website ZIP")
    parser.add_argument("--published-sha256",required=True,help="Pinned SHA-256 of that ZIP")
    parser.add_argument("--published-commit",required=True,help="Pinned full Git commit hash")
    parser.add_argument("--output",type=Path,required=True,help="New or empty directory separate from the run and stage output")
    args = parser.parse_args()
    try:
        print(json.dumps(cumulative_package(args),indent=2,ensure_ascii=False))
    except (ValueError,KeyError,OSError,zipfile.BadZipFile) as exc:
        print("Cumulative packaging refused: " + str(exc),file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
