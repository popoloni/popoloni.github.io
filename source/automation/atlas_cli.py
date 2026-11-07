#!/usr/bin/env python3
"""Repeatable Knowledge Atlas updates: prepare, discover, build, check, package.

All mutable work lives in the selected run directory. The supplied published
ZIP is fingerprinted and retained as the sole comparison baseline.
"""
from __future__ import annotations

import argparse
import collections
import copy
import datetime as dt
import hashlib
import html
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

TOOLS = Path(__file__).resolve().parent
VERSION = "1.1.0"
RUN_SCHEMA = "knowledge-atlas-update-run/1"
SKIP_PARTS = {".git", "__pycache__", ".pytest_cache", "node_modules"}
MAX_ARCHIVE_BYTES = 2 * 1024 ** 3
MAX_ARCHIVE_FILES = 20000


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def data_sha(data):
    return hashlib.sha256(data).hexdigest()


def files(root):
    root = Path(root)
    result = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if set(rel.parts) & SKIP_PARTS or p.suffix in (".pyc", ".pyo") or p.name == ".DS_Store":
            continue
        if p.is_symlink():
            raise ValueError("Unexpected symbolic link: " + str(p))
        if p.is_file():
            result[rel.as_posix()] = {"sha256": sha(p), "size": p.stat().st_size}
    return result


def safe_extract(archive_path, target):
    target = Path(target)
    seen = set()
    with zipfile.ZipFile(archive_path) as z:
        records = [i for i in z.infolist() if not i.is_dir()]
        if len(records) > MAX_ARCHIVE_FILES or sum(i.file_size for i in records) > MAX_ARCHIVE_BYTES:
            raise ValueError("Archive exceeds the documented file-count or uncompressed-size limit")
        for item in records:
            name = item.filename
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in path.parts[0] or name in seen:
                raise ValueError("Unsafe or duplicate archive path: " + name)
            if stat.S_ISLNK(item.external_attr >> 16) or item.flag_bits & 1:
                raise ValueError("Symbolic links and encrypted entries are not supported")
            if item.file_size > 200 * 1024 ** 2:
                raise ValueError("Unexpectedly large site entry: " + name)
            seen.add(name)
        target.mkdir(parents=True, exist_ok=True)
        z.extractall(target)
    return files(target)


def date_value(value):
    parsed = dt.date.fromisoformat(value)
    if parsed.year < 1980:
        raise ValueError("Date must be 1980 or later for portable ZIP timestamps")
    return parsed.isoformat()


def release_value(value):
    value = str(value).removeprefix("v")
    if not re.fullmatch(r"\d+(?:\.\d+){1,2}", value):
        raise ValueError("Release must have a numeric form such as 13.1 or 14.0.1")
    return value


def get_run(directory):
    from atlas_graph import payload_sha256
    root = Path(directory).resolve()
    state = load(root / "run.json")
    if state.get("schema") != RUN_SCHEMA:
        raise ValueError("Not a Knowledge Atlas update run")
    if sha(root / "baseline.zip") != state["baseline_sha256"]:
        raise ValueError("The immutable baseline ZIP has changed")
    if files(root / "baseline") != load(root / "baseline_manifest.json"):
        raise ValueError("The extracted baseline tree has changed")
    if payload_sha256(load(root / "baseline_payload.json")) != state["baseline_payload_sha256"]:
        raise ValueError("The cached immutable baseline payload has changed")
    return root, state


def graph_at(root):
    from atlas_graph import extract_payload
    return extract_payload((Path(root) / "swe_knowledge_graph.html").read_text(encoding="utf-8"))


def prepare(args):
    from atlas_graph import payload_sha256
    baseline = args.baseline.resolve()
    fingerprint = sha(baseline)
    if args.baseline_sha256 and fingerprint != args.baseline_sha256:
        raise ValueError("Supplied baseline checksum does not match the actual ZIP")
    root = args.run.resolve()
    if root.exists() and any(root.iterdir()):
        existing_root, old = get_run(root)
        if old["baseline_sha256"] == fingerprint and old["date"] == date_value(args.date) and old["release"] == release_value(args.release):
            print(json.dumps({"status": "resumed", "run": str(existing_root), "phase": old["phase"]}))
            return
        raise ValueError("Run directory already contains a different update; select a new directory")
    root.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(baseline, root / "baseline.zip")
    inventory = safe_extract(root / "baseline.zip", root / "baseline")
    if not (root / "baseline/index.html").is_file() or not (root / "baseline/swe_knowledge_graph.html").is_file():
        raise ValueError("The complete website ZIP must have index.html and swe_knowledge_graph.html at its root; do not use a delta")
    config_file = root / "baseline/source/site_config.json"
    if not config_file.is_file():
        raise ValueError("Missing site_config.json: this baseline needs an explicit format adapter")
    payload = graph_at(root / "baseline")
    config = load(config_file)
    if any(n.get("collection") == "N" for n in payload["nodes"]) and not (root / "baseline/source/ndse2_book.json").is_file():
        raise ValueError("Published N chapter records require the corresponding final book metadata")
    state = {"schema": RUN_SCHEMA, "tool_version": VERSION, "phase": "prepared", "date": date_value(args.date),
             "release": release_value(args.release), "baseline_name": baseline.name, "baseline_sha256": fingerprint,
             "baseline_payload_sha256": payload_sha256(payload), "baseline_release": config.get("site_version"),
             "baseline_graph_date": payload.get("meta", {}).get("date"), "baseline_files": len(inventory),
             "baseline_selection_basis": args.baseline_basis,
             "publication_state": "Baseline supplied as published; newly generated outputs are not automatically marked published"}
    save(root / "run.json", state)
    save(root / "baseline_manifest.json", inventory)
    save(root / "baseline_payload.json", payload)
    save(root / "vocabulary.json", {"collections": config["collections"], "themes": payload["themes"],
                                     "topics": payload["topics"], "chapters": payload["chapters"],
                                     "next_ids": {code: f'{code}{1+max([int(n["id"][1:]) for n in payload["nodes"] if re.fullmatch(code+r"\d+", n["id"])]+[0]):03}' for code in ("O", "P", "F")}})
    template = {"schema_version": 1, "baseline_sha256": fingerprint,
                "baseline_payload_sha256": state["baseline_payload_sha256"], "date": state["date"], "release": state["release"],
                "editorial_review": {"status": "pending", "reviewer": "", "scope": ""},
                "coverage": {"status": "pending", "through": state["date"], "sources": [], "limitations": []},
                "candidate_decisions": [], "additions": [], "revisions": [], "edges": [], "notes": [], "book_policy": "unchanged"}
    save(root / "review.json", template)
    print(json.dumps({"status": "prepared", "run": str(root), "baseline_files": len(inventory),
                      "baseline_sha256": fingerprint, "review_template": str(root / "review.json")}, ensure_ascii=False, indent=2))


def discover_command(args):
    from source_discovery import discover
    root, state = get_run(args.run)
    sources = load(args.sources or TOOLS / "sources.json")
    snapshots = args.snapshots
    result = discover(load(root / "baseline_payload.json"), state["date"], sources,
                      snapshots=snapshots, since=args.since or state.get("baseline_graph_date"))
    save(root / "discovery.json", result)
    save(root / "discovery_snapshot.json", result["metadata_snapshot"])
    draft = load(root / "review.json")
    draft["candidate_decisions"] = [
        {"candidate_key": c["candidate_key"], "url": c["url"], "decision": "pending", "reason": ""}
        for c in result.get("candidates", [])
    ]
    save(root / "review_candidates.json", draft)
    print(json.dumps({"status": "discovery_saved", "path": str(root / "discovery.json"),
                      "candidate_count": len(result.get("candidates", [])), "coverage": result.get("coverage")}, ensure_ascii=False, indent=2))


