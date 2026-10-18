#!/usr/bin/env python3
"""Deterministic, offline update engine for the normalized Knowledge Atlas.

The caller owns retrieval, editorial review, site generation and release packaging.
This module accepts reviewed data, never retrieves articles, and never guesses a
literal book citation. Every existing node ID/index and keyed edge is preserved.

Public API: apply_update(payload, review, book=None), extract_payload(html),
payload_sha256(payload), export_raw(payload), write_graphml(raw, path),
render_current_atlas(html, payload, version, date).
"""
from __future__ import annotations

import collections
import copy
import datetime as dt
import hashlib
import html as html_module
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SCHEMA_VERSION = 1
GRAPH_NS = "http://graphml.graphdrawing.org/xmlns"
CITATION_RELATIONS = ("NDSE2_CHAPTER_CITES", "NDSE2_SECTION_CITES", "NDSE2_DOCUMENT_CITES")
SOURCE_COLLECTIONS = {"W", "O", "P", "F", "B"}
EDITABLE_FIELDS = {"label", "summary", "limitation", "url", "authors", "year", "streams", "topics", "mapped", "volumes"}
RESERVED_ATTRIBUTES = {"id", "collection", "kind", "actual", "printed", "source_version", "edition_id",
                       "new_manuscript_citation", "book_citation_status", "manuscript_citation_status",
                       "manuscript_citation_basis"}
PAYLOAD_RE = re.compile(r'(<script\s+id="graph-data"\s+type="application/json">)(.*?)(</script>)', re.S)


class UpdateError(ValueError):
    """The review or baseline is incompatible; no output has been committed."""


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def payload_sha256(payload):
    """SHA-256 of UTF-8 canonical JSON; this is distinct from the ZIP hash."""
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def extract_payload(html):
    match = PAYLOAD_RE.search(html)
    if not match:
        raise UpdateError('Missing normalized <script id="graph-data"> payload')
    payload = json.loads(match.group(2))
    validate_payload(payload)
    return payload


def canonical_url(value):
    """Conservative local URL identity; network redirects need editorial review."""
    if not value:
        return ""
    parts = urlsplit(value)
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise UpdateError(f"An absolute public HTTP(S) URL is required: {value!r}")
    ignored = {"fbclid", "gclid", "mc_cid", "mc_eid", "r", "triedRedirect", "isFreemail"}
    query = sorted((key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True)
                   if not key.lower().startswith("utm_") and key not in ignored)
    host = parts.hostname.lower()
    if parts.port and parts.port not in {80, 443}:
        host += ":" + str(parts.port)
    return urlunsplit(("https", host, parts.path.rstrip("/") or "/", urlencode(query), ""))


def _check_date(value, field):
    try:
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError()
        dt.date.fromisoformat(value)
    except ValueError as exc:
        raise UpdateError(f"{field} must be an ISO calendar date (YYYY-MM-DD)") from exc


def _node(nid, label, kind, collection=None, category=None, **values):
    result = dict(id=nid, label=label, kind=kind, collection=collection, category=category,
                  streams=[], actual=[], mapped=[], printed=False, summary="", limitation="",
                  url="", authors="", year="", topics=[], volumes=[], attributes={})
    result.update(copy.deepcopy(values))
    return result


def validate_payload(payload):
    if not isinstance(payload, dict) or not all(key in payload for key in ("meta", "nodes", "edges", "relations", "edgeFamilies", "nodeGroups")):
        raise UpdateError("A complete normalized Atlas payload is required")
    ids = [node.get("id") for node in payload["nodes"]]
    if any(not isinstance(nid, str) or not nid for nid in ids) or len(set(ids)) != len(ids):
        raise UpdateError("Baseline node IDs are missing or duplicated")
    for node in payload["nodes"]:
        for field in ("label", "kind", "summary", "limitation", "url", "authors", "year"):
            if not isinstance(node.get(field), str):
                raise UpdateError(f"Normalized node {node['id']}.{field} must be a string")
        for field in ("streams", "actual", "mapped", "topics", "volumes"):
            if not isinstance(node.get(field), list) or any(not isinstance(v, str) for v in node[field]):
                raise UpdateError(f"Normalized node {node['id']}.{field} must be a list of IDs")
        if type(node.get("printed")) is not bool or not isinstance(node.get("attributes"), dict):
            raise UpdateError(f"Invalid printed/attributes fields for {node['id']}")
    edge_ids, keyed = set(), set()
    for edge in payload["edges"]:
        if edge.get("id") in edge_ids or not isinstance(edge.get("id"), str):
            raise UpdateError("Baseline edge IDs are missing or duplicated")
        edge_ids.add(edge["id"])
        for end in ("source", "target"):
            if type(edge.get(end)) is not int or not 0 <= edge[end] < len(ids):
                raise UpdateError(f"Invalid edge endpoint in {edge['id']}")
        key = (edge["source"], edge["target"], _canonical(edge.get("key")))
        if key in keyed:
            raise UpdateError(f"Duplicate baseline keyed edge: {edge['id']}")
        keyed.add(key)
        if not edge.get("relation") or not edge.get("family") or not isinstance(edge.get("attributes"), dict):
            raise UpdateError(f"Incomplete edge: {edge['id']}")
    _canonical(payload)  # Reject non-finite values and unserializable objects.


def _current_book_version(payload):
    ga = payload["meta"].get("graphAttributes", {})
    edition_id = ga.get("current_book_edition", "")
    node = next((n for n in payload["nodes"] if n["id"] == edition_id), {})
    return node.get("attributes", {}).get("source_version", "")


