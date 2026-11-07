#!/usr/bin/env python3
"""Explicit reviewed source-to-practice classification; append-only graph overlay.

The review binds each mapping to an existing source annotation or an exact
historical occurrence route. It changes no source, practice, book or citation
record. It does not retrieve primary texts or establish practice effectiveness.
"""
from __future__ import annotations

import collections
import copy
import hashlib
import html
import json
import re
import shutil

KIND = "atlas_practice_links_update/1"
SOURCE_COLLECTIONS = ("W", "O", "P", "F", "B", "N")
FAMILY = "practice"
SEMANTICS = "Editorial classification, not evidence of effectiveness or a literal book citation."
EXCLUSION_CATEGORIES = {"navigation_only", "promotion_or_announcement", "source_recruitment_only", "non_operational_context"}
RELATIONS = {
    "INFORMS_PRACTICE": {"label": "Informs practice", "scope": "thematic",
        "meaning": "The source's argument or findings inform a particular part of the practice."},
    "ILLUSTRATES_PRACTICE": {"label": "Illustrates practice", "scope": "reported_application",
        "meaning": "The source reports an application or example relevant to the practice; transfer is not guaranteed."},
    "EVALUATES_PRACTICE": {"label": "Evaluates a practice component", "scope": "component_evaluation",
        "meaning": "The source evaluates the named component, not the entire editorial practice guide."},
    "CAUTIONS_PRACTICE": {"label": "Cautions about practice", "scope": "boundary",
        "meaning": "The source identifies a failure mode, constraint or boundary relevant to using the practice."},
    "DOCUMENTS_PRACTICE": {"label": "Documents practice origin", "scope": "historical_documentation",
        "meaning": "An existing historical occurrence connects this earlier-book record to the reconciled practice."},
}


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def release_paths(review):
    suffix = "v" + review["release"].replace(".", "_") + "_" + review["date"].replace("-", "")
    return {"release_notes": "UPDATE_" + suffix + ".html",
            "review_path": "data/updates/practice_links_review_" + suffix + ".json"}


