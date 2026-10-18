#!/usr/bin/env python3
"""Rebuild the October 18 Atlas update from its frozen baseline and audited inputs.

Uses only the Python standard library. Does not access the network or modify the
frozen v12 graph. Published-book metadata and current citations form a new layer.
"""
from __future__ import annotations

import collections
import copy
import csv
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parent
DATE = "2026-10-18"
BASE = SOURCE / "atlas_v12_original.html"
EDITION_ID = "EDITION:NDSE2:13.7.1"
PUBLICATION_ID = "PUB:NDSE2"
GRAPH_NS = "http://graphml.graphdrawing.org/xmlns"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def node(nid, label, kind, category=None, collection=None, **kwargs):
    n = {
        "id": nid, "label": label, "kind": kind, "collection": collection,
        "category": category, "streams": [], "actual": [], "mapped": [],
        "printed": False, "summary": "", "limitation": "", "url": "",
        "authors": "", "year": "", "topics": [], "volumes": [], "attributes": {},
    }
    n.update(kwargs)
    n["attributes"].setdefault("label", label)
    n["attributes"].setdefault("kind", kind)
    n["attributes"].setdefault("node_class", "NDSE2_PUBLISHED_EDITION_20261018")
    return n


def graphml(raw, target):
    """GraphML retains semantic multiedge keys in an explicit JSON property.

    XML edge IDs are unique. atlas_original_key_json round-trips the original
    mixed string/integer keys without relying on a GraphML reader's ID coercion.
    """
    ET.register_namespace("", GRAPH_NS)
    q = lambda tag: "{" + GRAPH_NS + "}" + tag
    root = ET.Element(q("graphml"))
    scopes = {
        "graph": [raw["graph"]],
        "node": [{k: v for k, v in n.items() if k != "id"} for n in raw["nodes"]],
        "edge": [
            {**{k: v for k, v in e.items() if k not in ("source", "target", "key", "id")},
             "atlas_original_key_json": json.dumps(e["key"], ensure_ascii=False),
             "atlas_edge_id": e["id"]}
            for e in raw["edges"]
        ],
    }
    keys = {}
    for scope, rows in scopes.items():
        names = sorted({k for row in rows for k in row})
        for name in names:
            vals = [row[name] for row in rows if name in row and row[name] is not None]
            if vals and all(type(v) is bool for v in vals):
                typ = "boolean"
            elif vals and all(type(v) is int for v in vals):
                typ = "long"
            elif vals and all(type(v) in (int, float) for v in vals):
                typ = "double"
            else:
                typ = "string"
            kid = "k" + str(len(keys))
            keys[(scope, name)] = kid
            ET.SubElement(root, q("key"), id=kid, **{"for": scope, "attr.name": name, "attr.type": typ})

    def fill(element, scope, attrs):
        for name in sorted(attrs):
            v = attrs[name]
            if v is None:
                text = "null"
            elif type(v) is bool:
                text = str(v).lower()
            elif isinstance(v, (dict, list)):
                text = json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            else:
                text = str(v)
            ET.SubElement(element, q("data"), key=keys[(scope, name)]).text = text

    graph = ET.SubElement(root, q("graph"), id="KnowledgeAtlasV13", edgedefault="directed")
    fill(graph, "graph", raw["graph"])
    for n, attrs in zip(raw["nodes"], scopes["node"]):
        fill(ET.SubElement(graph, q("node"), id=n["id"]), "node", attrs)
    for e, attrs in zip(raw["edges"], scopes["edge"]):
        fill(ET.SubElement(graph, q("edge"), id=e["id"], source=e["source"], target=e["target"]), "edge", attrs)
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(target, encoding="utf-8", xml_declaration=True)


