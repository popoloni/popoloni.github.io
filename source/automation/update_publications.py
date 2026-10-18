#!/usr/bin/env python3
"""Apply a reviewed cover/Amazon navigation update to an exact Atlas baseline.

Run ``python -B source/update_publications.py`` from a complete website package.
The default input is source/book_publications.json. This offline, standard-library
adapter changes publication navigation only; it never reconciles a manuscript,
discovers articles, changes graph topology, publishes, or creates release ZIPs.
Both this file and its identical source/automation copy are runnable.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import html
import json
import re
import struct
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
SOURCE = HERE if (HERE / "site_config.json").is_file() else HERE.parent
ROOT = SOURCE.parent
sys.path.insert(0, str(SOURCE / "automation"))

from atlas_cli import run_builder
from atlas_graph import (export_raw, extract_payload, payload_sha256,
                         render_current_atlas, validate_payload, write_graphml)

KIND = "atlas_publications_update/1"
NAV_FIELDS = {"amazon_url", "amazon_asin", "amazon_language", "amazon_verification",
              "amazon_evidence_urls", "companion_url", "kindle_url", "cover_image",
              "cover_alt", "cover_width", "cover_height"}
COVER_FIELDS = {"cover_image", "cover_alt", "cover_width", "cover_height"}
REQUIRED_NAV = {"amazon_url", "amazon_asin", "amazon_language",
                "amazon_verification", "amazon_evidence_urls"}
EXPECTED_NODES = {**{f"V{i:02}": f"PUB:V11:V{i:02}" for i in range(1, 6)},
                  "V06": "PUB:NDSE2"}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local_path(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("A nonempty website-relative POSIX path is required")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or ":" in value:
        raise ValueError("Unsafe website-relative path: " + value)
    result = (ROOT / value).resolve()
    if not result.is_relative_to(ROOT):
        raise ValueError("Path escapes the website: " + value)
    return result


def public_url(value):
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("A nonempty public URL is required")
    u = urlsplit(value)
    if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password or u.port not in (None, 80, 443):
        raise ValueError("Invalid public URL: " + value)
    return u


def amazon_url(value, asin=None):
    u = public_url(value)
    match = re.fullmatch(r"/dp/([A-Z0-9]{10})", u.path)
    if u.scheme != "https" or u.netloc != "www.amazon.com" or u.query or u.fragment or not match:
        raise ValueError("Use a canonical https://www.amazon.com/dp/ASIN URL: " + value)
    if asin is not None and match.group(1) != asin:
        raise ValueError("Amazon URL and reviewed ASIN disagree: " + value)


def is_amazon(value):
    host = (urlsplit(value).hostname or "").lower()
    return host == "amazon.com" or host.startswith("www.amazon.") or host.startswith("amazon.")


def image_dimensions(path):
    """Inspect JPEG/PNG dimensions without modifying the supplied artwork."""
    data = path.read_bytes()
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24 and data[12:16] == b"IHDR":
        return struct.unpack(">II", data[16:24])
    if data[:2] == b"\xff\xd8":
        position = 2
        while position < len(data):
            if data[position] != 0xff:
                raise ValueError("Invalid JPEG marker in " + str(path))
            while position < len(data) and data[position] == 0xff:
                position += 1
            if position >= len(data):
                break
            marker = data[position]
            position += 1
            if marker in (0xd8, 0x01) or 0xd0 <= marker <= 0xd7:
                continue
            if marker in (0xd9, 0xda) or position + 2 > len(data):
                break
            length = int.from_bytes(data[position:position + 2], "big")
            if length < 2 or position + length > len(data):
                break
            if marker in {0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf}:
                if length < 7:
                    break
                height, width = struct.unpack(">HH", data[position + 3:position + 7])
                return width, height
            position += length
    raise ValueError("A valid local JPEG or PNG cover is required: " + str(path))


def validate_cover(record):
    if not COVER_FIELDS.issubset(record):
        raise ValueError("Cover image, alt text, width and height must be reviewed together")
    name = record["cover_image"]
    path = local_path(name)
    if not name.startswith("assets/books/") or not path.is_file():
        raise ValueError("Missing local assets/books/ cover: " + name)
    if not isinstance(record["cover_alt"], str) or not record["cover_alt"].strip():
        raise ValueError("A descriptive cover_alt is required")
    expected = (record["cover_width"], record["cover_height"])
    if any(type(v) is not int or v <= 0 for v in expected) or image_dimensions(path) != expected:
        raise ValueError("Reviewed cover dimensions disagree with the actual image: " + name)


def validate_manifest(review):
    if review.get("schema_version") != 1:
        raise ValueError("Publication metadata schema_version must be 1")
    for field in ("release", "baseline_release"):
        if not isinstance(review.get(field), str) or not re.fullmatch(r"\d+(?:\.\d+){1,2}", review[field]):
            raise ValueError(field + " must be a numeric release such as 13.2")
    date = review.get("reviewed_on") or review.get("date")
    if not isinstance(date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise ValueError("reviewed_on/date must be an ISO calendar date")
    dt.date.fromisoformat(date)
    if review.get("date", date) != date or review.get("reviewed_on", date) != date:
        raise ValueError("reviewed_on and date disagree")
    for field in ("baseline_package_sha256", "baseline_payload_sha256"):
        if not isinstance(review.get(field), str) or not re.fullmatch(r"[a-f0-9]{64}", review[field]):
            raise ValueError("Missing reviewed " + field)
    series = review.get("series", {})
    if not isinstance(series, dict) or not isinstance(series.get("title"), str) or not series["title"].strip():
        raise ValueError("A reviewed series title is required")
    amazon_url(series.get("amazon_url"))
    validate_cover(series)
    books = review.get("books")
    if not isinstance(books, list) or len(books) != len(EXPECTED_NODES):
        raise ValueError("Review exactly the six existing published books")
    by_volume = {}
    for book in books:
        if not isinstance(book, dict) or not REQUIRED_NAV.issubset(book):
            raise ValueError("Every book needs explicit Amazon navigation and verification metadata")
        extra = set(book) - NAV_FIELDS - {"volume_id", "node_id"}
        if extra:
            raise ValueError("Unsupported book metadata fields: " + ", ".join(sorted(extra)))
        volume = book.get("volume_id")
        if volume in by_volume or EXPECTED_NODES.get(volume) != book.get("node_id"):
            raise ValueError("Missing, duplicate or mismatched published book identity: " + str(volume))
        amazon_url(book["amazon_url"], book["amazon_asin"])
        if not isinstance(book["amazon_asin"], str) or not re.fullmatch(r"[A-Z0-9]{10}", book["amazon_asin"]):
            raise ValueError("Invalid reviewed ASIN: " + str(volume))
        if not isinstance(book["amazon_language"], str) or not book["amazon_language"].strip():
            raise ValueError("Amazon edition language must be explicit: " + volume)
        if not isinstance(book["amazon_verification"], (str, dict)) or not book["amazon_verification"]:
            raise ValueError("Amazon verification basis must be explicit: " + volume)
        evidence = book["amazon_evidence_urls"]
        if not isinstance(evidence, list) or not evidence:
            raise ValueError("At least one reviewed evidence URL is required: " + volume)
        for value in evidence:
            public_url(value)
        if book.get("companion_url"):
            public_url(book["companion_url"])
        if book.get("kindle_url"):
            amazon_url(book["kindle_url"])
        if COVER_FIELDS.intersection(book):
            if volume != "V06":
                raise ValueError("This review assigns individual cover artwork only to NDSE2/V06")
            validate_cover(book)
        elif volume == "V06":
            raise ValueError("The NDSE2 cover is required")
        by_volume[volume] = book
    if set(by_volume) != set(EXPECTED_NODES):
        raise ValueError("Publication review does not cover exactly V01 through V06")
    return date, by_volume


def snapshots(paths):
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(set(paths))}


def verify_files(expected):
    errors = [name for name, digest in expected.items() if not local_path(name).is_file() or sha(local_path(name)) != digest]
    if errors:
        raise ValueError("Audited update inputs/outputs have changed: " + ", ".join(errors))


def verify_graphml(path, node_count, edge_count, expected_sha256=None):
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as error:
        raise ValueError("GraphML export is incomplete or invalid: " + str(error)) from error
    namespace = "{http://graphml.graphdrawing.org/xmlns}"
    graph = root.find(namespace + "graph")
    if graph is None or len(graph.findall(namespace + "node")) != node_count or len(graph.findall(namespace + "edge")) != edge_count:
        raise ValueError("GraphML export node/edge counts differ from the reviewed payload")
    digest = sha(path)
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError("GraphML export differs from its prepared SHA-256")
    return digest


def write_verified_graphml(payload, target):
    """Commit only a complete, parsed, independently counted XML export."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix="." + target.name + "-", suffix=".tmp",
                                     dir=target.parent, delete=False) as handle:
        pending = Path(handle.name)
    try:
        write_graphml(export_raw(payload), pending)
        digest = verify_graphml(pending, len(payload["nodes"]), len(payload["edges"]))
        if target.exists():
            pending.chmod(target.stat().st_mode & 0o777)
        pending.replace(target)
        verify_graphml(target, len(payload["nodes"]), len(payload["edges"]), digest)
        return digest
    finally:
        pending.unlink(missing_ok=True)