def validate_review(review, state):
    """Validate the migration envelope and mapping shape, without reading files."""
    if not isinstance(review, dict) or review.get("kind") != KIND or review.get("schema_version") != 1:
        raise ValueError("Unsupported practice-links review schema")
    allowed = {"kind", "schema_version", "baseline_sha256", "baseline_payload_sha256", "baseline_release",
               "release", "date", "book_policy", "editorial_review", "mappings", "notes", "release_intro",
               "coverage", "provenance", "published_baseline", "additions", "revisions", "edges", "exclusions"}
    if set(review) - allowed:
        raise ValueError("Unsupported practice-links review fields: " + ", ".join(sorted(set(review) - allowed)))
    for field in ("baseline_sha256", "baseline_payload_sha256", "baseline_release", "release", "date"):
        if not _text(review.get(field)) or review[field] != state.get(field):
            raise ValueError("Practice-links review differs from the frozen run: " + field)
    if review.get("book_policy") != "unchanged":
        raise ValueError("Practice links preserve the book; book_policy must be unchanged")
    for field in ("additions", "revisions", "edges"):
        if field in review and review[field] != []:
            raise ValueError("Practice-links migration cannot contain source, node or ordinary edge operations: " + field)
    editorial = review.get("editorial_review")
    if not isinstance(editorial, dict) or editorial.get("status") != "complete" or any(not _text(editorial.get(k)) for k in ("reviewer", "scope")):
        raise ValueError("A completed named editorial review of the source-practice mappings is required")
    if "notes" in review and (not isinstance(review["notes"], list) or any(not _text(x) for x in review["notes"])):
        raise ValueError("Practice-links notes must be a list of nonempty strings")
    mappings = review.get("mappings")
    if not isinstance(mappings, list) or not mappings or any(not isinstance(m, dict) for m in mappings):
        raise ValueError("mappings must be a nonempty list of explicitly reviewed source-practice records")
    required = {"source", "practice", "relation", "primary", "rationale", "basis", "scope"}
    seen = set()
    for mapping in mappings:
        if not required.issubset(mapping) or set(mapping) - required - {"evaluated_component"}:
            raise ValueError("Each practice mapping requires exactly the declared mapping fields")
        if any(not _text(mapping.get(k)) for k in ("source", "practice", "relation", "rationale", "scope")):
            raise ValueError("Practice mapping endpoints, relation, rationale and scope must be nonempty text")
        if type(mapping["primary"]) is not bool:
            raise ValueError("Practice mapping primary must be an explicit boolean")
        pair = (mapping["source"], mapping["practice"])
        if pair in seen:
            raise ValueError("Only one canonical relationship is allowed per source/practice pair: " + " -> ".join(pair))
        seen.add(pair)
        relation = mapping["relation"]
        if relation not in RELATIONS or mapping["scope"] != RELATIONS[relation]["scope"]:
            raise ValueError("Practice relationship and scope do not match the reviewed vocabulary: " + relation)
        if relation == "EVALUATES_PRACTICE":
            if not _text(mapping.get("evaluated_component")):
                raise ValueError("EVALUATES_PRACTICE must identify the evaluated_component, not claim whole-practice effectiveness")
        elif "evaluated_component" in mapping:
            raise ValueError("evaluated_component is reserved for EVALUATES_PRACTICE")
        basis = mapping["basis"]
        if not isinstance(basis, dict):
            raise ValueError("Practice mapping basis must be an explicit object")
        if relation == "DOCUMENTS_PRACTICE":
            occurrences = basis.get("occurrence_ids")
            if set(basis) != {"occurrence_ids"} or not isinstance(occurrences, list) or not occurrences or any(not _text(x) for x in occurrences) or len(set(occurrences)) != len(occurrences):
                raise ValueError("DOCUMENTS_PRACTICE requires unique historical occurrence_ids")
        elif set(basis) != {"field", "excerpt"} or basis.get("field") not in ("summary", "limitation") or not _text(basis.get("excerpt")):
            raise ValueError("Editorial practice mappings require an exact summary or limitation excerpt")
    exclusions = review.get("exclusions", [])
    if not isinstance(exclusions, list) or any(not isinstance(x, dict) for x in exclusions):
        raise ValueError("exclusions must be a list of explicitly reviewed source records")
    excluded_ids = set()
    for exclusion in exclusions:
        if set(exclusion) != {"source", "reason", "basis", "category"} or any(not _text(exclusion.get(k)) for k in ("source", "reason", "category")):
            raise ValueError("Each exclusion requires source, reason, basis and category")
        if exclusion["source"] in excluded_ids:
            raise ValueError("A source may have only one exclusion decision: " + exclusion["source"])
        excluded_ids.add(exclusion["source"])
        if exclusion["category"] not in EXCLUSION_CATEGORIES:
            raise ValueError("Unsupported source-practice exclusion category")
        basis = exclusion["basis"]
        if not isinstance(basis, dict) or set(basis) != {"field", "excerpt"} or basis.get("field") not in ("summary", "limitation") or not _text(basis.get("excerpt")):
            raise ValueError("An exclusion requires an exact summary or limitation excerpt")
    return {"kind": KIND, "status": "complete", "reviewed_mappings": len(mappings), "reviewed_exclusions": len(exclusions)}