def main():
    base_html = BASE.read_text(encoding="utf-8")
    payload_match = re.search(r'<script id="graph-data" type="application/json">(.*?)</script>', base_html, re.S)
    D = json.loads(payload_match.group(1))
    old = copy.deepcopy(D)
    U = read_json(SOURCE / "article_update_20261018.json")
    B = read_json(SOURCE / "ndse2_book.json")
    chapters = B["chapters"]
    assert len(chapters) == 13
    assert [c["hub_id"] for c in chapters] == [f"C:C{i:02}" for i in range(1, 14)]
    by = {n["id"]: n for n in D["nodes"]}
    index = {n["id"]: i for i, n in enumerate(D["nodes"])}
    old_node_ids = set(by)
    added_node_ids = []
    added_edge_ids = []
    original_relations = {r["id"]: r for r in D["relations"]}
    relation_family = {r["id"]: r["family"] for r in D["relations"]}
    changes = []

    def add_node(n):
        assert n["id"] not in by, n["id"]
        n = copy.deepcopy(n)
        for k, default in node(n["id"], n["label"], n["kind"]).items():
            n.setdefault(k, copy.deepcopy(default))
        index[n["id"]] = len(D["nodes"])
        by[n["id"]] = n
        D["nodes"].append(n)
        added_node_ids.append(n["id"])
        return n

    def change(nid, field, value, attribute=False):
        obj = by[nid]["attributes"] if attribute else by[nid]
        previous = obj.get(field)
        if previous == value:
            return
        if previous is not None:
            prefix = "historical_v12_" if nid in old_node_ids else "pre_reconciliation_"
            obj.setdefault(prefix + field, copy.deepcopy(previous))
        obj[field] = value
        changes.append({"id": nid, "field": ("attributes." if attribute else "") + field})

    def edge(sid, tid, relation, family, attrs=None, key_suffix=""):
        assert sid in by and tid in by, (sid, tid, relation)
        family = relation_family.setdefault(relation, family)
        eid = f"u20261018_{len(added_edge_ids):05}"
        key = "UPDATE_20261018:" + relation + (":" + key_suffix if key_suffix else "")
        a = {"relation": relation, "provenance": "Atlas update, " + DATE}
        a.update(attrs or {})
        D["edges"].append({"id": eid, "source": index[sid], "target": index[tid],
                           "key": key, "relation": relation, "family": family, "attributes": a})
        added_edge_ids.append(eid)

    for n in U["nodes"] + U["context_nodes"]:
        add_node(n)
    for rev in U.get("metadata_updates", []):
        for k, v in rev["attributes_patch"].items():
            change(rev["id"], k, v, True)
    for e in U["edges"]:
        edge(e["source"], e["target"], e["relation"], e["family"], e.get("attributes"))

    book = B.get("book", {})
    title = book.get("title", book.get("title_en", "Non-Deterministic Software Engineering, Second Edition"))
    if isinstance(title, dict):
        title = title.get("EN", title.get("en", "Non-Deterministic Software Engineering, Second Edition"))
    full_title = str(title) if "second edition" in str(title).lower() else str(title) + ", Second Edition"
    subtitle = book.get("subtitle", book.get("subtitle_en", "Engineering Trustworthy Change in the Age of AI and Coding Agents"))
    if isinstance(subtitle, dict):
        subtitle = subtitle.get("EN", subtitle.get("en", ""))
    book_limit = "Author engineering synthesis and teaching material; publication is not independent empirical validation."
    provenance = "Author-supplied final EN/ITA 13.7.1 LaTeX sources; publication confirmed by the author on 2026-10-18."
    pub = add_node(node(PUBLICATION_ID, full_title, "published_book", "volumes",
                        authors="Enrico Papalini", year="2026", volumes=["V06"],
                        summary="Published second edition: 13 chapters, with the Knowledge Atlas as its companion.",
                        limitation=book_limit, url="https://popoloni.github.io/",
                        attributes={"volume_id": "V06", "author": "Enrico Papalini", "title": title,
                                    "subtitle": subtitle, "title_it": book.get("title_it", ""),
                                    "subtitle_it": book.get("subtitle_it", ""), "year": "2026", "edition_number": "2",
                                    "publisher": "Independently Published", "status": "PUBLISHED_AUTHOR_CONFIRMED",
                                    "publication_status": "Published; confirmed by author 2026-10-18",
                                    "publication_date": "Not asserted; 2026-10-18 is the confirmation date",
                                    "source_version": "13.7.1", "chapter_count": 13,
                                    "metadata_verification": provenance, "limitation": book_limit,
                                    "url": "https://popoloni.github.io/", "url_role": "author_companion"}))
    add_node(node(EDITION_ID, "NDSE2 · Published source edition 13.7.1", "edition", "teaching",
                  authors="Enrico Papalini", year="2026", volumes=["V06"],
                  summary="Final bilingual manuscript structure and literal source use, independently reconciled to the website.",
                  attributes={"source_version": "13.7.1", "chapter_count": 13,
                              "publication_status": "PUBLISHED_AUTHOR_CONFIRMED", "provenance": provenance,
                              "source_manifest": "data/updates/ndse2_source_manifest.json"}))
    edge(EDITION_ID, PUBLICATION_ID, "NDSE2_EDITION_OF", "provenance")
    edge(PUBLICATION_ID, "V06", "NDSE2_PUBLISHED_VOLUME", "provenance")
    change("V06", "label", full_title)
    change("V06", "summary", "Published second edition. Explore its 13 chapters and their verified literal source citations.")
    change("V06", "limitation", book_limit)
    change("V06", "year", "2026")
    change("V06", "url", "https://popoloni.github.io/")
    for field, value in {"label": full_title, "status": "PUBLISHED_AUTHOR_CONFIRMED",
                         "publication_confirmation_date": DATE, "source_version": "13.7.1",
                         "limitation": book_limit, "publication_id": PUBLICATION_ID,
                         "provenance": provenance}.items():
        change("V06", field, value, True)
    for v in D["volumes"]:
        if v["id"] == "V06":
            v["label"] = full_title

    citation_map = collections.defaultdict(set)
    occurrences = []
    section_rows = []
    unit_rows = []
    active_citation_ids = set()
    unresolved = []

    def valid_cites(cites):
        found = []
        for c in cites:
            s = c.get("source_id")
            if not s or s not in by:
                unresolved.append(c)
                continue
            found.append(c)
        return found

    def cite_edges(owner_id, cites, relation, chapter=None, language="EN"):
        grouped = collections.defaultdict(list)
        for cit in valid_cites(cites):
            sid = cit["source_id"]
            grouped[sid].append(cit)
            active_citation_ids.add(sid)
            if chapter:
                citation_map[sid].add(chapter)
            occurrences.append({**cit, "language": language, "owner_id": owner_id})
        for sid, cs in sorted(grouped.items()):
            locs = [{k: c.get(k) for k in ("file", "line", "macro", "bibkey", "sha256", "section_id")} for c in cs]
            edge(owner_id, sid, relation, "actual",
                 {"language": language, "citation_count": len(cs), "literal_citation": True,
                  "chapter_hub": chapter or "", "locators_json": json.dumps(locs, ensure_ascii=False),
                  "source_version": "13.7.1", "evidence_scope": "Literal manuscript use; not validation of the source claim"},
                 language)

    for ch in chapters:
        hid, cid = ch["hub_id"], ch["id"]
        assert cid == f"NDSE2:C{ch['number']:02}"
        attributes = {
            "chapter_number": ch["number"], "chapter_hub": hid, "title": ch["title"],
            "title_it": ch.get("title_it", ""), "summary": ch.get("summary", ""),
            "summary_it": ch.get("summary_it", ""), "author": "Enrico Papalini",
            "volume_id": "V06", "edition_id": EDITION_ID, "source_version": "13.7.1",
            "source_file": ch["root_file"], "source_sha256": ch["root_sha256"],
            "source_file_it": ch.get("root_file_it", ch["root_file"]),
            "source_sha256_it": ch.get("root_sha256_it", ""),
            "learning_goals_json": json.dumps(ch.get("learning_goals", []), ensure_ascii=False),
            "learning_goals_it_json": json.dumps(ch.get("learning_goals_it", []), ensure_ascii=False),
            "publication_status": "PUBLISHED_AUTHOR_CONFIRMED", "provenance": provenance,
            "evidence_class": "Published author chapter; engineering synthesis",
            "limitation": book_limit,
        }
        add_node(node(cid, ch["title"], "published_book_chapter", collection="N",
                      authors="Enrico Papalini", year="2026", volumes=["V06"],
                      actual=[hid], mapped=[hid], summary=ch.get("summary", ""),
                      limitation=book_limit, attributes=attributes))
        edge(PUBLICATION_ID, cid, "NDSE2_HAS_CHAPTER", "provenance", {"chapter_number": ch["number"]})
        edge(cid, hid, "NDSE2_REPRESENTS_CHAPTER", "provenance")
        change(hid, "label", ch["title"])
        change(hid, "summary", ch.get("summary", ""))
        change(hid, "title_it", ch.get("title_it", ""), True)
        change(hid, "published_chapter_record", cid, True)
        change(hid, "current_source_version", "13.7.1", True)
        for c in D["chapters"]:
            if c["id"] == hid:
                c.update(label=ch["title"], title_it=ch.get("title_it", ""), record_id=cid)
        it_sections = {s["id"]: s for s in ch.get("sections_it", [])}
        for sec in ch.get("sections", []):
            sid = sec["id"]
            assert sid not in by, sid
            its = it_sections.get(sid, {})
            row = {**sec, "chapter_id": cid, "chapter_hub": hid,
                   "title_it": its.get("title", ""), "file_it": its.get("file", ""),
                   "line_it": its.get("line"), "sha256_it": its.get("sha256", "")}
            section_rows.append(row)
            add_node(node(sid, sec["title"], "published_book_section", "sections",
                          authors="Enrico Papalini", year="2026", actual=[hid], mapped=[hid], volumes=["V06"],
                          attributes={**row, "source_file": sec["file"], "source_line": sec["line"],
                                      "source_sha256": sec["sha256"], "source_version": "13.7.1"}))
            edge(cid, sid, "NDSE2_HAS_SECTION", "provenance",
                 {"source_file": sec["file"], "source_line": sec["line"], "section_number": sec.get("number", "")})
        cite_edges(cid, ch.get("citations", []), "NDSE2_CHAPTER_CITES", hid, "EN")
        cite_edges(cid, ch.get("citations_it", []), "NDSE2_CHAPTER_CITES", hid, "ITA")
        for language, key in (("EN", "citations"), ("ITA", "citations_it")):
            grouped = collections.defaultdict(list)
            for cit in valid_cites(ch.get(key, [])):
                if cit.get("section_id") in by:
                    grouped[(cit["section_id"], cit["source_id"])].append(cit)
            for (sid, source_id), cs in sorted(grouped.items()):
                edge(sid, source_id, "NDSE2_SECTION_CITES", "actual",
                     {"language": language, "literal_citation": True, "citation_count": len(cs),
                      "chapter_hub": hid, "source_version": "13.7.1",
                      "locators_json": json.dumps(cs, ensure_ascii=False)}, language)
        unit_rows.append({"id": cid, "hub_id": hid, "number": ch["number"], "title": ch["title"],
                          "title_it": ch.get("title_it", ""), "literal_source_ids": sorted(set(ch.get("source_ids", []))),
                          "literal_citation_count": len(ch.get("citations", [])), "section_count": len(ch.get("sections", []))})

    for unit in B.get("nonchapter_units", []):
        uid = unit.get("id", "")
        if not uid or "INDEX" in uid.upper() or unit.get("kind") in ("source_identifier_index", "index"):
            continue
        if uid in by:
            continue
        add_node(node(uid, unit.get("title", uid), "published_book_document", "reader",
                      authors="Enrico Papalini", year="2026", volumes=["V06"],
                      summary=unit.get("summary", ""),
                      attributes={"title_it": unit.get("title_it", ""), "source_version": "13.7.1",
                                  "publication_id": PUBLICATION_ID, "provenance": provenance}))
        edge(PUBLICATION_ID, uid, "NDSE2_HAS_DOCUMENT", "provenance")
        cite_edges(uid, unit.get("citations", []), "NDSE2_DOCUMENT_CITES", language="EN")
        cite_edges(uid, unit.get("citations_it", []), "NDSE2_DOCUMENT_CITES", language="ITA")

    bib = B.get("bibliography", {})
    if isinstance(bib, dict) and "EN" in bib:
        bib = bib["EN"]
    bib_records = bib if isinstance(bib, list) else bib.get("records", bib.get("entries", []))
    if isinstance(bib_records, dict):
        bib_records = list(bib_records.values())
    bib_ids = {r.get("source_id") or r.get("bibkey") or r.get("key") or r.get("id") for r in bib_records}
    bib_ids = {f"PUB:V11:{x}" if re.fullmatch(r"V\d\d", str(x)) else x for x in bib_ids}
    if not bib_ids:
        ids = bib.get("source_ids", bib.get("stable_ids", []))
        if isinstance(ids, dict):
            ids = [x for xs in ids.values() for x in xs]
        bib_ids = set(ids)
    # All retained W references are included via the explicit wildcard bibliography.
    assert set(f"W{i:03}" for i in range(1, 194)).issubset(bib_ids), "Bibliography schema must expose all W IDs"
    assert len([x for x in bib_ids if str(x).startswith("F")]) == 11
    for n in D["nodes"]:
        nid = n["id"]
        if n.get("collection") in ("W", "O", "P", "F") or nid.startswith("PUB:V11:") or nid in citation_map or nid in bib_ids:
            actual = sorted(citation_map[nid])
            change(nid, "actual", actual)
            change(nid, "mapped", sorted(set(n.get("mapped", [])) | set(actual)))
            change(nid, "printed", nid in bib_ids)
            change(nid, "ndse2_actual_chapters_json", json.dumps(actual), True)
            change(nid, "ndse2_in_bibliography", nid in bib_ids, True)
            change(nid, "ndse2_citation_basis", "Final 13.7.1 active EN/ITA source tree; index links and nocite are not chapter citations", True)
            if n.get("collection") == "F":
                change(nid, "book_citation_status", "IN_PUBLISHED_NDSE2_BIBLIOGRAPHY" if nid in bib_ids else "COMPANION_READING_NOT_IN_BOOK", True)
                change(nid, "new_manuscript_citation", bool(actual), True)
            if nid in U["meta"]["source_additions"]:
                assert not actual and nid not in bib_ids, "Unexpected new-article citation requires source review"
                change(nid, "manuscript_citation_status", "NOT_CITED_IN_PUBLISHED_NDSE2_13_7_1", True)
                change(nid, "manuscript_citation_basis", "Absent from the final published NDSE2 13.7.1 active EN/ITA source tree and loaded bibliography", True)
    # Current chapter references supersede older display memberships, while every
    # historical node, keyed relationship and source caveat stays in the graph.
    ga = D["meta"]["graphAttributes"]
    ga["historical_v12_fowler_book_changed"] = ga.get("fowler_book_changed")
    ga["fowler_book_changed"] = "PUBLISHED_NDSE2_13_7_1_RECONCILED_11_BIBLIOGRAPHY_9_CHAPTER_SOURCES"
    current_metadata = {
        "portable_atlas_release": "v13.0-static-20261018",
        "portable_atlas_basis": "Author-supplied v12.1 website baseline, four reviewed article additions and final published NDSE2 13.7.1 structure and literal citation layer",
        "portable_atlas_snapshot_date": DATE,
        "orosz_evidence_note": "53 public main articles; 71 inherited restricted records remain provisional; no empirical replication or independent-rater accuracy score",
        "orosz_scope": "Blog plus newsletter Deepdives; reviewed through 2026-10-18 with latest included publication 2026-10-13; literal The Pulse title-prefix and podcast exclusion; cross-source deduplication",
    }
    for field, value in current_metadata.items():
        ga["historical_v12_" + field] = ga.get(field)
        ga[field] = value
    original_attribution = copy.deepcopy(D["meta"].get("fowler_attribution", {}))
    D["meta"]["historical_v12_fowler_attribution"] = original_attribution
    D["meta"]["fowler_attribution"] = {
        **original_attribution,
        "authors": sorted(set(original_attribution.get("authors", [])) | {"Jim Highsmith", "Kuldeep Singh"}),
        "source_count": 35, "snapshot_date": DATE,
        "scope": "33 historical Exploring Generative AI records plus two explicitly identified adjacent-site additions; source-specific credited authorship retained",
        "editor_role": "Birgitta Böckeler's editorship applies to the Exploring Generative AI series; no editorship over adjacent-site additions is inferred",
    }
    D["meta"]["historical_v12_notes"] = copy.deepcopy(D["meta"].get("notes", []))
    D["meta"]["notes"] = [
        "The author-supplied v12.1 website package is the byte-for-byte update baseline.",
        "All 1,757 historical node IDs and all 12,188 keyed edges remain; old display values are retained under historical_v12 fields when changed.",
        "Current actual chapter memberships come from literal citations in the final published EN/ITA NDSE2 13.7.1 sources.",
        "Bibliography membership, identifier-index links, nonchapter citations and editorial reading mappings remain distinct.",
        "N identifies the 13 published NDSE2 chapters; B retains the five earlier books' chapter/file records.",
        "F001–F035 credit individual authors on martinfowler.com; F034/F035 explicitly extend the original series scope.",
        "O051, F034, F035 and P124 are online companion updates and are not cited in the published manuscript.",
        "Publication, source use and collection membership do not establish empirical validation or institutional endorsement.",
        "The original W193-only opening preset, nine streams and historical relationship controls remain available.",
    ]
    for k in ("current_book_edition", "current_book_source_manifest", "current_book_graph_note"):
        ga["historical_v12_" + k] = ga.get(k)
    ga.update(current_book_edition=EDITION_ID,
              current_book_source_manifest="data/updates/ndse2_source_manifest.json",
              current_book_graph_note="Published EN/ITA 13.7.1 citation and section layer; historical v11 edges retained.",
              current_book_publication_id=PUBLICATION_ID, current_chapter_count=13,
              book_publication_status="PUBLISHED_AUTHOR_CONFIRMED_20261018",
              atlas_update="v13.0_20261018", article_update_source="data/updates/source_review_20261018.json",
              osmani_articles=51, fowler_articles=35, orosz_articles=124,
              fowler_scope_update="33 historical Exploring Gen AI records + 2 explicit adjacent-site additions",
              update_empirical_replication=False,
              graphml_key_encoding="atlas_original_key_json contains original keyed-edge identity",
              graphml_atlas_display_encoding="atlas_display contains the complete current normalized node view")
    counts = collections.Counter(e["relation"] for e in D["edges"])
    D["relations"] = [
        {**r, "count": counts[r["id"]]} for r in old["relations"]
    ] + [{"id": r, "label": r.replace("_", " ").title(), "family": relation_family[r], "count": counts[r]}
         for r in sorted(set(counts) - set(original_relations))]
    families = collections.Counter(e["family"] for e in D["edges"])
    D["edgeFamilies"] = [{**f, "count": families[f["id"]]} for f in old["edgeFamilies"]]
    categories = collections.Counter(n["category"] for n in D["nodes"] if not n.get("collection"))
    D["nodeGroups"] = [{**g, "count": categories[g["id"]]} for g in old["nodeGroups"]]
    D["meta"].update(edition="v13.0 · Published NDSE2 and October source update", date=DATE,
                     graphFile="knowledge_graph_v13.graphml", nodeCount=len(D["nodes"]),
                     edgeCount=len(D["edges"]), relationCount=len(D["relations"]),
                     publicationStatus="NDSE2 published; author-confirmed")

    raw = {
        "directed": True, "multigraph": True, "graph": ga,
        "nodes": [{"id": n["id"], **n["attributes"],
                   "atlas_display": {k: v for k, v in n.items() if k != "attributes"}} for n in D["nodes"]],
        "edges": [{"id": e["id"], "source": D["nodes"][e["source"]]["id"],
                   "target": D["nodes"][e["target"]]["id"], "key": e["key"], **e["attributes"],
                   "atlas_family": e["family"]} for e in D["edges"]],
    }
    graph_path = ROOT / "data/graph/knowledge_graph_v13.graphml"
    graphml(raw, graph_path)
    D["meta"]["graphSha256"] = sha(graph_path)
    raw["meta"] = D["meta"]
    write_json(ROOT / "data/graph/knowledge_graph_v13.json", raw)
    write_json(ROOT / "data/graph/atlas_payload_v13.json", D)
    write_json(ROOT / "data/updates/ndse2_source_manifest.json", B.get("source_manifest", {}))
    write_json(ROOT / "data/updates/ndse2_citation_occurrences.json",
               {"meta": {"source_version": "13.7.1", "date": DATE,
                          "basis": "Active literal citations only; source index and nocite excluded"},
                "occurrences": occurrences})
    write_json(ROOT / "data/catalogues/ndse2-sections.json", {"records": section_rows})
    write_json(ROOT / "data/catalogues/ndse2-chapter-citations.json", {"records": unit_rows})
    with (ROOT / "data/catalogues/ndse2-citation-occurrences.csv").open("w", encoding="utf-8-sig", newline="") as f:
        fields = ["language", "chapter_hub", "owner_id", "section_id", "source_id", "bibkey", "macro", "file", "line", "sha256"]
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(occurrences)
    audit = {
        "as_of": DATE, "baseline_nodes": len(old["nodes"]), "baseline_edges": len(old["edges"]),
        "nodes": len(D["nodes"]), "edges": len(D["edges"]), "relation_types": len(D["relations"]),
        "source_counts": dict(collections.Counter(n["collection"] for n in D["nodes"] if n.get("collection"))),
        "added_nodes": added_node_ids, "added_edges": added_edge_ids,
        "current_display_or_metadata_changes": changes,
        "all_original_node_ids_retained": old_node_ids.issubset(by),
        "all_original_edges_identical": D["edges"][:len(old["edges"])] == old["edges"],
        "chapter_count": len(chapters), "section_count": len(section_rows),
        "literal_occurrences": len(occurrences), "literal_chapter_source_pairs": sum(len(v) for v in citation_map.values()),
        "current_bibliography_source_ids": sorted(x for x in bib_ids if x in by),
        "unresolved_citations": unresolved, "book_audit": B.get("audit", {}),
        "current_citations_by_source": {k: sorted(v) for k, v in sorted(citation_map.items()) if v},
        "scope": "Publication and literal use do not establish empirical validity; historical audit boundaries retained",
    }
    write_json(ROOT / "verification/graph_update_checks.json", audit)
    # The reusable code template is patched separately, then receives this payload.
    from atlas_v13_template import patch_template
    template = patch_template(base_html, D)
    embedded = json.dumps(D, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace("&", "\\u0026")
    current = re.sub(r'(<script id="graph-data" type="application/json">).*?(</script>)',
                     lambda m: m.group(1) + embedded + m.group(2), template, count=1, flags=re.S)
    (SOURCE / "atlas_v13_current.html").write_text(current, encoding="utf-8")
    print(json.dumps({k: audit[k] for k in ("nodes", "edges", "relation_types", "source_counts", "chapter_count", "section_count", "literal_chapter_source_pairs")}))


if __name__ == "__main__":
    main()