def _audit(payload, baseline, *, digest, added_nodes=(), added_edges=(), changes=(), assigned_ids=(), book_audit=None, no_op=False):
    version = _current_book_version(payload)
    edition = payload["meta"].get("graphAttributes", {}).get("current_book_edition", "")
    current_edges = [e["id"] for e in payload["edges"] if e["relation"] in CITATION_RELATIONS
                     and e["attributes"].get("source_version") == version
                     and e["attributes"].get("edition_id", edition) == edition]
    return {
        "schema_version": SCHEMA_VERSION, "review_digest": digest, "no_op": no_op,
        "baseline_payload_sha256": payload_sha256(baseline), "result_payload_sha256": payload_sha256(payload),
        "baseline_nodes": len(baseline["nodes"]), "baseline_edges": len(baseline["edges"]),
        "nodes": len(payload["nodes"]), "edges": len(payload["edges"]), "relation_types": len(payload["relations"]),
        "source_counts": dict(sorted(collections.Counter(n["collection"] for n in payload["nodes"] if n.get("collection")).items())),
        "added_nodes": list(added_nodes), "added_edges": list(added_edges), "assigned_ids": list(assigned_ids),
        "new_source_ids": [nid for nid in added_nodes if next(n for n in payload["nodes"] if n["id"] == nid).get("collection") in {"O", "P", "F"}],
        "changed_source_ids": sorted({c["id"] for c in changes if next(n for n in payload["nodes"] if n["id"] == c["id"]).get("collection") in {"O", "P", "F"}}),
        "changes": list(changes), "all_original_node_ids_retained": [n["id"] for n in payload["nodes"][:len(baseline["nodes"])]] == [n["id"] for n in baseline["nodes"]],
        "all_original_edges_identical": payload["edges"][:len(baseline["edges"])] == baseline["edges"],
        "current_book_version": version, "current_book_edition": edition,
        "current_citation_relations": list(CITATION_RELATIONS), "current_citation_edge_ids": current_edges,
        "book": book_audit or {"status": "unchanged"},
    }