def reviewed_author_contexts(review, state):
    """Validate the named practitioner adapter's byline-only context overlay.

    Context stays separate from ordinary source operations in the reviewed
    input. Only build_to appends these validated records for the graph engine.
    """
    if "context_additions" in review and review.get("kind") != "atlas_practitioner_update/1":
        raise ValueError("context_additions requires the explicit atlas_practitioner_update/1 review kind")
    contexts = review.get("context_additions", [])
    if not isinstance(contexts, list) or any(not isinstance(item, dict) for item in contexts):
        raise ValueError("context_additions must be a list of reviewed credited-author records")
    if not contexts:
        return contexts

    from urllib.parse import urlsplit
    from source_discovery import normalize_url

    def nonempty(value):
        return isinstance(value, str) and bool(value.strip())

    def primary_url(value):
        if not nonempty(value):
            raise ValueError("Author context requires an explicit martinfowler.com primary URL")
        url = normalize_url(value)
        parsed = urlsplit(url)
        if parsed.hostname != "martinfowler.com" or parsed.port not in (None, 80, 443):
            raise ValueError("Author context evidence must be a public primary URL on martinfowler.com")
        return url

    def inspected_url(evidence):
        if not isinstance(evidence, dict) or evidence.get("reviewed_on") != state["date"] or evidence.get("access") != "full_public":
            raise ValueError("Author context needs dated full_public primary evidence")
        if not nonempty(evidence.get("scope")):
            raise ValueError("Author context evidence requires an explicit inspection scope")
        return primary_url(evidence.get("url"))

    # An author may be supported only by a newly included F article whose
    # actual byline and inspected public primary page are present in this review.
    sources = review.get("additions", [])
    if not isinstance(sources, list) or any(not isinstance(item, dict) for item in sources):
        raise ValueError("additions must be a list of reviewed source operations")
    articles = []
    for item in sources:
        if item.get("collection") != "F":
            continue
        attrs = item.get("attributes", {})
        if not isinstance(attrs, dict):
            continue
        try:
            names = json.loads(attrs.get("authors_json", "null"))
            if not isinstance(names, list) or not names or any(not nonempty(name) for name in names):
                continue
            evidence = item.get("evidence") or attrs.get("evidence_review")
            url = inspected_url(evidence)
            if primary_url(item.get("url")) != url:
                continue
        except (TypeError, ValueError):
            continue  # Restricted/metadata-only sources cannot establish a new context node.
        refs = {item["id"]} if nonempty(item.get("id")) else set()
        if nonempty(item.get("ref")):
            refs.add("$" + item["ref"].lstrip("$"))
        articles.append({"names": {name.strip() for name in names}, "url": url, "refs": refs})

    fields = {"id", "label", "kind", "collection", "category", "summary", "limitation", "url", "authors", "year",
              "streams", "actual", "mapped", "printed", "topics", "volumes", "attributes"}
    attribute_fields = {"provenance", "source_url", "evidence_review"}
    evidence_fields = {"reviewed_on", "access", "url", "scope", "locator", "note", "inspection_depth", "http_status",
                       "source_sha256", "source_bytes", "body_included_in_deliverable"}
    by_id = {}
    source_ids = {item["id"] for item in sources if nonempty(item.get("id"))}
    for item in contexts:
        nid = item.get("id")
        if not isinstance(nid, str) or not re.fullmatch(r"AUTHOR:MF:[a-z0-9-]+", nid):
            raise ValueError("Author context ID must match AUTHOR:MF:[a-z0-9-]+")
        if nid in by_id or nid in source_ids:
            raise ValueError("Duplicate author context ID: " + nid)
        if set(item) - fields:
            raise ValueError("Unsupported author context fields (including book/citation fields): " + ", ".join(sorted(set(item) - fields)))
        if "collection" not in item or item["collection"] is not None or item.get("kind") != "credited_author" or item.get("category") != "contributors":
            raise ValueError("Author context requires collection=null, kind=credited_author and category=contributors")
        for field in ("label", "summary", "authors"):
            if not nonempty(item.get(field)):
                raise ValueError("Author context requires a nonempty " + field)
        if item["authors"].strip() != item["label"].strip():
            raise ValueError("Author context authors must name its credited label")
        if item.get("actual") != [] or item.get("volumes") != [] or item.get("printed") is not False:
            raise ValueError("Author context requires explicit actual=[], volumes=[] and printed=false")
        for field in ("streams", "topics", "mapped"):
            if item.get(field, []) != []:
                raise ValueError("Author context cannot claim source classification or chapter mapping: " + field)
        if item.get("year", "") != "" or not isinstance(item.get("limitation", ""), str):
            raise ValueError("Author context has no source publication year and limitation must be text")
        attrs = item.get("attributes")
        if not isinstance(attrs, dict) or set(attrs) - attribute_fields:
            raise ValueError("Author context attributes support only provenance, source_url and evidence_review; book/citation attributes are prohibited")
        if not nonempty(attrs.get("provenance")):
            raise ValueError("Author context requires explicit attributes.provenance")
        evidence = attrs.get("evidence_review")
        url = inspected_url(evidence)
        if set(evidence) - evidence_fields:
            raise ValueError("Unsupported author context evidence fields; book/citation fields are prohibited")
        if primary_url(item.get("url")) != url or ("source_url" in attrs and primary_url(attrs["source_url"]) != url):
            raise ValueError("Author context URL and source_url must identify its inspected primary article")
        if not any(item["label"].strip() in article["names"] and url == article["url"] for article in articles):
            raise ValueError("Author context label and evidence URL must match the authors_json and inspected primary URL of an included F article: " + nid)
        by_id[nid] = item

    # Each optional authored-by edge must independently match that article's
    # byline; a valid author node cannot be used to misattribute another source.
    edges = review.get("edges", [])
    if not isinstance(edges, list) or any(not isinstance(edge, dict) for edge in edges):
        raise ValueError("edges must be a list of reviewed relationships")
    for edge in edges:
        source, target = edge.get("source"), edge.get("target")
        if source not in by_id and target not in by_id:
            continue
        if target not in by_id or source in by_id or edge.get("relation") != "F_AUTHORED_BY" or edge.get("family") != "provenance":
            raise ValueError("New author context supports only incoming F_AUTHORED_BY provenance relationships")
        linked = [article for article in articles if source in article["refs"]]
        attrs = edge.get("attributes")
        if len(linked) != 1 or by_id[target]["label"].strip() not in linked[0]["names"]:
            raise ValueError("Author relationship must match the actual byline of an included F article")
        if not isinstance(attrs, dict) or not nonempty(attrs.get("provenance")) or primary_url(attrs.get("source_url")) != linked[0]["url"]:
            raise ValueError("Author relationship requires provenance and that article's inspected primary source_url")
    return contexts