def render_release_notes(path, review, audit, nodes):
    esc = lambda value: html.escape(str(value), quote=True)
    rows = "".join('<li><a href="' + esc(b["amazon_url"]) + '">' + esc(nodes[b["node_id"]]["label"]) + '</a></li>' for b in review["books"])
    text = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Atlas v{esc(review['release'])} · Book covers and links</title><link rel="stylesheet" href="assets/site.css"></head><body><main class="wrap" id="main">
<p class="eyebrow">Release {esc(review['release'])} · {esc(audit['reviewed_on'])}</p><h1>Book covers and Amazon.com links</h1>
<p>The Non-Deterministic series and published NDSE2 pages now include the author-supplied cover artwork and reviewed Amazon.com navigation. Each of the six published-book records links to its individual product; the series link remains identified separately.</p>
<p><a href="catalogues/books.html">Earlier Non-Deterministic books</a> · <a href="catalogues/ndse2.html">NDSE2 · Published second edition</a></p>
<h2>Individual books</h2><ul>{rows}</ul>
<h2>Preserved research and practices</h2><p>All {audit['topology_proof']['node_count']:,} node identities and all {audit['topology_proof']['edge_count']:,} keyed relationships remain unchanged. The practices, source records, literal citations, bibliography membership and published manuscript source version are retained.</p>
<p>Shopping links and cover images provide publication navigation. They do not change research evidence or imply independent validation.</p>
<p><a href="{esc(audit['publications_manifest'])}">Reviewed publication metadata</a> · <a href="{esc(audit['audit_path'])}">Update audit and original navigation</a> · <a href="verification/report.html">Verification report</a></p>
<p>Baseline package SHA-256: <code style="overflow-wrap:anywhere">{esc(review['baseline_package_sha256'])}</code>. Package comparison and deployment are separate steps.</p>
</main></body></html>'''
    path.write_text(text + "\n", encoding="utf-8")


def complete_build(audit_path, audit, config):
    run_builder(ROOT)
    # The renderer may produce pages and catalogue exports, but must not mutate
    # any prepared metadata/export byte. Never replace these hashes with later
    # values and thereby accept a truncated or otherwise changed graph export.
    verify_files(audit["metadata_output_integrity"])
    graphml = local_path(config["graph_graphml"])
    verify_graphml(graphml, audit["topology_proof"]["node_count"], audit["topology_proof"]["edge_count"],
                   audit["metadata_output_integrity"][graphml.relative_to(ROOT).as_posix()])
    delivered = local_path(config.get("graph_html", "swe_knowledge_graph.html"))
    if payload_sha256(extract_payload(delivered.read_text(encoding="utf-8"))) != audit["result_payload_sha256"]:
        raise ValueError("Static builder did not deliver the audited graph payload")
    audit["status"] = "complete"
    audit["delivered_graph_html_sha256"] = sha(delivered)
    audit["output_integrity"] = snapshots([local_path(p) for p in audit["metadata_output_integrity"]] + [delivered])
    save(audit_path, audit)
    return audit


def update(publications_path):
    publications_path = publications_path.resolve()
    if not publications_path.is_relative_to(ROOT) or not publications_path.is_file():
        raise ValueError("Publication metadata must be a local file inside this website")
    review = load(publications_path)
    date, publications = validate_manifest(review)
    suffix = "v" + review["release"].replace(".", "_") + "_" + date.replace("-", "")
    audit_relative = "data/updates/publications_review_" + suffix + ".json"
    audit_path = local_path(audit_relative)
    release_relative = "UPDATE_" + suffix + ".html"
    config_path = SOURCE / "site_config.json"
    config = load(config_path)
    template_path = local_path("source/" + config["atlas_source"])
    baseline_html = template_path.read_text(encoding="utf-8")
    old = extract_payload(baseline_html)
    current_digest = payload_sha256(old)
    manifest_digest = payload_sha256(review)
    book_path = local_path(config.get("book_json", "source/ndse2_book.json"))
    if audit_path.is_file():
        prior = load(audit_path)
        if prior.get("manifest_canonical_sha256") == manifest_digest and prior.get("result_payload_sha256") == current_digest:
            verify_files(prior.get("build_input_integrity", {}))
            verify_files(prior.get("metadata_output_integrity", {}))
            if prior.get("status") == "complete":
                verify_files(prior.get("output_integrity", {}))
                return {"status": "no_op", "release": review["release"], "audit": audit_relative,
                        "result_payload_sha256": current_digest}
            if prior.get("status") == "metadata_prepared":
                complete_build(audit_path, prior, config)
                return {"status": "completed_interrupted_build", "release": review["release"], "audit": audit_relative,
                        "result_payload_sha256": current_digest}
    if current_digest != review["baseline_payload_sha256"]:
        raise ValueError("Current payload differs from the reviewed baseline; restore the exact baseline or prepare a new review")
    if config.get("site_version") != review["baseline_release"]:
        raise ValueError("Current website release differs from baseline_release")
    current_books = {n["id"]: n for n in old["nodes"] if n["kind"] == "published_book"}
    if set(current_books) != set(EXPECTED_NODES.values()):
        raise ValueError("Baseline published-book node inventory differs from the six reviewed identities")
    before_book = load(book_path)
    if before_book.get("book", {}).get("id") != "V06" or before_book["book"].get("source_version") != "13.7.1":
        raise ValueError("This metadata adapter requires the retained NDSE2 V06 source edition 13.7.1")
    new, new_book, new_config = copy.deepcopy(old), copy.deepcopy(before_book), copy.deepcopy(config)
    by_id = {n["id"]: n for n in new["nodes"]}
    for volume, publication in publications.items():
        n = by_id[publication["node_id"]]
        a = n["attributes"]
        if a.get("volume_id") != volume:
            raise ValueError("Graph volume identity differs from reviewed metadata: " + volume)
        navigation = {key: copy.deepcopy(value) for key, value in publication.items() if key in NAV_FIELDS}
        old_companions = {value for value in (n.get("url"), a.get("url"), a.get("companion_url")) if value and not is_amazon(value)}
        if len(old_companions) > 1 or (navigation.get("companion_url") and old_companions and navigation["companion_url"] not in old_companions):
            raise ValueError("Companion navigation is ambiguous or would be lost: " + volume)
        if old_companions:
            navigation.setdefault("companion_url", next(iter(old_companions)))
        n["url"] = publication["amazon_url"]
        a.update(navigation, url=publication["amazon_url"], url_role="individual_book")
        if volume == "V06":
            new_book["book"].update(copy.deepcopy(navigation))
    node_ids = [n["id"] for n in old["nodes"]]
    excluded = set(EXPECTED_NODES.values())
    untouched_before = [n for n in old["nodes"] if n["id"] not in excluded]
    untouched_after = [n for n in new["nodes"] if n["id"] not in excluded]
    if [n["id"] for n in new["nodes"]] != node_ids or old["edges"] != new["edges"] or untouched_before != untouched_after:
        raise ValueError("Publication amendment changed graph identity, edges or unrelated nodes")
    for key in set(old) - {"nodes", "meta"}:
        if old[key] != new[key]:
            raise ValueError("Publication amendment changed a graph structure: " + key)
    manifest_relative = publications_path.relative_to(ROOT).as_posix()
    new_config.update(site_version=review["release"], graph_version=review["release"],
                      build_date=date, graph_snapshot=date, release_notes=release_relative,
                      book_series=copy.deepcopy(review["series"]), book_publications_json=manifest_relative,
                      publications_audit_json=audit_relative)
    new["meta"].update(edition="v" + review["release"], date=date)
    new["meta"].setdefault("graphAttributes", {}).update(
        portable_atlas_release="v" + review["release"] + "-static-" + date.replace("-", ""),
        portable_atlas_snapshot_date=date, atlas_update="v" + review["release"] + "_" + date.replace("-", ""),
        publication_navigation_release=review["release"], publication_navigation_manifest=manifest_relative)
    new["meta"]["publication_navigation"] = {
        "release": review["release"], "reviewed_on": date, "manifest": manifest_relative,
        "audit": audit_relative, "scope": "Local book covers and reviewed Amazon.com navigation; graph topology and manuscript citations unchanged"}
    graphml_path = local_path(new_config["graph_graphml"])
    raw_path = local_path(new_config["graph_json"])
    payload_name = new_config.get("payload_json") or new_config.get("atlas_payload_json") or new_config.get("graph_payload")
    if not payload_name:
        raise ValueError("The normalized payload export path must be explicit in site_config.json")
    payload_path = local_path(payload_name)
    if len({graphml_path, raw_path, payload_path, template_path, book_path, config_path, audit_path}) != 7:
        raise ValueError("Configured output paths collide")
    for path in (graphml_path, raw_path, payload_path, book_path):
        if not path.is_file():
            raise ValueError("Missing configured baseline export or metadata: " + str(path))
    new["meta"]["graphFile"] = graphml_path.name
    new["meta"].pop("graphSha256", None)
    validate_payload(new)
    build_inputs = [publications_path, SOURCE / "update_publications.py",
                    SOURCE / "automation/update_publications.py", SOURCE / "automation/atlas_graph.py",
                    SOURCE / "automation/atlas_cli.py", SOURCE / "build_site.py",
                    SOURCE / "build_ndse2_pages.py", SOURCE / "atlas_navigation_patch.js",
                    local_path(review["series"]["cover_image"]), local_path(publications["V06"]["cover_image"])]
    for path in build_inputs:
        if not path.is_file():
            raise ValueError("Missing rebuild input: " + str(path))
    audit = {
        "schema_version": 1, "kind": KIND, "status": "metadata_prepared", "release": review["release"],
        "baseline_release": review["baseline_release"], "reviewed_on": date,
        "baseline_package_sha256": review["baseline_package_sha256"],
        "baseline_package_hash_basis": "Reviewed package identifier; archive bytes are verified separately during release packaging",
        "baseline_payload_sha256": current_digest, "manifest_canonical_sha256": manifest_digest,
        "publications_manifest": manifest_relative, "audit_path": audit_relative,
        "book_source_version": before_book["book"]["source_version"],
        "book_nodes_before": [copy.deepcopy(n) for n in old["nodes"] if n["id"] in excluded],
        "ndse2_book_metadata_before": copy.deepcopy(before_book["book"]),
        "config_before": {k: copy.deepcopy(config[k]) for k in new_config if k in config and new_config[k] != config[k]},
        "config_added_fields": sorted(set(new_config) - set(config)),
        "payload_meta_before": copy.deepcopy(old["meta"]),
        "updated_book_ids": [n["id"] for n in new["nodes"] if n["id"] in excluded],
        "topology_proof": {"node_count": len(node_ids), "edge_count": len(old["edges"]),
            "relation_count": len(old["relations"]), "node_ids_in_original_order": True,
            "all_keyed_edges_identical": True, "all_graph_groups_identical": True,
            "all_non_book_nodes_identical": True, "node_ids_sha256": payload_sha256(node_ids),
            "edges_before_sha256": payload_sha256(old["edges"]), "edges_after_sha256": payload_sha256(new["edges"]),
            "non_book_nodes_before_sha256": payload_sha256(untouched_before),
            "non_book_nodes_after_sha256": payload_sha256(untouched_after)},
        "manuscript_proof": {"chapters_bibliography_citations_and_source_manifest_unchanged":
            {k: v for k, v in before_book.items() if k != "book"} == {k: v for k, v in new_book.items() if k != "book"}},
        "build_input_integrity": snapshots(build_inputs),
    }
    new["meta"]["graphSha256"] = write_verified_graphml(new, graphml_path)
    audit["result_payload_sha256"] = payload_sha256(new)
    save(raw_path, export_raw(new))
    save(payload_path, new)
    template_path.write_text(render_current_atlas(baseline_html, new, review["release"], date), encoding="utf-8")
    save(book_path, new_book)
    save(config_path, new_config)
    render_release_notes(local_path(release_relative), review, audit, by_id)
    audit["metadata_output_integrity"] = snapshots([graphml_path, raw_path, payload_path, template_path,
                                                    book_path, config_path, local_path(release_relative)])
    save(audit_path, audit)
    complete_build(audit_path, audit, new_config)
    return {"status": "updated", "release": review["release"], "audit": audit_relative,
            "result_payload_sha256": audit["result_payload_sha256"], "nodes": len(new["nodes"]),
            "edges": len(new["edges"]), "updated_books": len(publications), "topology_unchanged": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publications", type=Path, default=SOURCE / "book_publications.json",
                        help="Reviewed metadata JSON inside this website (default: source/book_publications.json)")
    args = parser.parse_args()
    try:
        result = update(args.publications)
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, "Publication update failed: " + str(error) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