def apply_update(baseline_payload, review, book=None):
    """Apply a fully reviewed overlay without touching the input objects.

    review keys: schema_version=1, date, release, baseline_payload_sha256,
    baseline_sha256 (external ZIP; validated by the caller), additions, revisions,
    edges, notes, book_policy ('unchanged' or 'reconcile'). Missing article IDs
    receive the next O/P/F number. Optional ``ref`` values are used as ``$ref``
    endpoints in review edges. A revision needs a nonempty ``reason``.

    The complete review+book digest is recorded; replaying it is a no-op, including
    replay on its resulting payload. Omitted ``book`` retains actual/printed.
    """
    validate_payload(baseline_payload)
    if not isinstance(review, dict) or review.get("schema_version", 1) != SCHEMA_VERSION:
        raise UpdateError("Unsupported review schema_version")
    _check_date(review.get("date"), "review.date")
    release = review.get("release", "")
    if not isinstance(release, str) or not re.fullmatch(r"v?\d+(?:\.\d+){1,3}", release):
        raise UpdateError("review.release must be a numeric release, for example 13.1 or v13.1")
    digest = payload_sha256({"review": review, "book": book})
    ledger = baseline_payload["meta"].get("automation_updates", [])
    if any(entry.get("review_digest") == digest for entry in ledger):
        out = copy.deepcopy(baseline_payload)
        return out, _audit(out, baseline_payload, digest=digest, no_op=True)
    expected = review.get("baseline_payload_sha256")
    if expected and expected != payload_sha256(baseline_payload):
        raise UpdateError("Baseline payload hash mismatch; regenerate the review against the exact current package")
    policy = review.get("book_policy", "unchanged" if book is None else "reconcile")
    if policy not in {"unchanged", "reconcile"} or (book is not None and policy != "reconcile") or (book is None and policy == "reconcile"):
        raise UpdateError("book_policy must agree with the explicitly supplied final-book metadata")
    D = copy.deepcopy(baseline_payload)
    by = {n["id"]: n for n in D["nodes"]}
    indexes = {n["id"]: i for i, n in enumerate(D["nodes"])}
    aliases, assigned_ids, added_nodes, added_edges, changes = {}, [], [], [], []
    families = {r["id"]: r["family"] for r in D["relations"]}
    valid_families = {g["id"] for g in D["edgeFamilies"]}
    category_ids = {g["id"] for g in D["nodeGroups"]}
    keyed = {(e["source"], e["target"], _canonical(e["key"])) for e in D["edges"]}
    all_edge_ids = {e["id"] for e in D["edges"]}

    def change(nid, field, value, *, attribute=False):
        obj = by[nid]["attributes"] if attribute else by[nid]
        if obj.get(field) == value:
            return
        history = by[nid]["attributes"].setdefault("atlas_revision_history", [])
        history.append({"release": release, "date": review["date"], "field": ("attributes." if attribute else "") + field,
                        "previous_present": field in obj, "previous": copy.deepcopy(obj.get(field))})
        obj[field] = copy.deepcopy(value)
        changes.append({"id": nid, "field": ("attributes." if attribute else "") + field})

    def add_node(node):
        nid = node["id"]
        if nid in by:
            raise UpdateError(f"Node ID already exists: {nid}")
        if node.get("category") and node["category"] not in category_ids:
            raise UpdateError(f"Unsupported context category for {nid}: {node['category']}")
        indexes[nid] = len(D["nodes"])
        D["nodes"].append(node)
        by[nid] = node
        added_nodes.append(nid)

    def add_edge(source, target, relation, family, attrs=None, key=None):
        source, target = aliases.get(source, source), aliases.get(target, target)
        if source not in by or target not in by:
            raise UpdateError(f"Unknown edge endpoint: {source} -> {target}")
        if family not in valid_families:
            raise UpdateError(f"Unknown relationship family: {family}")
        if relation in families and families[relation] != family:
            raise UpdateError(f"The existing relationship family cannot change: {relation}")
        families[relation] = family
        ordinal = len(added_edges)
        eid = f"auto_{digest[:16]}_{ordinal:05}"
        key = key if key is not None else f"AUTO:{digest[:16]}:{ordinal:05}:{relation}"
        identity = (indexes[source], indexes[target], _canonical(key))
        if identity in keyed or eid in all_edge_ids:
            raise UpdateError(f"Duplicate keyed edge or generated ID: {source} -> {target} ({relation})")
        attrs = copy.deepcopy(attrs or {})
        if attrs.get("relation", relation) != relation:
            raise UpdateError("Edge attributes.relation conflicts with its normalized relation")
        attrs.update(relation=relation)
        attrs.setdefault("provenance", f"Reviewed Atlas update {review['date']}")
        D["edges"].append(dict(id=eid, source=indexes[source], target=indexes[target], key=key,
                              relation=relation, family=family, attributes=attrs))
        keyed.add(identity)
        all_edge_ids.add(eid)
        added_edges.append(eid)

    def check_article_url(nid, value):
        identity = canonical_url(value)
        if not identity:
            raise UpdateError(f"Article URL missing: {nid}")
        for n in D["nodes"]:
            if n["id"] != nid and n.get("collection") in {"W", "O", "P", "F"} and n.get("url"):
                if canonical_url(n["url"]) == identity:
                    raise UpdateError(f"Duplicate article URL: {nid} duplicates {n['id']}; use an explicit revision")

    for position, supplied in enumerate(review.get("additions", [])):
        n = copy.deepcopy(supplied)
        collection = n.get("collection")
        if collection not in {"O", "P", "F", None}:
            raise UpdateError("Automatic editorial additions support O/P/F and context nodes only; W/B/N changes require a separately reviewed migration")
        if n.get("actual") or n.get("printed"):
            raise UpdateError("New articles cannot claim actual citations or bibliography membership through a review; supply final-book metadata")
        nid, ref = n.pop("id", None), n.pop("ref", None)
        if not nid:
            if not collection:
                raise UpdateError("A context node needs an explicit stable ID")
            maximum = max((int(key[1:]) for key in by if re.fullmatch(collection + r"\d{3,}", key)), default=0)
            nid = f"{collection}{maximum + 1:03}"
        if collection and not re.fullmatch(collection + r"\d{3,}", nid):
            raise UpdateError(f"ID does not match collection {collection}: {nid}")
        if nid in by:
            raise UpdateError(f"Existing IDs cannot be reused for additions: {nid}")
        if not isinstance(n.get("label"), str) or not n["label"].strip() or not n.get("kind"):
            raise UpdateError(f"Node label and kind are required: {nid}")
        values = _node(nid, n.pop("label"), n.pop("kind"), **n)
        if not isinstance(values["attributes"], dict):
            raise UpdateError(f"attributes must be an object: {nid}")
        if collection:
            if not values["authors"] or not values["summary"] or not values["limitation"]:
                raise UpdateError(f"Article author, concise summary and evidence limitation are required: {nid}")
            check_article_url(nid, values["url"])
            for key in ("publication_date", "updated_date", "latest_activity_date"):
                if values["attributes"].get(key):
                    _check_date(values["attributes"][key], f"{nid}.{key}")
            values["attributes"].setdefault("manuscript_citation_status", "COMPANION_READING_PENDING_OR_ABSENT_FROM_CURRENT_BOOK")
        values["attributes"].update(atlas_added_release=release, atlas_added_date=review["date"])
        add_node(values)
        if ref:
            alias = "$" + str(ref).lstrip("$")
            if alias in aliases or alias in by:
                raise UpdateError(f"Duplicate addition ref: {ref}")
            aliases[alias] = nid
        assigned_ids.append({"position": position, "ref": ref, "id": nid})

    for revision in review.get("revisions", []):
        nid = revision.get("id")
        if nid not in by or nid in added_nodes:
            raise UpdateError(f"Revision requires an existing baseline ID: {nid}")
        if not isinstance(revision.get("reason"), str) or not revision["reason"].strip():
            raise UpdateError(f"Revision requires a reason: {nid}")
        if by[nid].get("collection") not in {"O", "P", "F"}:
            raise UpdateError(f"Editorial revision is restricted to O/P/F records: {nid}")
        patch = revision.get("patch", {})
        if set(patch) - EDITABLE_FIELDS:
            raise UpdateError(f"Unsupported revision fields for {nid}: {sorted(set(patch) - EDITABLE_FIELDS)}")
        for field, value in patch.items():
            if field == "url":
                check_article_url(nid, value)
            change(nid, field, value)
        for field, value in revision.get("attributes_patch", {}).items():
            if field in RESERVED_ATTRIBUTES or field.startswith(("ndse2_", "atlas_revision_history")):
                raise UpdateError(f"Protected book/identity attribute cannot be revised editorially: {field}")
            if field in ("publication_date", "updated_date", "latest_activity_date"):
                _check_date(value, f"{nid}.{field}")
            change(nid, field, value, attribute=True)
        by[nid]["attributes"].setdefault("atlas_editorial_revisions", []).append({
            "release": release, "date": review["date"], "reason": revision["reason"]})

    for n in D["nodes"]:
        if n["id"] not in added_nodes and not any(c["id"] == n["id"] for c in changes):
            continue
        for field, group in (("streams", "themes"), ("topics", "topics"), ("mapped", "chapters"), ("volumes", "volumes")):
            known = {g["id"] for g in D.get(group, [])}
            if not isinstance(n[field], list) or len(set(n[field])) != len(n[field]) or not set(n[field]).issubset(known):
                raise UpdateError(f"Invalid or duplicate {field} references: {n['id']}")

    for supplied in review.get("edges", []):
        relation = supplied.get("relation", "")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_:. -]*", relation):
            raise UpdateError("An explicit relationship name is required")
        if supplied.get("family") == "actual" or relation in CITATION_RELATIONS:
            raise UpdateError("Actual-use edges must come from final-book reconciliation, not editorial review")
        add_edge(supplied.get("source"), supplied.get("target"), relation, supplied.get("family"), supplied.get("attributes"), supplied.get("key"))

    book_audit = _reconcile_book(D, book, by, change, add_node, add_edge, review) if book is not None else {"status": "unchanged"}
    counts = collections.Counter(e["relation"] for e in D["edges"])
    old_relations = {r["id"] for r in D["relations"]}
    D["relations"] = [{**r, "count": counts[r["id"]]} for r in D["relations"]] + [
        {"id": rid, "label": rid.replace("_", " ").title(), "family": families[rid], "count": counts[rid]}
        for rid in sorted(set(counts) - old_relations)]
    family_counts = collections.Counter(e["family"] for e in D["edges"])
    D["edgeFamilies"] = [{**g, "count": family_counts[g["id"]]} for g in D["edgeFamilies"]]
    node_counts = collections.Counter(n.get("category") for n in D["nodes"] if not n.get("collection"))
    D["nodeGroups"] = [{**g, "count": node_counts[g["id"]]} for g in D["nodeGroups"]]
    source_counts = collections.Counter(n.get("collection") for n in D["nodes"])
    ga = D["meta"].setdefault("graphAttributes", {})
    D["meta"].setdefault("atlas_metadata_history", []).append({"release_before_update": baseline_payload["meta"].get("edition"),
        "date_before_update": baseline_payload["meta"].get("date"), "notes": copy.deepcopy(baseline_payload["meta"].get("notes", [])),
        "fowler_attribution": copy.deepcopy(baseline_payload["meta"].get("fowler_attribution", {})),
        "graphAttributes": {k: copy.deepcopy(v) for k, v in baseline_payload["meta"].get("graphAttributes", {}).items() if not k.startswith("historical_")}})
    ga.update(portable_atlas_release=release, portable_atlas_snapshot_date=review["date"],
              atlas_update=release + "_" + review["date"].replace("-", ""), osmani_articles=source_counts["O"],
              fowler_articles=source_counts["F"], orosz_articles=source_counts["P"],
              portable_atlas_basis="Exact supplied website package plus explicitly reviewed incremental records; final-book citations change only when final source metadata is supplied",
              orosz_scope="Blog plus newsletter Deepdives; The Pulse title-prefix and podcast exclusions retained; individual review scopes are recorded on each source",
              orosz_evidence_note="Access and inspected-text scope are recorded per article; inherited restricted records remain provisional; no empirical replication is asserted",
              fowler_scope_update=f"{source_counts['F']} records from martinfowler.com; series membership versus adjacent-site scope and actual bylines remain source-specific",
              graphml_key_encoding="atlas_original_key_json retains each original keyed-edge identity")
    if review.get("source_review_path"):
        ga["article_update_source"] = review["source_review_path"]
    if D["meta"].get("fowler_attribution"):
        fowler = D["meta"]["fowler_attribution"]
        fowler["source_count"], fowler["snapshot_date"] = source_counts["F"], review["date"]
        fowler["scope"] = "Historical Exploring Generative AI records and explicitly reviewed adjacent-site additions; article-level scope retained; no unqualified site-wide completeness claim"
        credited = set()
        for n in D["nodes"]:
            if n.get("collection") == "F" and n.get("authors"):
                try:
                    authors = json.loads(n["attributes"].get("authors_json", "null"))
                except (TypeError, json.JSONDecodeError):
                    authors = None
                credited.update(authors if isinstance(authors, list) and all(isinstance(v, str) for v in authors) else [n["authors"]])
        fowler["authors"] = sorted(set(fowler.get("authors", [])) | credited)
    D["meta"].update(edition=release + " · Reviewed Atlas update", date=review["date"], nodeCount=len(D["nodes"]),
                     edgeCount=len(D["edges"]), relationCount=len(D["relations"]))
    D["meta"].pop("graphSha256", None)  # The caller sets it after writing the current GraphML.
    D["meta"]["notes"] = [
        f"Release {release}, reviewed through {review['date']}; the exact supplied package is the immutable baseline.",
        f"All {len(baseline_payload['nodes']):,} baseline node IDs and {len(baseline_payload['edges']):,} keyed edges remain in their original order.",
        "Bibliography membership, literal chapter citations, index links and editorial mappings remain distinct.",
        "Historical metadata and relationships remain available; current citation membership names its source edition.",
        "Provenance, publication and literal source use do not establish empirical validation or endorsement.",
        "The baseline opening preset and original stream taxonomy remain unchanged.",
    ] + list(review.get("notes", []))
    D["meta"].setdefault("automation_updates", []).append({"review_digest": digest, "release": release, "date": review["date"],
        "baseline_payload_sha256": payload_sha256(baseline_payload), "baseline_zip_sha256": review.get("baseline_sha256"),
        "book_sha256": payload_sha256(book) if book is not None else None})
    validate_payload(D)
    audit = _audit(D, baseline_payload, digest=digest, added_nodes=added_nodes, added_edges=added_edges, changes=changes,
                   assigned_ids=assigned_ids, book_audit=book_audit)
    if not audit["all_original_node_ids_retained"] or not audit["all_original_edges_identical"]:
        raise UpdateError("Internal error: baseline identity preservation failed")
    return D, audit