def validate_review(review, state, discovery=None):
    if any(field in review for field in ("mappings", "exclusions")) and review.get("kind") != "atlas_practice_links_update/1":
        raise ValueError("Source-practice mappings and exclusions require the explicit atlas_practice_links_update/1 adapter")
    reviewed_author_contexts(review, state)
    if review.get('kind') == 'atlas_practice_links_update/1':
        from practice_links_update import validate_review as validate_practice_links_review
        return validate_practice_links_review(review, state)
    if review.get('kind') == 'atlas_polimi_update/1':
        from polimi_migration import validate_review as validate_polimi_review
        return validate_polimi_review(review, state)
    if review.get('kind') == 'atlas_practices_update/1':
        from practices_migration import validate_review as validate_practice_review
        return validate_practice_review(review, state)
    from urllib.parse import urlsplit
    import ipaddress
    from source_discovery import normalize_url

    def nonempty(value):
        return isinstance(value, str) and bool(value.strip())

    def text_list(value, field):
        if not isinstance(value, list) or any(not nonempty(item) for item in value):
            raise ValueError(field + " must be a list of nonempty strings")
        return value

    def public_url(value, field):
        if not nonempty(value):
            raise ValueError(field + " requires an explicit public source URL")
        try:
            url = normalize_url(value)
            parsed = urlsplit(url)
            host = parsed.hostname or ""
            if parsed.port not in (None, 80, 443) or host == "localhost" or host.endswith((".local", ".localhost", ".internal")):
                raise ValueError("local host or nonstandard port")
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                address = None
            if address is not None and not address.is_global:
                raise ValueError("private or special-purpose address")
        except (ValueError, TypeError) as exc:
            raise ValueError(field + " must be a credential-free public HTTP(S) URL: " + str(exc)) from exc
        return url

    def url_list(value, field):
        if not isinstance(value, list) or not value:
            raise ValueError(field + " requires at least one primary URL")
        return [public_url(url, field) for url in value]

    if review.get("schema_version") != 1:
        raise ValueError("Review schema_version must be 1")
    for field in ("baseline_sha256", "baseline_payload_sha256", "date"):
        if review.get(field) != state[field]:
            raise ValueError("Review does not match the prepared run: " + field)
    if release_value(review.get("release", "")) != state["release"]:
        raise ValueError("Review release differs from this run")
    if review.get("editorial_review", {}).get("status") != "complete" or not nonempty(review["editorial_review"].get("reviewer")):
        raise ValueError("Finish the editorial review and identify its reviewer before building")
    coverage = review.get("coverage", {})
    if coverage.get("status") not in ("complete", "complete_with_disclosed_limits") or coverage.get("through") != state["date"]:
        raise ValueError("Record source coverage through the requested date, including any access or feed limits")
    limits = text_list(coverage.get("limitations", []), "coverage.limitations") + text_list(coverage.get("limits", []), "coverage.limits")
    limited = coverage["status"] == "complete_with_disclosed_limits"
    if limited and not limits:
        raise ValueError("complete_with_disclosed_limits requires nonempty coverage.limits or coverage.limitations")
    primary_hosts = {"O": {"addyosmani.com", "addyo.substack.com"}, "F": {"martinfowler.com"},
                     "P": {"newsletter.pragmaticengineer.com", "blog.pragmaticengineer.com"}}
    source_records = coverage.get("sources", [])
    if not isinstance(source_records, list) or not source_records:
        raise ValueError("Coverage requires source records for each of O, P and F")
    covered = set()
    for source in source_records:
        if not isinstance(source, dict) or source.get("collection") not in primary_hosts:
            raise ValueError("Each coverage.sources record requires collection O, P or F")
        code = source["collection"]
        urls = url_list(source.get("urls"), "coverage.sources[" + code + "].urls")
        if not any(urlsplit(url).hostname in primary_hosts[code] for url in urls):
            raise ValueError("Coverage for " + code + " requires an official source URL for that collection")
        if not nonempty(source.get("method")) or source.get("status") not in ("complete", "limited"):
            raise ValueError("Each coverage source needs a concrete method and status complete or limited")
        source_limits = text_list(source.get("limitations", []), "coverage.sources[" + code + "].limitations")
        if source["status"] == "limited" and (not source_limits or not limited):
            raise ValueError("A limited source requires its own limitations and overall complete_with_disclosed_limits")
        if source.get("through", state["date"]) != state["date"]:
            raise ValueError("Per-source coverage must reach the requested date, with limits explicitly disclosed")
        covered.add(code)
    if covered != set(primary_hosts):
        raise ValueError("Missing reviewed source coverage for: " + ", ".join(sorted(set(primary_hosts) - covered)))

    # 'Complete' means that the declared review is complete, not that a rolling
    # public feed proves an exhaustive archive. Every observed gap must have an
    # explicit fallback review or a disclosed limitation, never silent success.
    resolutions = coverage.get("gap_resolutions", [])
    if not isinstance(resolutions, list):
        raise ValueError("coverage.gap_resolutions must be a list keyed by endpoint and reason")
    resolved_by_key = {}
    for resolution in resolutions:
        if not isinstance(resolution, dict) or not nonempty(resolution.get("endpoint")) or not nonempty(resolution.get("reason")):
            raise ValueError("Each gap resolution needs the exact discovery endpoint and reason")
        key = (resolution["endpoint"], resolution["reason"])
        if key in resolved_by_key:
            raise ValueError("Duplicate gap resolution: " + " | ".join(key))
        if resolution.get("status") not in ("resolved", "disclosed") or not nonempty(resolution.get("note")):
            raise ValueError("A gap resolution needs status resolved/disclosed and an explanation")
        if resolution["status"] == "resolved":
            url_list(resolution.get("primary_urls"), "gap_resolutions.primary_urls")
        elif not limited or not limits:
            raise ValueError("A disclosed gap requires overall complete_with_disclosed_limits and nonempty limits")
        elif resolution.get("primary_urls"):
            url_list(resolution["primary_urls"], "gap_resolutions.primary_urls")
        resolved_by_key[key] = resolution
    if discovery:
        gaps = list(discovery.get("coverage", {}).get("gaps", []))
        reports = {entry.get("id"): entry for entry in discovery.get("endpoints", [])}
        observed_endpoints = {gap.get("endpoint") for gap in gaps}
        for endpoint in discovery.get("coverage", {}).get("failed_endpoints", []):
            if endpoint not in observed_endpoints:
                gaps.append({"endpoint": endpoint, "reason": reports.get(endpoint, {}).get("error", "endpoint_failed")})
        for gap in gaps:
            key = (gap.get("endpoint"), gap.get("reason"))
            if key not in resolved_by_key:
                raise ValueError("Unresolved discovery coverage gap: " + " | ".join(map(str, key)))

    operations = {}
    for operation in ("additions", "revisions"):
        items = review.get(operation, [])
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise ValueError(operation + " must be a list of reviewed operations")
        operations[operation] = items
        for item in items:
            ev = item.get("evidence") or item.get("attributes", {}).get("evidence_review") or item.get("attributes_patch", {}).get("evidence_review")
            if not isinstance(ev, dict) or ev.get("reviewed_on") != state["date"] or ev.get("access") not in ("full_public", "restricted_preview", "metadata_only"):
                raise ValueError("Every addition/revision needs dated primary-source evidence and an honest access classification")
            public_url(ev.get("url"), operation + ".evidence.url")
            if ev["access"] != "full_public" and not any(nonempty(ev.get(field)) for field in ("scope", "locator", "note")):
                raise ValueError("Restricted/metadata-only evidence must describe the material actually inspected (scope, locator or note)")
            if operation == "additions":
                if item.get("collection") not in ("O", "P", "F"):
                    raise ValueError("This procedure preserves W and earlier-book collections; other changes need an explicit adapter")
                for field in ("label", "authors", "url", "summary", "limitation"):
                    if not nonempty(item.get(field)):
                        raise ValueError("Reviewed additions require a nonempty " + field)
                public_url(item["url"], "addition.url")
            elif not nonempty(item.get("id")) or not nonempty(item.get("reason")):
                raise ValueError("Reviewed revisions require an existing ID and an explicit reason")
            if item.get("patch", {}).get("url"):
                public_url(item["patch"]["url"], "revision.patch.url")

    decisions = review.get("candidate_decisions", [])
    if not isinstance(decisions, list) or any(not isinstance(d, dict) or d.get("decision") not in ("add", "revise", "exclude", "already_present") or not nonempty(d.get("reason")) for d in decisions):
        raise ValueError("Each candidate decision needs an explicit disposition and reason")
    candidates = discovery.get("candidates", []) if discovery else []
    reviewed_candidates = set()
    for decision in decisions:
        decision_url = public_url(decision["url"], "candidate_decision.url") if decision.get("url") else None
        key = decision.get("candidate_key") or decision.get("candidate_id")
        matched = [c for c in candidates if key and key == (c.get("candidate_key") or c.get("candidate_id"))]
        if not matched and decision_url:
            matched = [c for c in candidates if public_url(c["url"], "discovery.candidate.url") == decision_url]
        if len(matched) > 1:
            raise ValueError("Ambiguous candidate decision; identify it by candidate_key")
        candidate = matched[0] if matched else None
        if key and candidates and candidate is None:
            raise ValueError("Unknown discovery candidate key: " + str(key))
        if candidate:
            identity = candidate.get("candidate_key") or candidate["url"]
            if identity in reviewed_candidates:
                raise ValueError("Duplicate decisions for discovery candidate: " + identity)
            reviewed_candidates.add(identity)
        if decision["decision"] not in ("add", "revise"):
            continue
        operation = "additions" if decision["decision"] == "add" else "revisions"
        reference = decision.get("operation_ref") or decision.get("ref") or decision.get("existing_id") or decision.get("id")
        refs = {str(reference).lstrip("$")} if reference else set()
        urls = {decision_url} if decision_url else set()
        baseline_ids = set()
        if candidate:
            urls.add(public_url(candidate["url"], "discovery.candidate.url"))
            baseline_ids.update(candidate.get("baseline_ids", []))
            baseline_ids.update(candidate.get("possible_syndication_ids", []))
            baseline_ids.update(candidate.get("related_edition_ids", []))
        matched_operations = []
        for item in operations[operation]:
            if candidate and candidate.get("collection"):
                code = item.get("collection") if operation == "additions" else str(item.get("id", ""))[:1]
                if code != candidate["collection"]:
                    continue
            item_refs = {str(value).lstrip("$") for value in (item.get("id"), item.get("ref")) if value}
            if refs:
                linked = bool(refs & item_refs)
            else:
                item_urls = {public_url(value, "operation.url") for value in (item.get("url"), item.get("patch", {}).get("url")) if value}
                ev = item.get("evidence") or item.get("attributes", {}).get("evidence_review") or item.get("attributes_patch", {}).get("evidence_review") or {}
                if operation == "revisions" and ev.get("url"):
                    item_urls.add(public_url(ev["url"], "revision.evidence.url"))
                linked = bool(urls & item_urls) or (operation == "revisions" and item.get("id") in baseline_ids)
            if linked:
                matched_operations.append(item)
        if len(matched_operations) != 1:
            raise ValueError("Candidate decision " + decision["decision"] + " must link to exactly one actual " + operation + " operation via URL, operation_ref/ref or existing ID")
    unresolved = [c.get("candidate_key") or c["url"] for c in candidates if (c.get("candidate_key") or c["url"]) not in reviewed_candidates]
    if unresolved:
        raise ValueError("Unreviewed discovery candidates: " + ", ".join(map(str, unresolved[:20])))
    if review.get("book_policy", "unchanged") not in ("unchanged", "reconcile"):
        raise ValueError("book_policy must be unchanged or reconcile")