def validate_mappings(baseline, review):
    """Bind every mapping to the immutable graph and require complete coverage."""
    from atlas_graph import payload_sha256, validate_payload
    validate_payload(baseline)
    if review.get("baseline_payload_sha256") != payload_sha256(baseline):
        raise ValueError("Practice-links baseline payload hash mismatch")
    by = {n["id"]: n for n in baseline["nodes"]}
    sources = {n["id"] for n in baseline["nodes"] if n.get("collection") in SOURCE_COLLECTIONS}
    practices = {n["id"] for n in baseline["nodes"] if n.get("collection") == "PAT" and n.get("kind") == "practice_descriptor"}
    if not sources or not practices:
        raise ValueError("Practice-links migration requires existing source records and PAT descriptors")
    known_routes = {(baseline["nodes"][e["source"]]["id"], baseline["nodes"][e["target"]]["id"], e["relation"]) for e in baseline["edges"]}
    existing_pairs = {(baseline["nodes"][e["source"]]["id"], baseline["nodes"][e["target"]]["id"]) for e in baseline["edges"] if e.get("family") == FAMILY or e.get("relation") in RELATIONS}
    covered_sources, covered_practices, primary = set(), set(), collections.Counter()
    by_collection, by_relation = collections.Counter(), collections.Counter()
    for mapping in review["mappings"]:
        source, practice = mapping["source"], mapping["practice"]
        if source not in sources or practice not in practices:
            raise ValueError("Practice links require an existing W/O/P/F/B/N source and PAT descriptor: " + source + " -> " + practice)
        if (source, practice) in existing_pairs:
            raise ValueError("An existing source/practice pair cannot be duplicated or silently reclassified: " + source + " -> " + practice)
        relation, basis = mapping["relation"], mapping["basis"]
        if relation == "DOCUMENTS_PRACTICE":
            if by[source].get("collection") != "B":
                raise ValueError("DOCUMENTS_PRACTICE is restricted to exact historical B/OCC/PAT provenance")
            for occurrence in basis["occurrence_ids"]:
                if occurrence not in by or by[occurrence].get("kind") != "practice_occurrence" or (occurrence, source, "V10_OCCURRENCE_IN_FILE") not in known_routes or (occurrence, practice, "V10_DESCRIBES_RECONCILED_PRACTICE") not in known_routes:
                    raise ValueError("No exact historical source/occurrence/practice route: " + source + " <- " + occurrence + " -> " + practice)
        elif basis["excerpt"] not in by[source][basis["field"]]:
            raise ValueError("Mapping evidence is not an exact substring of baseline " + source + "." + basis["field"])
        covered_sources.add(source)
        covered_practices.add(practice)
        primary[source] += int(mapping["primary"])
        by_collection[by[source]["collection"]] += 1
        by_relation[relation] += 1
    excluded_sources = set()
    for exclusion in review.get("exclusions", []):
        source, basis = exclusion["source"], exclusion["basis"]
        if source not in sources:
            raise ValueError("An excluded record must be an existing W/O/P/F/B/N source: " + source)
        if source in covered_sources:
            raise ValueError("A source cannot be both mapped and excluded: " + source)
        if basis["excerpt"] not in by[source][basis["field"]]:
            raise ValueError("Exclusion evidence is not an exact substring of baseline " + source + "." + basis["field"])
        excluded_sources.add(source)
    unreviewed = sources - covered_sources - excluded_sources
    if unreviewed:
        raise ValueError("Source-practice review is incomplete; missing sources: " + ", ".join(sorted(unreviewed)))
    wrong_primary = {sid: primary[sid] for sid in sorted(covered_sources) if primary[sid] != 1}
    if wrong_primary:
        raise ValueError("Each source requires exactly one primary practice classification: " + json.dumps(wrong_primary, sort_keys=True))
    if practices - covered_practices:
        raise ValueError("Source-practice review leaves practices uncovered: " + ", ".join(sorted(practices - covered_practices)))
    return {"source_count": len(sources), "reviewed_source_count": len(covered_sources | excluded_sources),
            "mapped_source_count": len(covered_sources), "excluded_source_count": len(excluded_sources),
            "eligible_source_count": len(sources - excluded_sources), "eligible_coverage_percent": 100,
            "practice_count": len(practices), "link_count": len(review["mappings"]),
            "source_counts": {c: sum(by[s]["collection"] == c for s in sources) for c in SOURCE_COLLECTIONS},
            "mapped_source_counts": {c: sum(by[s]["collection"] == c for s in covered_sources) for c in SOURCE_COLLECTIONS},
            "excluded_source_counts": {c: sum(by[s]["collection"] == c for s in excluded_sources) for c in SOURCE_COLLECTIONS},
            "link_counts_by_source_collection": dict(sorted(by_collection.items())), "relation_counts": dict(sorted(by_relation.items())),
            "primary_count": sum(primary.values()), "unclassified_sources": sorted(excluded_sources),
            "unreviewed_sources": [], "uncovered_practices": [], "all_mapped_sources_have_exactly_one_primary": True}