def _book_signature(book):
    return [(c["id"], c["hub_id"], c["number"], c["title"],
             [(s["id"], s.get("level"), s.get("number"), s["title"], s.get("label"), bool(s.get("starred"))) for s in c.get("sections", [])])
            for c in book["chapters"]]


def _reconcile_book(D, book, by, change, add_node, add_edge, review):
    """Reconcile explicit final metadata; structure changes require migration.

    A compatible new source version keeps stable current chapter/section records,
    stores prior display values, and appends an edition-qualified citation layer.
    Historical edges always retain their old version and original attributes.
    """
    if not isinstance(book, dict) or not book.get("chapters") or not isinstance(book.get("book"), dict):
        raise UpdateError("Final book extraction must contain book, chapters and bibliography")
    version = book["book"].get("source_version")
    if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", version):
        raise UpdateError("Book source_version is required and must be a safe edition identifier")
    current_version = _current_book_version(D)
    if not current_version:
        raise UpdateError("No current NDSE2 edition exists; initial book installation requires a reviewed migration")
    signature = _book_signature(book)
    existing_chapters = sorted((n for n in D["nodes"] if n.get("collection") == "N"), key=lambda n: n["attributes"]["chapter_number"])
    if [c[0] for c in signature] != [n["id"] for n in existing_chapters]:
        raise UpdateError("Book chapter IDs/order changed; automatic reconciliation is blocked until a reviewed structural migration exists")
    for ch, expected in zip(book["chapters"], existing_chapters):
        if (ch["hub_id"], ch["number"], ch["title"]) != (expected["attributes"]["chapter_hub"], expected["attributes"]["chapter_number"], expected["label"]):
            raise UpdateError(f"Book chapter identity/title changed ({ch['id']}); supply a reviewed structural migration")
        current_sections = [n for n in D["nodes"] if n["kind"] == "published_book_section" and n["attributes"].get("chapter_id") == ch["id"]]
        current_section_sig = [(n["id"], n["attributes"].get("level"), n["attributes"].get("number"), n["label"], n["attributes"].get("label"), bool(n["attributes"].get("starred"))) for n in current_sections]
        if next(s for s in signature if s[0] == ch["id"])[4] != current_section_sig:
            raise UpdateError(f"Book section structure/identity changed ({ch['id']}); supply a reviewed structural migration")
        if [s["id"] for s in ch.get("sections_it", [])] != [s["id"] for s in ch.get("sections", [])]:
            raise UpdateError(f"EN/ITA section identities disagree: {ch['id']}")
    bibliography = book.get("bibliography", {})
    if not all(isinstance(bibliography.get(lang), dict) and isinstance(bibliography[lang].get("entries"), list) for lang in ("EN", "ITA")):
        raise UpdateError("Both EN and ITA final loaded bibliography entries are required")
    bib_sets = {lang: {e.get("source_id") for e in bibliography[lang]["entries"]} for lang in ("EN", "ITA")}
    if None in bib_sets["EN"] or None in bib_sets["ITA"] or bib_sets["EN"] != bib_sets["ITA"]:
        raise UpdateError("Unresolved or divergent EN/ITA bibliography identities")
    bib_ids = bib_sets["EN"]
    if bib_ids - set(by):
        raise UpdateError(f"Book bibliography contains unresolved graph IDs: {sorted(bib_ids - set(by))}")
    units = [u for u in book.get("nonchapter_units", []) if "INDEX" not in u.get("id", "").upper() and u.get("kind") not in {"source_identifier_index", "index"}]
    existing_units = {n["id"] for n in D["nodes"] if n["kind"] == "published_book_document"}
    if {u["id"] for u in units} != existing_units:
        raise UpdateError("Book nonchapter document identities changed; supply a reviewed structural migration")
    occurrences, chapter_map, edge_specs = [], collections.defaultdict(set), []
    for unit in list(book["chapters"]) + units:
        uid, hub = unit["id"], unit.get("hub_id") if unit in book["chapters"] else None
        if uid not in by:
            raise UpdateError(f"Book document identity changed ({uid}); supply a reviewed structural migration")
        if unit.get("title") != by[uid]["label"]:
            raise UpdateError(f"Book document title/identity changed ({uid}); supply a reviewed structural migration")
        relation = "NDSE2_CHAPTER_CITES" if hub else "NDSE2_DOCUMENT_CITES"
        for lang, field in (("EN", "citations"), ("ITA", "citations_it")):
            grouped, sections = collections.defaultdict(list), collections.defaultdict(list)
            declared_ids_field = "source_ids" if lang == "EN" else "source_ids_it"
            if declared_ids_field in unit and set(unit[declared_ids_field]) != {c.get("source_id") for c in unit.get(field, [])}:
                raise UpdateError(f"Declared source IDs disagree with literal citation records: {uid}, {lang}")
            for cit in unit.get(field, []):
                sid = cit.get("source_id")
                if sid not in by or sid not in bib_ids:
                    raise UpdateError(f"Unresolved or unloaded literal citation: {uid} -> {sid}")
                if cit.get("macro") in {"nocite", "workref", "ref", "pageref"}:
                    raise UpdateError(f"A non-citation macro leaked into body citations: {uid}")
                if not cit.get("file") or type(cit.get("line")) is not int or not re.fullmatch(r"[a-fA-F0-9]{64}", cit.get("sha256", "")):
                    raise UpdateError(f"Literal citation lacks file/line/SHA-256 provenance: {uid} -> {sid}")
                grouped[sid].append(cit)
                occurrences.append({**cit, "language": lang, "owner_id": uid})
                if hub:
                    chapter_map[sid].add(hub)
                    section = cit.get("section_id")
                    if section and section not in by:
                        raise UpdateError(f"Unknown citation section: {section}")
                    if section:
                        sections[(section, sid)].append(cit)
            for sid, citations in sorted(grouped.items()):
                edge_specs.append((uid, sid, relation, lang, hub or "", citations))
            for (section, sid), citations in sorted(sections.items()):
                edge_specs.append((section, sid, "NDSE2_SECTION_CITES", lang, hub, citations))
    # Same-version sources must agree with the existing layer, not silently append
    # a second layer under the same source-version label.
    wanted = collections.Counter((source, target, rel, lang, len(cites)) for source, target, rel, lang, hub, cites in edge_specs)
    existing = collections.Counter((D["nodes"][e["source"]]["id"], D["nodes"][e["target"]]["id"], e["relation"], e["attributes"].get("language"), e["attributes"].get("citation_count"))
        for e in D["edges"] if e["relation"] in CITATION_RELATIONS and e["attributes"].get("source_version") == current_version)
    displayed_bib = {n["id"] for n in D["nodes"] if n.get("printed") and
                     (n.get("collection") in {"W", "O", "P", "F"} or n["id"].startswith(("PUB:V11:", "BIB:")))}
    same_sources = all(by[c["id"]]["attributes"].get("source_sha256") == c.get("root_sha256")
                       and by[c["id"]]["attributes"].get("source_sha256_it") == c.get("root_sha256_it") for c in book["chapters"])
    def locator_signature(citations):
        fields = ("file", "line", "macro", "bibkey", "sha256", "section_id")
        return sorted(_canonical({k: citation.get(k) for k in fields}) for citation in citations)
    wanted_locations = {(source, target, relation, lang): locator_signature(cites) for source, target, relation, lang, hub, cites in edge_specs}
    existing_locations = {(D["nodes"][e["source"]]["id"], D["nodes"][e["target"]]["id"], e["relation"], e["attributes"].get("language")):
                          locator_signature(json.loads(e["attributes"].get("locators_json", "[]")))
        for e in D["edges"] if e["relation"] in CITATION_RELATIONS and e["attributes"].get("source_version") == current_version}
    same_metadata = all(by[c["id"]].get("summary", "") == c.get("summary", "") and
                        by[c["id"]]["attributes"].get("title_it", "") == c.get("title_it", "") and
                        json.loads(by[c["id"]]["attributes"].get("learning_goals_json", "[]")) == c.get("learning_goals", [])
                        for c in book["chapters"])
    if version == current_version:
        if wanted != existing or displayed_bib != bib_ids or not same_sources or wanted_locations != existing_locations or not same_metadata:
            raise UpdateError("The book changed without a new source_version; bump its version or resolve the extraction mismatch before reconciliation")
        return {"status": "unchanged_verified", "source_version": version, "chapters": len(book["chapters"]),
                "sections": sum(len(c.get("sections", [])) for c in book["chapters"]), "literal_occurrences": len(occurrences),
                "book_sha256": payload_sha256(book), "new_citation_layer": False}
    edition_id = "EDITION:NDSE2:" + version
    if edition_id in by:
        raise UpdateError(f"This book source edition already exists historically: {edition_id}; an explicit migration is required to make it current again")
    add_node(_node(edition_id, "NDSE2 · Source edition " + version, "edition", category="teaching", volumes=["V06"],
                   authors=book["book"].get("author", "Enrico Papalini"), year=str(book["book"].get("publication_year", "")),
                   attributes={"source_version": version, "chapter_count": len(book["chapters"]),
                               "publication_status": book["book"].get("publication_status", ""),
                               "book_metadata_sha256": payload_sha256(book), "previous_edition_id": "EDITION:NDSE2:" + current_version}))
    add_edge(edition_id, "PUB:NDSE2", "NDSE2_EDITION_OF", "provenance", {"source_version": version})
    for source, target, relation, lang, hub, citations in edge_specs:
        add_edge(source, target, relation, "actual", {"language": lang, "chapter_hub": hub, "literal_citation": True,
                 "citation_count": len(citations), "source_version": version, "edition_id": edition_id,
                 "locators_json": json.dumps(citations, ensure_ascii=False, sort_keys=True),
                 "evidence_scope": "Literal manuscript use; not validation of source claims"})
    for ch in book["chapters"]:
        cid = ch["id"]
        change(cid, "summary", ch.get("summary", ""))
        for field, value in {"edition_id": edition_id, "source_version": version, "summary": ch.get("summary", ""),
            "summary_it": ch.get("summary_it", ""), "title_it": ch.get("title_it", ""), "source_file": ch.get("root_file", ""),
            "source_sha256": ch.get("root_sha256", ""), "source_file_it": ch.get("root_file_it", ""),
            "source_sha256_it": ch.get("root_sha256_it", ""), "learning_goals_json": json.dumps(ch.get("learning_goals", []), ensure_ascii=False),
            "learning_goals_it_json": json.dumps(ch.get("learning_goals_it", []), ensure_ascii=False)}.items():
            change(cid, field, value, attribute=True)
        change(ch["hub_id"], "summary", ch.get("summary", ""))
        change(ch["hub_id"], "current_source_version", version, attribute=True)
        it_sections = {s["id"]: s for s in ch.get("sections_it", [])}
        for sec in ch.get("sections", []):
            its = it_sections[sec["id"]]
            for field, value in {"source_version": version, "file": sec.get("file"), "line": sec.get("line"),
                "sha256": sec.get("sha256"), "source_file": sec.get("file"), "source_line": sec.get("line"),
                "source_sha256": sec.get("sha256"), "file_it": its.get("file"), "line_it": its.get("line"),
                "sha256_it": its.get("sha256"), "title_it": its.get("title", "")}.items():
                change(sec["id"], field, value, attribute=True)
    for n in D["nodes"]:
        nid = n["id"]
        if n.get("collection") in {"W", "O", "P", "F"} or nid.startswith(("PUB:V11:", "BIB:")) or nid in chapter_map or nid in bib_ids:
            actual = sorted(chapter_map[nid])
            change(nid, "actual", actual)
            change(nid, "mapped", sorted(set(n.get("mapped", [])) | set(actual)))
            change(nid, "printed", nid in bib_ids)
            for field, value in {"ndse2_actual_chapters_json": json.dumps(actual), "ndse2_in_bibliography": nid in bib_ids,
                "ndse2_citation_basis": f"Final active EN/ITA source edition {version}; index links and nocite excluded",
                "manuscript_citation_status": "CITED_IN_CURRENT_CHAPTERS" if actual else "BIBLIOGRAPHY_ONLY" if nid in bib_ids else "COMPANION_READING_NOT_IN_CURRENT_BOOK"}.items():
                change(nid, field, value, attribute=True)
            if n.get("collection") == "F":
                change(nid, "book_citation_status", "IN_PUBLISHED_NDSE2_BIBLIOGRAPHY" if nid in bib_ids else "COMPANION_READING_NOT_IN_BOOK", attribute=True)
                change(nid, "new_manuscript_citation", bool(actual), attribute=True)
    for nid in ("PUB:NDSE2", "V06"):
        change(nid, "source_version", version, attribute=True)
        for field in ("title", "title_it", "subtitle", "subtitle_it", "publication_status", "publisher"):
            if field in book["book"]:
                change(nid, field, book["book"][field], attribute=True)
    for unit in units:
        change(unit["id"], "source_version", version, attribute=True)
    ga = D["meta"].setdefault("graphAttributes", {})
    ga.update(current_book_edition=edition_id, current_chapter_count=len(book["chapters"]),
              current_book_metadata_sha256=payload_sha256(book), current_book_graph_note=f"Current literal EN/ITA citations use source edition {version}; all earlier citation layers remain historical")
    f_bib = sum(n.get("collection") == "F" and n["id"] in bib_ids for n in D["nodes"])
    f_cited = sum(n.get("collection") == "F" and bool(chapter_map.get(n["id"])) for n in D["nodes"])
    ga["fowler_book_changed"] = f"SOURCE_VERSION_{version}_RECONCILED_{f_bib}_BIBLIOGRAPHY_{f_cited}_CHAPTER_SOURCES"
    return {"status": "reconciled", "source_version": version, "previous_source_version": current_version,
            "chapters": len(book["chapters"]), "sections": sum(len(c.get("sections", [])) for c in book["chapters"]),
            "literal_occurrences": len(occurrences), "chapter_source_pairs": sum(map(len, chapter_map.values())),
            "bibliography_source_ids": sorted(bib_ids), "book_sha256": payload_sha256(book), "new_citation_layer": True,
            "occurrences": occurrences}