def tool_files():
    names = ["atlas_cli.py", "atlas_graph.py", "atlas_validate.py", "source_discovery.py", "sources.json",
             "browser_check.js", "build_site.py", "build_ndse2_pages.py", "book_tools.py", "extract_ndse2_base.py",
             "practices_checks.py", "practices_migration.py", "practice_book_context.py", "PRACTICES_UPDATE.txt",
             "polimi_migration.py", "POLIMI_UPDATE.txt", "PRACTITIONER_UPDATE.txt",
             "cumulative_package.py", "CUMULATIVE_UPDATE.txt", "practice_links_update.py", "PRACTICE_LINKS_UPDATE.txt",
             "practice_links_ui.py"]
    return [name for name in names if (TOOLS / name).is_file()]


def install_tools(destination):
    target = destination / "source/automation"
    target.mkdir(parents=True, exist_ok=True)
    for name in tool_files():
        shutil.copyfile(TOOLS / name, target / name)
    for name in ("build_site.py", "build_ndse2_pages.py", "practice_links_ui.py"):
        if name == "practice_links_ui.py" and not (TOOLS / name).is_file():
            continue
        shutil.copyfile(TOOLS / name, destination / "source" / name)


def export_book_views(root, book):
    rows, occurrences, chapters = [], [], []
    for c in book["chapters"]:
        it = {s["id"]: s for s in c.get("sections_it", [])}
        for s in c.get("sections", []):
            other = it.get(s["id"], {})
            rows.append({**s, "chapter_id": c["id"], "chapter_hub": c["hub_id"], "title_it": other.get("title", ""),
                         "file_it": other.get("file", ""), "line_it": other.get("line"), "sha256_it": other.get("sha256", "")})
        chapters.append({"id": c["id"], "hub_id": c["hub_id"], "number": c["number"], "title": c["title"],
                         "title_it": c.get("title_it", ""), "literal_source_ids": sorted(set(c["source_ids"])),
                         "literal_citation_count": len(c["citations"]), "section_count": len(c["sections"])})
    for unit in book["chapters"] + book.get("nonchapter_units", []):
        if "INDEX" in unit["id"].upper() or "index" in unit.get("kind", ""):
            continue
        for language, key in (("EN", "citations"), ("ITA", "citations_it")):
            occurrences.extend({**c, "language": language, "owner_id": unit["id"]} for c in unit.get(key, []))
    save(root / "data/catalogues/ndse2-sections.json", {"records": rows})
    save(root / "data/catalogues/ndse2-chapter-citations.json", {"records": chapters})
    save(root / "data/updates/ndse2_source_manifest.json", book.get("source_manifest", {}))
    save(root / "data/updates/ndse2_citation_occurrences.json", {"meta": {"source_version": book["book"]["source_version"],
              "basis": "Active literal body citations; identifier index and nocite excluded"}, "occurrences": occurrences})
    import csv
    with (root / "data/catalogues/ndse2-citation-occurrences.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["language", "chapter_hub", "owner_id", "section_id", "source_id", "bibkey", "macro", "file", "line", "sha256"], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(occurrences)


def run_builder(site):
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONHASHSEED"] = "0"
    done = subprocess.run([sys.executable, "-B", str(site / "source/build_site.py")], cwd=site, env=env,
                          capture_output=True, text=True, timeout=180)
    if done.returncode:
        raise ValueError("Static rebuild failed: " + (done.stderr or done.stdout)[-5000:])


def release_paths(state):
    suffix = 'v' + state['release'].replace('.', '_') + '_' + state['date'].replace('-', '')
    return {"release_notes": 'UPDATE_' + suffix + '.html',
            "research_audit": 'data/updates/source_review_' + suffix + '.json'}


def render_update_page(site, state, audit, review):
    esc = lambda x: html.escape(str(x))
    allocated = {item['position']: item['id'] for item in audit.get('assigned_ids', [])}
    slugs = {'O': 'osmani', 'P': 'pragmatic-engineer', 'F': 'fowler'}
    groups = {'new': [], 'backfill': []}
    for i, n in enumerate(review.get('additions', [])):
        nid = n.get('id') or allocated.get(i, '')
        record_url = 'catalogues/' + slugs[n['collection']] + '.html#' + nid
        date = n.get('attributes', {}).get('publication_date') or n.get('year', '')
        item = '<li><strong><a href="' + record_url + '">' + esc(nid) + ' · ' + esc(n['label']) + '</a></strong><br>' + esc(n['authors']) + ' · ' + esc(date) + '<p>' + esc(n['summary']) + '</p></li>'
        key = 'backfill' if n.get('attributes', {}).get('discovery_category') == 'older_backfill' else 'new'
        groups[key].append(item)
    body = f'<p class="eyebrow">Reviewed {esc(state["date"])} · v{esc(state["release"])}</p><h1>Practitioner sources: review and update</h1>'
    body += '<p>' + esc(review.get('release_intro', 'Reviewed updates from Osmani, The Pragmatic Engineer and Martin Fowler’s website.')) + '</p>'
    body += '<h2>Source coverage</h2><table><thead><tr><th>Collection</th><th>Outcome</th><th>Inspection limits</th></tr></thead><tbody>'
    for source in review.get('coverage', {}).get('sources', []):
        label = {'O': 'Addy Osmani', 'P': 'The Pragmatic Engineer', 'F': 'Martin Fowler’s website'}.get(source['collection'], source['collection'])
        limits = '; '.join(source.get('limitations', [])) or 'No additional source-specific limitation recorded.'
        body += '<tr><th>' + esc(label) + '</th><td>' + esc(source.get('outcome', source.get('method', ''))) + '</td><td>' + esc(limits) + '</td></tr>'
    body += '</tbody></table>'
    for key, title in [('new', 'New publications since the previous source review'), ('backfill', 'Older articles newly catalogued')]:
        if groups[key]:
            body += '<h2>' + title + '</h2><ul>' + ''.join(groups[key]) + '</ul>'
    if review.get('revisions'):
        body += '<h2>Existing records revised</h2><ul>' + ''.join('<li><strong>' + esc(r['id']) + '</strong>: ' + esc(r['reason']) + '</li>' for r in review['revisions']) + '</ul>'
    body += '<h2>Evidence and preservation</h2><p>Dates distinguish original publication from subsequent activity. Older omissions are labelled as backfills. Public previews remain separate from full-text inspection, and practitioner arguments are not treated as independently replicated research.</p>'
    for note in review.get('notes', []):
        body += '<p>' + esc(note) + '</p>'
    polimi_notes = load(site / 'source/site_config.json').get('polimi_update', {}).get('release_notes')
    if polimi_notes:
        body += '<p>The 36 SEPolimi additions and 14 revisions from v13.3 are retained. <a href="' + esc(polimi_notes) + '">Read the SEPolimi update</a>.</p>'
    body += '<p>All existing node IDs and keyed relationships are retained. Actual book citations, bibliography membership and editorial reading mappings remain distinct. Book policy: ' + esc(review.get('book_policy', 'unchanged')) + '.</p>'
    body += '<h2>Build and publication baselines</h2><p>Verified working checkpoint: <code>' + esc(state['baseline_name']) + '</code>.</p><p>SHA-256: <code style="overflow-wrap:anywhere">' + state['baseline_sha256'] + '</code></p>'
    published = review.get('published_baseline', {})
    if published:
        body += '<p>The cumulative publication delta is compared with the published v' + esc(published['release']) + ' repository at commit <code>' + esc(published['commit']) + '</code>. The working checkpoint above is an intermediate release, not a claim of deployment.</p>'
    body += '<p><a href="' + release_paths(state)['research_audit'] + '">Complete source review and candidate decisions</a> · <a href="verification/report.html">Release verification</a> · <a href="index.html">Home</a></p>'
    body += '<p>The packages are generated and checked locally; publication uses the existing GitHub Pages workflow.</p>'
    filename = release_paths(state)['release_notes']
    (site / filename).write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Atlas source review and update</title><link rel="stylesheet" href="assets/site.css"><body><main class="wrap" id="main">' + body + '</main></body></html>', encoding='utf-8')


def build_to(root, destination, state, review, book):
    if any(field in review for field in ("mappings", "exclusions")) and review.get("kind") != "atlas_practice_links_update/1":
        raise ValueError("Source-practice mappings and exclusions require the explicit atlas_practice_links_update/1 adapter")
    contexts = reviewed_author_contexts(review, state)
    if review.get('kind') == 'atlas_practice_links_update/1':
        from practice_links_update import build_practice_links_to
        return build_practice_links_to(root, destination, state, review, book)
    if review.get('kind') == 'atlas_polimi_update/1':
        from polimi_migration import build_polimi_to
        return build_polimi_to(root, destination, state, review, book)
    if review.get('kind') == 'atlas_practices_update/1':
        from practices_migration import build_practices_to
        return build_practices_to(root, destination, state, review, book)
    from atlas_graph import apply_update, export_raw, payload_sha256, render_current_atlas, write_graphml
    shutil.copytree(root / "baseline", destination, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git'))
    old = load(root / "baseline_payload.json")
    old_book_path = root / "baseline/source/ndse2_book.json"
    old_book = load(old_book_path) if old_book_path.is_file() else None
    no_changes = not any(review.get(k) for k in ("additions", "context_additions", "revisions", "edges", "mappings", "exclusions")) and (book is None or book == old_book)
    if no_changes:
        return {"no_changes": True, "source_additions": [], "baseline_nodes": len(old["nodes"]), "nodes": len(old["nodes"]), "edges": len(old["edges"])}
    engine_review = copy.deepcopy(review)
    engine_review["source_review_path"] = release_paths(state)['research_audit']
    # Source operations retain their positions and IDs; contributor records are
    # an explicit, separately validated overlay at the end of the engine input.
    context_ids = [item["id"] for item in contexts]
    if contexts:
        engine_contexts = copy.deepcopy(contexts)
        for item in engine_contexts:
            item["attributes"].update(atlas_context_review_kind=review["kind"],
                                      atlas_context_review_path=engine_review["source_review_path"])
        engine_review["additions"] = engine_review.get("additions", []) + engine_contexts
    new, audit = apply_update(old, engine_review, book=book)
    if book is not None:
        from practice_book_context import reconcile_practice_book_context
        audit["practice_book_context"] = reconcile_practice_book_context(new, book, engine_review)
    audit["source_additions"] = [n["id"] for n in new["nodes"][len(old["nodes"]):] if n.get("collection") in ("W", "O", "P", "F", "B", "N")]
    if contexts:
        audit.update(context_additions=context_ids, context_review_kind=review["kind"],
                     context_policy="Credited-author context bound to reviewed included F bylines; not source records or book citations")
        new["meta"]["graphAttributes"].update(practitioner_context_review_kind=review["kind"],
            practitioner_context_review_source=engine_review["source_review_path"],
            practitioner_context_added_ids_json=json.dumps(context_ids, ensure_ascii=False))
    audit["no_changes"] = False
    install_tools(destination)
    config = load(destination / "source/site_config.json")
    if config.get('polimi_update'):
        config['polimi_update'].setdefault('release_notes', config.get('release_notes'))
    config.update(site_version=state["release"], graph_version=state["release"], build_date=state["date"], graph_snapshot=state["date"],
                  atlas_source="atlas_current.html", graph_json="data/graph/knowledge_graph_current.json",
                  graph_graphml="data/graph/knowledge_graph_current.graphml", payload_json="data/graph/atlas_payload_current.json",
                  book_json="source/ndse2_book.json", book_occurrences_json="data/updates/ndse2_citation_occurrences.json",
                  **release_paths(state))
    config['practitioner_update'] = {'date': state['date'], 'release': state['release'],
        'added_ids': audit['source_additions'], 'revised_ids': [r['id'] for r in review.get('revisions', [])],
        'coverage': review['coverage']}
    if contexts:
        config['practitioner_update']['context_added_ids'] = context_ids
        config['practitioner_update']['context_review_kind'] = review['kind']
    if book is not None and book.get('meta', {}).get('parser_name') == 'extract_ndse2_base.py':
        config['book_extractor'] = 'source/automation/extract_ndse2_base.py'
    elif book is not None and book.get('meta', {}).get('parser_sha256') == sha(TOOLS / 'extract_ndse2_base.py'):
        config['book_extractor'] = 'source/automation/extract_ndse2_base.py'
    counts = collections.Counter(n.get("collection") for n in new["nodes"])
    descriptions = {
        "O": f'{counts["O"]} reviewed Addy Osmani records. Source arguments and independent evidence remain distinct.',
        "P": f'{counts["P"]} written Pragmatic Engineer records. Blog and Deepdives are deduplicated; The Pulse title-prefix and podcast exclusions remain in force.',
        "F": f'{counts["F"]} records on Martin Fowler’s website, retaining actual bylines, publication and revision dates, and explicit series or adjacent-site scope.',
    }
    for collection in config["collections"]:
        if collection["code"] in descriptions:
            collection["description"] = descriptions[collection["code"]]
    save(destination / "source/site_config.json", config)
    new["meta"]["graphFile"] = "knowledge_graph_current.graphml"
    raw = export_raw(new)
    write_graphml(raw, destination / config["graph_graphml"])
    new["meta"]["graphSha256"] = sha(destination / config["graph_graphml"])
    audit["result_payload_sha256"] = payload_sha256(new)
    save(destination / config["graph_json"], export_raw(new))
    save(destination / config["payload_json"], new)
    old_config = load(root / "baseline/source/site_config.json")
    source_template = root / "baseline/source" / old_config.get("atlas_source", "atlas_v12_original.html")
    baseline_html = source_template.read_text(encoding="utf-8") if source_template.is_file() else (root / "baseline/swe_knowledge_graph.html").read_text(encoding="utf-8")
    current = render_current_atlas(baseline_html, new, version=state["release"], date=state["date"])
    (destination / "source/atlas_current.html").write_text(current, encoding="utf-8")
    if book is not None:
        save(destination / "source/ndse2_book.json", book)
        export_book_views(destination, book)
    save(destination / config["research_audit"], {"as_of": state["date"], "review": review, "graph_update": audit})
    release_info = {"tool_version": VERSION, "date": state["date"], "release": state["release"],
         "baseline_name": state["baseline_name"], "baseline_sha256": state["baseline_sha256"], "source_additions": audit["source_additions"]}
    if contexts:
        release_info.update(context_additions=context_ids, context_review_kind=review["kind"])
    save(destination / "source/automation_release.json", release_info)
    render_update_page(destination, state, audit, review)
    run_builder(destination)
    return audit


def build_command(args):
    root, state = get_run(args.run)
    review = load(args.review or root / "review.json")
    discovery = load(root / "discovery.json") if (root / "discovery.json").is_file() else None
    validate_review(review, state, discovery)
    book = load(args.book) if args.book else None
    if review.get("book_policy") == "reconcile" and book is None:
        raise ValueError("book_policy=reconcile requires --book with final reviewed metadata")
    if book is not None and review.get("book_policy") != "reconcile":
        raise ValueError("A changed book requires explicit book_policy=reconcile")
    if book and (book.get("meta", {}).get("editorial_review_required") or any(c.get("editorial_review_required") for c in book["chapters"])):
        raise ValueError("Review chapter summaries and goals before clearing editorial_review_required in new book metadata")
    if book and (book.get("meta", {}).get("build_blocked") or book.get("meta", {}).get("extraction_blockers")):
        raise ValueError("Resolve manuscript extraction blockers before reconciling the book: " + str(book.get("meta", {}).get("extraction_blockers", [])))
    stage = root / "candidate.building"
    if stage.exists():
        shutil.rmtree(stage)
    audit = build_to(root, stage, state, review, book)
    if set(load(root / "baseline_manifest.json")) - set(files(stage)):
        raise ValueError("Build removed a baseline file; copy-only deltas forbid deletions")
    candidate = root / "candidate"
    if candidate.exists():
        shutil.rmtree(candidate)
    stage.rename(candidate)
    save(root / "inputs/review.json", review)
    if book is not None:
        save(root / "inputs/book.json", book)
    elif (root / "inputs/book.json").exists():
        (root / "inputs/book.json").unlink()
    save(root / "update_audit.json", audit)
    state.update(phase="built", no_changes=audit["no_changes"], review_sha256=sha(root / "inputs/review.json"),
                 book_sha256=sha(root / "inputs/book.json") if book is not None else None)
    state.pop("verified_artifact_sha256", None)
    save(root / "run.json", state)
    print(json.dumps({"status": "unchanged" if audit["no_changes"] else "built", "candidate": str(candidate),
                      "source_additions": audit["source_additions"]}, ensure_ascii=False, indent=2))


def check_inputs(root, state):
    if sha(root / "inputs/review.json") != state.get("review_sha256"):
        raise ValueError("Frozen reviewed input changed; run build again")
    if state.get("book_sha256") and sha(root / "inputs/book.json") != state["book_sha256"]:
        raise ValueError("Frozen book metadata changed; run build again")


def final_inventory_sha256(site):
    inventory = {p: m for p, m in files(site).items() if p != 'SHA256SUMS.txt'}
    return data_sha(json.dumps(inventory, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8'))


def report_page(site, state, reports):
    esc = html.escape
    rows = ''.join('<tr><th>' + name + '</th><td>' + str(r.get('passed', 0)) + ' passed / ' + str(r.get('failed', 0)) + ' failed</td></tr>' for name, r in reports.items())
    body = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Atlas verification</title><link rel="stylesheet" href="../assets/site.css"><body><main class="wrap" id="main">'
    body += '<h1>Release verification</h1><p>Atlas v' + esc(state['release']) + ' · ' + esc(state['date']) + '</p><table>' + rows + '</table>'
    body += '<p>Browser checks use real local HTTP navigation. Exact existing node IDs and keyed edges, catalogue links, current source counts, chapter citations and two deterministic rebuilds are checked. This report does not assert deployment to GitHub or native Safari coverage.</p>'
    body += '<p>Retained verification images and other older check files belong to their historical releases. Current results are in the files linked below.</p><ul>'
    for name in reports:
        body += '<li><a href="automation_' + name + '.json">' + name + '</a></li>'
    body += '</ul><p><a href="../index.html">Atlas homepage</a></p></main></body></html>'
    (site / "verification/report.html").write_text(body, encoding="utf-8")


def check_command(args):
    from atlas_validate import validate_site
    root, state = get_run(args.run)
    check_inputs(root, state)
    candidate = root / "candidate"
    audit = load(root / "update_audit.json")
    changes = {**audit, "baseline_html": str(root / "baseline/swe_knowledge_graph.html")}
    book = load(candidate / "source/ndse2_book.json") if (candidate / "source/ndse2_book.json").is_file() else None
    (root / "reports").mkdir(exist_ok=True)
    save(root / "reports/expected_changes.json", changes)
    structure = validate_site(candidate, baseline_payload=load(root / "baseline_payload.json"), expected_changes=changes, book=book)
    save(root / "reports/structure.json", structure)
    if structure.get("failed") or not structure.get("complete", True):
        raise ValueError("Structural verification failed; see reports/structure.json")
    report_file = root / "reports/browser/browser_checks.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    command = [args.node or "node", str(TOOLS / "browser_check.js"), "--site", str(candidate), "--output", str(report_file),
               "--baseline", str(root / "baseline/swe_knowledge_graph.html"), "--changes", str(root / "reports/expected_changes.json")]
    if args.browser:
        command += ["--browser", str(args.browser.resolve())]
    if args.playwright:
        command += ["--playwright", str(args.playwright.resolve())]
    done = subprocess.run(command, text=True, capture_output=True, timeout=300)
    (root / "reports/browser.log").write_text(done.stdout + done.stderr, encoding="utf-8")
    browser = load(report_file) if report_file.exists() else {"complete": False, "failed": 1, "error": "No browser report"}
    if done.returncode or not browser.get("complete") or browser.get("failed"):
        raise ValueError("Browser verification incomplete or failed; see reports/browser.log. Packaging remains unavailable.")
    if browser.get("artifact_sha256") != structure.get("artifact_sha256"):
        raise ValueError("Browser and structural checks did not inspect the same artifact")
    review = load(root / "inputs/review.json")
    changed_book = load(root / "inputs/book.json") if state.get("book_sha256") else None
    actual_files = files(candidate)
    compared = {p: m for p, m in actual_files.items() if not p.startswith("verification/") and p != "SHA256SUMS.txt"}
    with tempfile.TemporaryDirectory(prefix="atlas-rebuild-") as temp:
        results = []
        for number in (1, 2):
            rebuilt = Path(temp) / str(number)
            build_to(root, rebuilt, state, review, changed_book)
            result = {p: m for p, m in files(rebuilt).items() if not p.startswith("verification/") and p != "SHA256SUMS.txt"}
            results.append(result)
        mismatches = sorted(p for p in set(compared) | set(results[0]) | set(results[1]) if compared.get(p) != results[0].get(p) or compared.get(p) != results[1].get(p))
    repro = {"complete": True, "passed": len(compared) - len(mismatches), "failed": len(mismatches), "outputs_tested": len(compared),
             "artifact_sha256": structure["artifact_sha256"], "method": "Two independent rebuilds from the immutable ZIP and frozen reviewed inputs; compare delivered bytes", "mismatches": mismatches}
    save(root / "reports/reproducibility.json", repro)
    if mismatches:
        raise ValueError("Rebuild differs from candidate: " + ", ".join(mismatches[:12]))
    reports = {"structure": structure, "browser": browser, "reproducibility": repro}
    if not state["no_changes"]:
        for name, value in reports.items():
            save(candidate / "verification" / ("automation_" + name + ".json"), value)
        report_page(candidate, state, reports)
    state.update(phase="verified", verified_artifact_sha256=structure["artifact_sha256"],
                 verified_graph_html_sha256=structure["graph_html_sha256"],
                 verified_files_sha256=final_inventory_sha256(candidate))
    save(root / "run.json", state)
    print(json.dumps({"status": "verified", "checks": {k: {"passed": r.get("passed"), "failed": r.get("failed")} for k, r in reports.items()},
                      "artifact_sha256": state["verified_artifact_sha256"]}, indent=2))


def archive_site(path, root, names, date):
    stamp = tuple(int(x) for x in date.split('-')) + (0, 0, 0)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in sorted(names):
            item = zipfile.ZipInfo(name, stamp)
            item.create_system = 3
            item.external_attr = 0o100644 << 16
            z.writestr(item, (root / name).read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def package_command(args):
    from atlas_validate import validate_site
    root, state = get_run(args.run)
    check_inputs(root, state)
    if state["phase"] not in ("verified", "packaged"):
        raise ValueError("Run check successfully before packaging")
    candidate = root / "candidate"
    if final_inventory_sha256(candidate) != state.get('verified_files_sha256'):
        raise ValueError("Candidate or verification files changed after checks; run check again")
    if state.get('no_changes') and files(candidate) != load(root / 'baseline_manifest.json'):
        raise ValueError("A no-change update must preserve every baseline file byte-for-byte")
    # Recompute artifact identity, including source scripts, before trusting saved QA.
    fresh = validate_site(candidate, baseline_payload=load(root / "baseline_payload.json"),
                          expected_changes={**load(root / "update_audit.json"), "baseline_html": str(root / "baseline/swe_knowledge_graph.html")},
                          book=load(candidate / "source/ndse2_book.json") if (candidate / "source/ndse2_book.json").is_file() else None)
    if fresh["failed"] or fresh["artifact_sha256"] != state["verified_artifact_sha256"]:
        raise ValueError("Candidate changed after verification; run check again")
    for name in ("structure", "reproducibility"):
        r = load(root / "reports" / (name + ".json"))
        if r.get("failed") or r.get("artifact_sha256") != state["verified_artifact_sha256"]:
            raise ValueError("Stale or failed verification report: " + name)
    browser = load(root / "reports/browser/browser_checks.json")
    if not browser.get("complete") or browser.get("failed") or browser.get("artifact_sha256") != state["verified_artifact_sha256"]:
        raise ValueError("Missing complete current browser evidence")
    current = files(candidate)
    if not state["no_changes"]:
        lines = ''.join(m["sha256"] + '  ' + p + '\n' for p, m in sorted(current.items()) if p != "SHA256SUMS.txt")
        (candidate / "SHA256SUMS.txt").write_text(lines, encoding="utf-8")
        current = files(candidate)
    baseline = load(root / "baseline_manifest.json")
    missing = sorted(set(baseline) - set(current))
    if missing:
        raise ValueError("Copy-only delta cannot remove files: " + ", ".join(missing))
    changed = sorted(p for p in baseline if baseline[p] != current[p])
    added = sorted(set(current) - set(baseline))
    unchanged = sorted(p for p in baseline if baseline[p] == current[p])
    out = (args.output or root / "output").resolve()
    if out.is_relative_to(candidate) or out.is_relative_to(root / "baseline"):
        raise ValueError("Output directory must be outside both site trees")
    out.mkdir(parents=True, exist_ok=True)
    suffix = state['date'].replace('-', '')
    prefix = 'Knowledge_Atlas_v' + state['release'].replace('.', '_')
    full_name = prefix + '_Complete_' + suffix + ('_UNCHANGED' if state['no_changes'] else '') + '.zip'
    delta_name = prefix + '_Delta_from_v' + str(state['baseline_release']).replace('.', '_') + '_' + suffix + ('_EMPTY' if state['no_changes'] else '') + '.zip'
    archive_site(out / full_name, candidate, current, state["date"])
    archive_site(out / delta_name, candidate, changed + added, state["date"])
    with tempfile.TemporaryDirectory(prefix="atlas-apply-delta-") as temp:
        patched, complete = Path(temp) / "patched", Path(temp) / "full"
        safe_extract(root / "baseline.zip", patched)
        safe_extract(out / delta_name, patched)
        safe_extract(out / full_name, complete)
        if files(patched) != current or files(complete) != current:
            raise ValueError("Applying the actual delta archive does not reconstruct the actual full archive")
    manifest = {"schema": "knowledge-atlas-release/1", "date": state["date"], "release": state["release"], "no_changes": state["no_changes"],
                "content_release": state.get('baseline_release') if state['no_changes'] else state['release'],
                "baseline": {"name": state["baseline_name"], "sha256": state["baseline_sha256"], "files": len(baseline)},
                "full": {"name": full_name, "sha256": sha(out / full_name), "size": (out / full_name).stat().st_size, "files": len(current)},
                "delta": {"name": delta_name, "sha256": sha(out / delta_name), "size": (out / delta_name).stat().st_size, "files": len(changed) + len(added)},
                "counts": {"overwrite": len(changed), "add": len(added), "unchanged": len(unchanged), "remove": 0},
                "verification": {"artifact_sha256": state["verified_artifact_sha256"], "baseline_plus_delta_equals_full": True,
                                 "delta_only_changed_or_added_files": True, "deployed": False},
                "files": [{"path": p, "action": "overwrite" if p in baseline else "add", "old_sha256": baseline.get(p, {}).get("sha256"), **current[p]} for p in sorted(changed + added)]}
    save(out / (prefix + '_Manifest_' + suffix + '.json'), manifest)
    text = f"ATLAS v{state['release']} — {state['date']}\n\nBASE PUBBLICATA: {state['baseline_name']}\nSHA-256: {state['baseline_sha256']}\n\nFULL: {full_name}\nDELTA: {delta_name}\n\n{len(changed)} file da sovrascrivere; {len(added)} file da aggiungere; nessuna eliminazione.\nCopia i contenuti estratti del delta nella cartella del sito che contiene index.html, conservando i percorsi.\nIl delta applicato a una copia della base ricostruisce esattamente il full.\nI pacchetti sono generati e verificati; la pubblicazione segue il flusso GitHub Pages esistente.\nUn nuovo full diventa la prossima base solo dopo la conferma della sua pubblicazione.\n"
    (out / (prefix + '_Istruzioni_' + suffix + '.txt')).write_text(text, encoding="utf-8")
    state.update(phase="packaged", output=str(out), full=manifest["full"], delta=manifest["delta"])
    save(root / "run.json", state)
    print(json.dumps({"status": "packaged", "output": str(out), "full": manifest["full"], "delta": manifest["delta"], "counts": manifest["counts"], "baseline_plus_delta_equals_full": True}, ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--version', action='version', version=VERSION)
    sub = p.add_subparsers(dest="command", required=True)
    init = sub.add_parser("prepare", help="Freeze the exact published full ZIP and create a reviewed-update template")
    init.add_argument("--baseline", type=Path, required=True)
    init.add_argument("--baseline-sha256")
    init.add_argument("--baseline-basis", default="Explicitly selected full ZIP supplied as the published baseline")
    init.add_argument("--run", type=Path, required=True)
    init.add_argument("--date", required=True)
    init.add_argument("--release", required=True)
    init.set_defaults(function=prepare)
    discover = sub.add_parser("discover", help="Collect public source metadata; leave editorial decisions pending")
    discover.add_argument("--run", type=Path, required=True)
    discover.add_argument("--sources", type=Path)
    discover.add_argument("--snapshots", type=Path)
    discover.add_argument("--since")
    discover.set_defaults(function=discover_command)
    build = sub.add_parser("build", help="Apply reviewed changes and regenerate the website offline")
    build.add_argument("--run", type=Path, required=True)
    build.add_argument("--review", type=Path)
    build.add_argument("--book", type=Path)
    build.set_defaults(function=build_command)
    for name in ("check", "finish"):
        cmd = sub.add_parser(name, help="Verify current bytes" if name == "check" else "Build, verify and package from the reviewed inputs")
        cmd.add_argument("--run", type=Path, required=True)
        cmd.add_argument("--browser", type=Path)
        cmd.add_argument("--playwright", type=Path)
        cmd.add_argument("--node")
        if name == "finish":
            cmd.add_argument("--review", type=Path)
            cmd.add_argument("--book", type=Path)
            cmd.add_argument("--output", type=Path)
            cmd.set_defaults(function=lambda a: (build_command(a), check_command(a), package_command(a)))
        else:
            cmd.set_defaults(function=check_command)
    package = sub.add_parser("package", help="Emit full/delta only from the exact successfully verified candidate")
    package.add_argument("--run", type=Path, required=True)
    package.add_argument("--output", type=Path)
    package.set_defaults(function=package_command)
    status = sub.add_parser("status", help="Show state without changing the site")
    status.add_argument("--run", type=Path, required=True)
    status.set_defaults(function=lambda a: print(json.dumps(get_run(a.run)[1], ensure_ascii=False, indent=2)))
    extract = sub.add_parser("extract-book", help="Extract a draft citation/section catalogue from a new bilingual manuscript")
    extract.add_argument("--run", type=Path, required=True)
    extract.add_argument("--book-root", type=Path, required=True)
    extract.add_argument("--metadata", type=Path, required=True)
    extract.add_argument("--output", type=Path)
    extract.set_defaults(function=extract_book_command)
    a = p.parse_args()
    try:
        a.function(a)
        return 0
    except (ValueError, FileNotFoundError, AssertionError, zipfile.BadZipFile, subprocess.TimeoutExpired) as e:
        print(json.dumps({"status": "blocked", "reason": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 2


def extract_book_command(args):
    from book_tools import extract_book
    root, state = get_run(args.run)
    previous = root / "baseline/source/ndse2_book.json"
    draft = extract_book(args.book_root, load(args.metadata), load(root / "baseline_payload.json"),
                         previous=load(previous) if previous.exists() else None, extracted_on=state["date"])
    out = args.output or root / "book_review.json"
    save(out, draft)
    print(json.dumps({"status": "book_draft_extracted", "path": str(out), "chapter_count": len(draft["chapters"]),
                      "chapters_requiring_editorial_review": [c["id"] for c in draft["chapters"] if c.get("editorial_review_required")]}, indent=2))


if __name__ == "__main__":
    sys.exit(main())