def apply_links(baseline, review, state):
    from atlas_graph import payload_sha256, validate_payload
    validate_review(review, state)
    coverage = validate_mappings(baseline, review)
    graph = copy.deepcopy(baseline)
    indexes = {n["id"]: i for i, n in enumerate(graph["nodes"])}
    by = {n["id"]: n for n in graph["nodes"]}
    digest = payload_sha256(review)
    edge_ids = {e["id"] for e in graph["edges"]}
    keyed = {(e["source"], e["target"], json.dumps(e["key"], sort_keys=True)) for e in graph["edges"]}
    existing_relations = {r["id"]: r for r in graph["relations"]}
    if any(r in existing_relations and existing_relations[r]["family"] != FAMILY for r in RELATIONS):
        raise ValueError("A practice relation already belongs to a different edge family")
    existing_family = next((g for g in graph["edgeFamilies"] if g["id"] == FAMILY), None)
    if existing_family and existing_family.get("label") != "Practice links":
        raise ValueError("An incompatible practice edge family already exists")
    if existing_family is None:
        graph["edgeFamilies"].append({"id": FAMILY, "label": "Practice links", "count": 0})
    added = []
    for mapping in sorted(review["mappings"], key=lambda m: (m["source"], m["practice"])):
        source, practice = mapping["source"], mapping["practice"]
        pair_hash = hashlib.sha256((source + "\0" + practice).encode("utf-8")).hexdigest()[:24]
        eid, key = "practice_" + pair_hash, "PRACTICE:" + source + ":" + practice
        identity = (indexes[source], indexes[practice], json.dumps(key, sort_keys=True))
        if eid in edge_ids or identity in keyed:
            raise ValueError("Practice edge would reuse an existing edge ID or key")
        attrs = {k: copy.deepcopy(mapping[k]) for k in ("rationale", "primary", "basis", "scope")}
        if "evaluated_component" in mapping:
            attrs["evaluated_component"] = mapping["evaluated_component"]
        attrs.update(relation=mapping["relation"], review_kind=KIND, reviewed_on=review["date"],
                     review_digest=digest, review_path=release_paths(review)["review_path"],
                     provenance="Reviewed source-to-practice classification from the frozen Atlas annotations or exact historical occurrence route, " + review["date"],
                     semantics=SEMANTICS, literal_book_citation=False, practice_effectiveness_claim=False,
                     empirical_validation=False, primary_text_reinspected=False,
                     source_record_sha256=payload_sha256(by[source]), practice_record_sha256=payload_sha256(by[practice]))
        if mapping["relation"] == "DOCUMENTS_PRACTICE":
            attrs["inspection_scope"] = "Existing graph provenance route; a historical origin record, not independent empirical evidence."
        else:
            attrs["inspection_scope"] = "Exact existing Atlas " + mapping["basis"]["field"] + " excerpt and the existing practice guide; no new full-text inspection or replication is asserted."
        source_evidence = by[source].get("attributes", {}).get("evidence_review", {})
        if isinstance(source_evidence, dict) and source_evidence.get("access"):
            attrs["inherited_source_access"] = source_evidence["access"]
        graph["edges"].append({"id": eid, "source": indexes[source], "target": indexes[practice],
                               "key": key, "relation": mapping["relation"], "family": FAMILY, "attributes": attrs})
        added.append(eid)
        edge_ids.add(eid)
        keyed.add(identity)
    counts = collections.Counter(e["relation"] for e in graph["edges"])
    graph["relations"] = [{**r, "count": counts[r["id"]]} for r in graph["relations"]] + [
        {"id": relation, "label": RELATIONS[relation]["label"], "family": FAMILY, "count": counts[relation]}
        for relation in RELATIONS if counts[relation] and relation not in existing_relations]
    family_counts = collections.Counter(e["family"] for e in graph["edges"])
    graph["edgeFamilies"] = [{**g, "count": family_counts[g["id"]]} for g in graph["edgeFamilies"]]
    meta = graph["meta"]
    meta.setdefault("atlas_metadata_history", []).append({"release_before_update": baseline["meta"].get("edition"),
        "date_before_update": baseline["meta"].get("date"), "notes": copy.deepcopy(baseline["meta"].get("notes", []))})
    meta.update(edition=review["release"] + " · Reviewed practice connections", date=review["date"],
                nodeCount=len(graph["nodes"]), edgeCount=len(graph["edges"]), relationCount=len(graph["relations"]))
    meta["practice_links"] = {"schema": KIND, "reviewed_on": review["date"], "release": review["release"],
        "review_path": release_paths(review)["review_path"], "semantics": SEMANTICS, "coverage": coverage,
        "relation_definitions": copy.deepcopy(RELATIONS), "exclusions": copy.deepcopy(review.get("exclusions", []))}
    meta["notes"] = [
        "Release " + review["release"] + ", " + review["date"] + ": reviewed source-to-practice connections added to the exact published baseline.",
        "All source and practice nodes, historical keyed edges, book metadata and literal citation fields are retained unchanged.",
        str(coverage["reviewed_source_count"]) + " existing sources reviewed: " + str(coverage["mapped_source_count"]) + " classified to " + str(coverage["practice_count"]) + " practices, and " + str(coverage["excluded_source_count"]) + " explicitly excluded with reasons. Each mapped source has exactly one primary classification.",
        SEMANTICS, "No new sources, revised source findings or fresh primary-text inspections are claimed by this migration.",
    ] + list(review.get("notes", []))
    meta.setdefault("graphAttributes", {}).update(portable_atlas_release=review["release"], portable_atlas_snapshot_date=review["date"],
        atlas_update=review["release"] + "_" + review["date"].replace("-", ""),
        portable_atlas_basis="Exact published website plus an explicitly reviewed source-to-practice edge overlay; all source, practice and book records retained.",
        practice_links_review=release_paths(review)["review_path"], practice_links_schema=KIND,
        practice_link_count=coverage["link_count"], practice_classified_source_count=coverage["mapped_source_count"],
        practice_reviewed_source_count=coverage["reviewed_source_count"], practice_excluded_source_count=coverage["excluded_source_count"], practice_links_semantics=SEMANTICS)
    meta.setdefault("automation_updates", []).append({"kind": KIND, "review_digest": digest, "release": review["release"],
        "date": review["date"], "baseline_payload_sha256": payload_sha256(baseline), "baseline_zip_sha256": review["baseline_sha256"]})
    meta.pop("graphSha256", None)
    if graph["nodes"] != baseline["nodes"] or graph["edges"][:len(baseline["edges"])] != baseline["edges"]:
        raise ValueError("Practice-links overlay changed existing graph records")
    validate_payload(graph)
    audit = {"kind": KIND, "date": review["date"], "release": review["release"], "review_digest": digest,
        "baseline_payload_sha256": payload_sha256(baseline), "result_payload_sha256": payload_sha256(graph),
        "baseline_nodes": len(baseline["nodes"]), "baseline_edges": len(baseline["edges"]),
        "nodes": len(graph["nodes"]), "edges": len(graph["edges"]), "relation_types": len(graph["relations"]),
        "source_additions": [], "new_source_ids": [], "changed_source_ids": [], "added_nodes": [], "added_edges": added,
        "no_changes": False, "all_original_nodes_identical": True, "all_original_node_ids_retained": True,
        "all_original_edges_identical": True, "book": {"status": "unchanged"}, "coverage": coverage,
        "editorial_review": copy.deepcopy(review["editorial_review"]), "semantics": SEMANTICS}
    return graph, audit