def export_raw(payload):
    """NetworkX-style node/edge export with normalized display data retained."""
    validate_payload(payload)
    return {"directed": True, "multigraph": True, "graph": copy.deepcopy(payload["meta"].get("graphAttributes", {})),
            "meta": copy.deepcopy(payload["meta"]),
            "nodes": [{**copy.deepcopy(n["attributes"]), "id": n["id"],
                       "atlas_display": {k: copy.deepcopy(v) for k, v in n.items() if k != "attributes"}} for n in payload["nodes"]],
            "edges": [{**copy.deepcopy(e["attributes"]), "id": e["id"], "source": payload["nodes"][e["source"]]["id"],
                       "target": payload["nodes"][e["target"]]["id"], "key": copy.deepcopy(e["key"]),
                       "relation": e["relation"], "atlas_family": e["family"]} for e in payload["edges"]]}


def write_graphml(raw, target):
    """Write valid deterministic GraphML, preserving mixed multiedge key types."""
    ET.register_namespace("", GRAPH_NS)
    q = lambda tag: "{" + GRAPH_NS + "}" + tag
    root = ET.Element(q("graphml"))
    scopes = {"graph": [raw["graph"]], "node": [{k: v for k, v in n.items() if k != "id"} for n in raw["nodes"]],
              "edge": [{**{k: v for k, v in e.items() if k not in {"id", "source", "target", "key"}},
                        "atlas_original_key_json": _canonical(e["key"]), "atlas_edge_id": e["id"]} for e in raw["edges"]]}
    keys = {}
    for scope, rows in scopes.items():
        for name in sorted({k for row in rows for k in row}):
            values = [row[name] for row in rows if name in row and row[name] is not None]
            typ = "boolean" if values and all(type(v) is bool for v in values) else "long" if values and all(type(v) is int for v in values) else "double" if values and all(type(v) in (int, float) for v in values) else "string"
            kid = "k" + str(len(keys))
            keys[(scope, name)] = kid
            ET.SubElement(root, q("key"), id=kid, **{"for": scope, "attr.name": name, "attr.type": typ})
    def fill(element, scope, attrs):
        for name in sorted(attrs):
            value = attrs[name]
            text = _canonical(value) if value is None or isinstance(value, (bool, dict, list)) else str(value)
            ET.SubElement(element, q("data"), key=keys[(scope, name)]).text = text
    graph = ET.SubElement(root, q("graph"), id="KnowledgeAtlas", edgedefault="directed")
    fill(graph, "graph", raw["graph"])
    for node, attrs in zip(raw["nodes"], scopes["node"]):
        fill(ET.SubElement(graph, q("node"), id=node["id"]), "node", attrs)
    for edge, attrs in zip(raw["edges"], scopes["edge"]):
        fill(ET.SubElement(graph, q("edge"), id=edge["id"], source=edge["source"], target=edge["target"]), "edge", attrs)
    ET.indent(root, space="  ")
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(target, encoding="utf-8", xml_declaration=True)


def render_current_atlas(baseline_html, payload, version, date):
    """Refresh known v13+ shell labels/counts without changing application logic.

    Deliberately fails if the baseline no longer uses the known normalized shell;
    a changed frontend requires an explicit adapter, not a broad text rewrite.
    """
    previous = extract_payload(baseline_html)
    _check_date(date, "date")
    if not re.fullmatch(r"v?\d+(?:\.\d+){1,3}", str(version)):
        raise UpdateError("Invalid rendered release")
    version = str(version) if str(version).startswith("v") else "v" + str(version)
    text = PAYLOAD_RE.sub(lambda m: m.group(1) + "{}" + m.group(3), baseline_html, count=1)
    default = re.search(r"const defaultState=.*?;", text)
    if not default or 'id="sourceN"' not in text:
        raise UpdateError("Unsupported Atlas frontend; v13 normalized NDSE2 shell is required")
    original_default = default.group(0)
    counts = collections.Counter(n.get("collection") for n in payload["nodes"])
    for code in ("W", "O", "P", "F", "B", "N") + (("PAT",) if counts['PAT'] else ()):
        pattern = r'(<label class="source-row"[^>]*><input id="source' + code + r'".*?<span class="count">)\d+(</span></label>)'
        text, found = re.subn(pattern, lambda m: m.group(1) + str(counts[code]) + m.group(2), text, count=1)
        if found != 1:
            raise UpdateError(f"Source count placeholder changed: {code}")
    # Replace entire known semantic fragments; do not globally rewrite numeric
    # strings that might also be IDs, SVG coordinates or historical provenance.
    text = re.sub(r'(<title>AI & Software Engineering · Knowledge Atlas )v[\d.]+( · Published NDSE2</title>)', lambda m: m.group(1) + version + m.group(2), text, count=1)
    text = re.sub(r'(<span class="version">)V[\d.]+( · NDSE2 &amp; SOURCES</span>)', lambda m: m.group(1) + version.upper() + m.group(2), text, count=1)
    text = re.sub(r'(<span class="count" id="edgeTypesCount">)\d+( types</span>)', lambda m: m.group(1) + str(len(payload["relations"])) + m.group(2), text, count=1)
    text = re.sub(r'(<details class="disclosure" id="contextDetails"><summary>Context nodes <span class="count">)\d+(</span>)',
                  lambda m: m.group(1) + str(counts[None]) + m.group(2), text, count=1)
    text = re.sub(r'(<span id="footerCounts">).*?(</span>)', lambda m: m.group(1) + f"{version.upper()} · {len(payload['nodes']):,} nodes · {len(payload['edges']):,} directed edges" + m.group(2), text, count=1)
    text = re.sub(r'\d+ published chapters · EN / ITA', f"{counts['N']} published chapters · EN / ITA", text)
    text = re.sub(r"toast\('\d+ essays from martinfowler\.com\.", f"toast('{counts['F']} essays from martinfowler.com.", text)
    text = re.sub(r"toast\('\d+ published NDSE2 chapters\.", f"toast('{counts['N']} published NDSE2 chapters.", text)
    text = re.sub(r"toast\('All [\d,]+ nodes and [\d,]+ relationships are enabled\.'\)", f"toast('All {len(payload['nodes']):,} nodes and {len(payload['edges']):,} relationships are enabled.')", text)
    text = re.sub(r"v[\d.]+ static graph: [\d,]+ nodes, [\d,]+ directed relationships and \d+ distinct edge types", f"{version} static graph: {len(payload['nodes']):,} nodes, {len(payload['edges']):,} directed relationships and {len(payload['relations'])} distinct edge types", text)
    text = re.sub(r'All [\d,]+ nodes and [\d,]+ edges, including hidden records\.', f"All {len(payload['nodes']):,} nodes and {len(payload['edges']):,} edges, including hidden records.", text)
    text = re.sub(r'F001–F\d+ are independent atlas identifiers;', f"F001–F{counts['F']:03} are independent atlas identifiers;", text)
    text = re.sub(r'— v[\d.]+ filtered graph', "— " + version + " filtered graph", text)
    text = re.sub(r'AI_SWE_Atlas_v\d+(?:[._]\d+)*_', "AI_SWE_Atlas_" + version.replace(".", "_") + "_", text)
    text = text.replace("The P corpus retains its 71 restricted substantive records.",
                        "The P corpus retains source-specific access and inspection limits; restricted records remain explicitly qualified.")
    text = text.replace("F sources actually present in the published bibliography and chapters are marked; new F034/F035 records remain companion readings.",
                        "F bibliography membership and literal chapter citations follow the current published source edition; editorial companion mappings remain separate.")
    note = f"Release {version}, {date}. Updated from the exact supplied website package. All historical node IDs and keyed edges remain; current source provenance and literal book citations remain distinct. The original opening view is preserved."
    text = re.sub(r'<p>Release v[\d.]+ .*?</p>', lambda m: "<p>" + html_module.escape(note) + "</p>", text, count=1)
    old_book, new_book = _current_book_version(previous), _current_book_version(payload)
    if old_book and new_book and old_book != new_book:
        # The payload has already been removed. These occurrences are current UI
        # labels, not historical data; IDs and frozen history remain untouched.
        text = text.replace("final EN/ITA " + old_book, "final EN/ITA " + new_book)
        text = text.replace("NDSE2 " + old_book, "NDSE2 " + new_book)
    if re.search(r"const defaultState=.*?;", text).group(0) != original_default:
        raise UpdateError("Internal error: defaultState changed")
    embedded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c").replace("&", "\\u0026")
    return PAYLOAD_RE.sub(lambda m: m.group(1) + embedded + m.group(3), text, count=1)