def render_release_page(site, state, review, audit, config):
    esc = lambda x: html.escape(str(x), quote=True)
    cov = audit["coverage"]
    body = '<p class="eyebrow">Atlas v' + esc(state["release"]) + ' · ' + esc(state["date"]) + '</p><h1>Sources connected to engineering practices</h1>'
    body += '<p>' + esc(review.get("release_intro") or ("All " + str(cov["reviewed_source_count"]) + " existing source records were reviewed: " + str(cov["mapped_source_count"]) + " have explicit relationships to " + str(cov["practice_count"]) + " engineering practices, and " + str(cov["excluded_source_count"]) + " have documented reasons for exclusion. This update adds no sources and retains the existing source annotations, operational guides and book citations.")) + '</p>'
    body += '<p><a href="catalogues/practices.html">Browse practices and their sources</a> · <a href="swe_knowledge_graph.html?practice=all">Explore practice connections in the graph</a></p>'
    body += '<h2>What changed</h2><p>The previous practice guides had chapter-reading and historical-occurrence routes, but no direct source-to-practice classification. The new layer contains ' + str(cov["link_count"]) + ' reviewed links, with exactly one primary practice for every mapped source and additional relevant connections where warranted. All eligible source records are mapped; navigation-only and other non-operational records retain their identity and their explicit review decisions.</p>'
    body += '<table><thead><tr><th>Collection</th><th>Records reviewed</th><th>Mapped</th><th>Excluded with reason</th><th>Practice links</th></tr></thead><tbody>'
    for code in SOURCE_COLLECTIONS:
        label = next((c["title"] for c in config["collections"] if c["code"] == code), code)
        body += '<tr><th>' + esc(label) + '</th><td>' + str(cov["source_counts"][code]) + '</td><td>' + str(cov["mapped_source_counts"][code]) + '</td><td>' + str(cov["excluded_source_counts"][code]) + '</td><td>' + str(cov["link_counts_by_source_collection"].get(code, 0)) + '</td></tr>'
    body += '</tbody></table><h2>How to read a practice link</h2><p>' + esc(SEMANTICS) + ' A primary classification identifies the most useful editorial entry point for that source; it is not a quality rating.</p><dl>'
    for relation, definition in RELATIONS.items():
        body += '<dt><strong>' + esc(definition["label"]) + '</strong> · ' + str(cov["relation_counts"].get(relation, 0)) + '</dt><dd>' + esc(definition["meaning"]) + '</dd>'
    body += '</dl><h2>Review basis and limits</h2><p>Every editorial mapping carries a specific rationale and an exact excerpt from the source’s existing Atlas summary or limitation. A component-evaluation link names the component evaluated. Historical documentation links preserve the exact earlier-book ← occurrence → practice route. This mapping review does not assert a fresh inspection of every primary text, independent replication, or validation of a complete practice.</p>'
    body += '<p>Practice pages and source cards provide reciprocal links. The graph offers an overview of the classification and a focused view for each practice. The original Polimi opening view remains available, and all existing node identifiers and keyed relationships are retained.</p>'
    for note in review.get("notes", []):
        body += '<p>' + esc(note) + '</p>'
    if review.get("exclusions"):
        body += '<h2>Reviewed records without a practice classification</h2><p>These records remain in the source corpus. An announcement, navigation page or other contextual item is not assigned a practice merely to inflate coverage.</p><ul>'
        for exclusion in review["exclusions"]:
            source = exclusion["source"]
            code = "N" if source.startswith("NDSE2:") else source[0]
            slug = next(c["slug"] for c in config["collections"] if c["code"] == code)
            body += '<li><a href="catalogues/' + esc(slug) + '.html#' + esc(source) + '">' + esc(source) + '</a>: ' + esc(exclusion["reason"]) + '</li>'
        body += '</ul>'
    body += '<h2>Published baseline and verification</h2><p>Published baseline: <code>' + esc(state["baseline_name"]) + '</code> (v' + esc(state["baseline_release"]) + ').</p><p>SHA-256: <code style="overflow-wrap:anywhere">' + esc(state["baseline_sha256"]) + '</code></p>'
    links = [(release_paths(review)["review_path"], "Complete reviewed mapping and graph audit"),
             ("data/practice_links.json", "Practice-link data"), ("data/practice_coverage.json", "Classification coverage"),
             ("verification/report.html", "Release verification")]
    for key, label in (("practitioner_update", "Previous practitioner-source update"), ("polimi_update", "Previous SEPolimi update")):
        if config.get(key, {}).get("release_notes"):
            links.append((config[key]["release_notes"], label))
    body += '<ul>' + ''.join('<li><a href="' + esc(url) + '">' + esc(label) + '</a></li>' for url, label in links) + '</ul><p>The full package and delta are generated and checked locally. Publication follows the existing GitHub Pages workflow.</p><p><a href="index.html">Home</a></p>'
    (site / release_paths(review)["release_notes"]).write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Atlas practice connections update</title><link rel="stylesheet" href="assets/site.css"><body><main class="wrap" id="main">' + body + '</main></body></html>', encoding="utf-8")


def build_practice_links_to(root, destination, state, review, book=None):
    from atlas_cli import install_tools, load, run_builder, save, sha
    from atlas_graph import export_raw, payload_sha256, render_current_atlas, write_graphml
    if book is not None:
        raise ValueError("Practice-links migration accepts no book replacement or reconciliation")
    baseline = load(root / "baseline_payload.json")
    graph, audit = apply_links(baseline, review, state)
    shutil.copytree(root / "baseline", destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"))
    install_tools(destination)
    config = load(destination / "source/site_config.json")
    if config.get("practitioner_update"):
        config["practitioner_update"].setdefault("release_notes", config.get("release_notes"))
    paths = release_paths(review)
    config.update(site_version=state["release"], graph_version=state["release"], build_date=state["date"],
        graph_snapshot=state["date"], atlas_source="atlas_current.html", graph_json="data/graph/knowledge_graph_current.json",
        graph_graphml="data/graph/knowledge_graph_current.graphml", payload_json="data/graph/atlas_payload_current.json",
        release_notes=paths["release_notes"], practice_links_audit=paths["review_path"])
    config["practice_links_update"] = {"kind": KIND, "date": state["date"], "release": state["release"],
        **paths, **{k: audit["coverage"][k] for k in ("source_count", "reviewed_source_count", "mapped_source_count", "excluded_source_count",
            "eligible_source_count", "eligible_coverage_percent", "practice_count", "link_count", "relation_counts")},
        "exclusions": copy.deepcopy(review.get("exclusions", [])), "semantics": SEMANTICS}
    save(destination / "source/site_config.json", config)
    graph["meta"]["graphFile"] = "knowledge_graph_current.graphml"
    write_graphml(export_raw(graph), destination / config["graph_graphml"])
    graph["meta"]["graphSha256"] = sha(destination / config["graph_graphml"])
    audit["result_payload_sha256"] = payload_sha256(graph)
    save(destination / config["graph_json"], export_raw(graph))
    save(destination / config["payload_json"], graph)
    old_config = load(root / "baseline/source/site_config.json")
    source_template = root / "baseline/source" / old_config["atlas_source"]
    current = render_current_atlas(source_template.read_text(encoding="utf-8"), graph, version=state["release"], date=state["date"])
    (destination / "source/atlas_current.html").write_text(current, encoding="utf-8")
    save(destination / paths["review_path"], {"as_of": state["date"], "review": review, "graph_update": audit})
    save(destination / "source/automation_release.json", {"tool_version": "1.1.0", "kind": KIND, "date": state["date"],
        "release": state["release"], "baseline_name": state["baseline_name"], "baseline_sha256": state["baseline_sha256"],
        "source_additions": [], "practice_links_added": len(audit["added_edges"]), "review_path": paths["review_path"]})
    render_release_page(destination, state, review, audit, config)
    run_builder(destination)
    return audit
