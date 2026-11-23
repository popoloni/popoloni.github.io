#!/usr/bin/env python3
"""Check the Atlas book release against the pinned live baseline and editorial review.

Run with Python 3.10+ and a clean copy of the baseline recorded in
source/book_chapter_review.json. Uses the standard library only.
"""
import argparse
import collections
import copy
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def indexed(rows):
    return {row["id"]: row for row in rows}


class Audit:
    def __init__(self):
        self.failures = []
        self.checks = collections.Counter()

    def check(self, test, valid, detail=""):
        self.checks[test] += 1
        if not valid:
            self.failures.append({"test": test, "detail": detail})


def xml_text(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value)


def check_graphml(raw, path, audit):
    ns = "{http://graphml.graphdrawing.org/xmlns}"
    tree = ET.parse(path).getroot()
    keys = {item.get("id"): (item.get("for"), item.get("attr.name")) for item in tree.findall(ns + "key")}
    graph = tree.find(ns + "graph")
    audit.check("directed exports", raw["directed"] and raw["multigraph"] and
                graph.get("edgedefault") == "directed")
    raw_by_scope = {scope: indexed(raw[scope + "s"]) for scope in ("node", "edge")}
    for scope in ("graph", "node", "edge"):
        seen = set()
        for el in ([graph] if scope == "graph" else graph.iterfind(ns + scope)):
            identity = el.get("id")
            data = el.findall(ns + "data")
            actual = {keys[x.get("key")][1]: x.text or "" for x in data}
            audit.check("GraphML attribute keys", len(data) == len(actual) and
                        all(keys[x.get("key")][0] == scope for x in data), identity)
            if scope == "graph":
                expected = raw["graph"]
            else:
                row = raw_by_scope[scope].get(identity)
                audit.check("GraphML identity", row is not None and identity not in seen, identity)
                if row is None:
                    continue
                seen.add(identity)
                expected = {k: v for k, v in row.items() if k != "id"}
                if scope == "edge":
                    audit.check("GraphML endpoints", all(expected.pop(k) == el.get(k)
                                for k in ("source", "target")), identity)
                    expected["atlas_original_key_json"] = json.dumps(expected.pop("key"), ensure_ascii=False)
                    expected["atlas_edge_id"] = identity
            audit.check("GraphML attributes", actual == {k: xml_text(v) for k, v in expected.items()}, identity)
        if scope != "graph":
            audit.check("GraphML complete", seen == set(raw_by_scope[scope]), scope)


def check_exports(site, normalized, raw, audit):
    nlist = normalized["nodes"]
    nodes, edges = indexed(raw["nodes"]), indexed(raw["edges"])
    for name, rows, other in (("nodes", nlist, nodes), ("edges", normalized["edges"], edges)):
        actual = {r["id"] for r in rows}
        audit.check("unique IDs and equal ID sets", len(actual) == len(rows) == len(raw[name]) and actual == set(other), name)
    for n in nlist:
        expected = {**n["attributes"], "id": n["id"],
                    "atlas_display": {k: v for k, v in n.items() if k != "attributes"}}
        audit.check("normalized and raw nodes", nodes.get(n["id"]) == expected, n["id"])
    keys = set()
    for e in normalized["edges"]:
        row = edges.get(e["id"])
        valid_endpoints = all(type(e[k]) is int and 0 <= e[k] < len(nlist) for k in ("source", "target"))
        audit.check("normalized endpoints", valid_endpoints, e["id"])
        if not valid_endpoints:
            continue
        a, b = [nlist[e[k]]["id"] for k in ("source", "target")]
        key = (a, b, json.dumps(e["key"], ensure_ascii=False))
        audit.check("unique directed multiedge key", key not in keys, e["id"])
        keys.add(key)
        expected = {**e["attributes"], "source": a, "target": b, "key": e["key"], "id": e["id"],
                    "atlas_family": e["family"]}
        audit.check("normalized and raw edges", expected == row and e["relation"] == expected["relation"], e["id"])
    relations = collections.Counter(e["relation"] for e in raw["edges"])
    family_counts = collections.Counter(e["atlas_family"] for e in raw["edges"])
    for key, count in (("relations", relations), ("edgeFamilies", family_counts)):
        declared = normalized[key]
        audit.check("declared classification totals", len(indexed(declared)) == len(declared) and
                    {r["id"]: r["count"] for r in declared if r["count"]} == dict(count), key)
    gml = site / "data/graph/knowledge_graph_current.graphml"
    meta = normalized["meta"]
    audit.check("export metadata", meta == raw["meta"] and meta["nodeCount"] == len(nlist) and
                meta["edgeCount"] == len(keys) and meta["graphSha256"] == sha(gml))
    check_graphml(raw, gml, audit)


def check_prior_graph(baseline, site, normalized, raw, review, audit):
    prior_path = baseline / "data/graph/atlas_payload_current.json"
    audit.check("pinned baseline", sha(prior_path) == review["baseline_payload_file_sha256"])
    old = load(baseline / "data/graph/knowledge_graph_current.json")
    old_normal = load(prior_path)
    nodes, edges = indexed(raw["nodes"]), indexed(raw["edges"])
    current_display = indexed(normalized["nodes"])
    for was in old["edges"]:
        expected = was.copy()
        for field in ("source", "target"):
            if expected[field] == "V05":
                expected[field] = "V05-H"
        current = edges.get(was["id"])
        audit.check("preserved baseline edge and citation attributes", current == expected, was["id"])
    for was in old_normal["nodes"]:
        id_ = was["id"]
        n = nodes.get("V05-H" if id_ == "V05" else id_, {}).get("atlas_display", {})
        audit.check("historical identities present", bool(n), id_)
        expected = copy.deepcopy(was)
        if id_ == "V05":
            expected["id"] = "V05-H"
            expected["label"] += " (self-published edition)"
            expected["attributes"]["label"] = expected["label"]
        if "V05" in was.get("volumes", []):
            expected["volumes"] = ["V05-H" if v == "V05" else v for v in was["volumes"]]
            if expected["attributes"].get("volume_id") == "V05":
                expected["attributes"].update(volume_id="V05-H", original_atlas_volume_id="V05")
            if expected.get("book", {}).get("volume") == "V05":
                expected["book"]["volume"] = "V05-H"
            if was["kind"] == "practice_occurrence":
                expected["summary"] = expected["summary"].replace("retained V05 source",
                                                                  "retained self-published Loop Engineering source")
        if id_ == "PUB:V11:V05":
            expected["kind"] = "archived_book_edition"
            expected["attributes"].update(kind="archived_book_edition", edition_status="Historical self-published edition")
        audit.check("all baseline node fields retained except declared edition migration",
                    current_display.get(expected["id"]) == expected, id_)
        for k in ("actual", "mapped", "printed"):
            audit.check("literal and historic chapter overlay retained", was.get(k) == n.get(k), f"{id_} {k}")
        if "V05" in was.get("volumes", []):
            audit.check("prior Loop connections assigned to historical volume", "V05-H" in n.get("volumes", []), id_)
        if re.fullmatch(r"B10[2-9]|B11[01]", id_):
            old_attrs = was["attributes"]
            new_attrs = nodes[id_]
            audit.check("old card source and bibliographic identity", all(new_attrs.get(k) == old_attrs.get(k)
                        for k in ("source_path", "source_sha256")) and n["label"] == was["label"], id_)
    old_cites = {e["id"] for e in old["edges"] if e["relation"].startswith("NDSE2_") and "CITES" in e["relation"]}
    new_cites = {e["id"] for e in raw["edges"] if e["relation"].startswith("NDSE2_") and "CITES" in e["relation"]}
    audit.check("literal NDSE2 citation set", old_cites == new_cites)
    for path in ("data/catalogues/ndse2-chapter-citations.json", "data/catalogues/ndse2-sections.json",
                 "data/catalogues/ndse2-citation-occurrences.csv", "data/updates/ndse2_citation_occurrences.json",
                 "data/updates/ndse2_source_manifest.json", "source/ndse2_book.json"):
        audit.check("literal NDSE2 files", (site / path).read_bytes() == (baseline / path).read_bytes(), path)
    frozen = list((baseline / "data/graph").glob("*_v1[23].*"))
    for file in frozen:
        audit.check("frozen graph snapshots", file.read_bytes() == (site / file.relative_to(baseline)).read_bytes(), file.name)
    return set(indexed(old["edges"]))


def check_archive(site, audit):
    data = site / "data"
    with zipfile.ZipFile(data / "catalogue-data.zip") as z:
        members = [p for p in z.namelist() if not p.endswith("/")]
        audit.check("catalogue archive integrity", len(members) == len(set(members)) and z.testzip() is None)
        for p in members:
            dest = (site / "source/book_chapter_review.json" if p == "books/book_chapter_review.json" else data / p)
            valid = dest.resolve().is_relative_to(site.resolve()) and dest.is_file()
            audit.check("catalogue archive matches disk", valid and z.read(p) == dest.read_bytes(), p)
        expected = {p.relative_to(data).as_posix() for folder in ("catalogues", "originals")
                    for p in (data / folder).rglob("*") if p.is_file()}
        audit.check("complete catalogue archive", expected.issubset(members), sorted(expected - set(members)))

# Checked against the respective final print tables of contents. Page numbers use the 7 × 10 trim for ESA.
CHAPTER_STARTS = {
    "PACKT": [
        ('Loop Engineering for AI Agents: A Critical Assessment', 3),
        ('The Organization Becomes a Loop', 37),
        ('The Economics of Loop Engineering', 67),
        ('The Ralph Loop: Persistent Progress Through Fresh Context', 101),
        ('Building a Full Local AI Loop', 133),
        ('Choosing the Right Loop', 185),
    ],
    "ESA": [
        ('The first accountable change', 2),
        ('From need to a verifiable outcome', 16),
        ('Specify behavior and acceptance', 29),
        ('Context, memory, tools and agent boundaries', 43),
        ('Design and prototype alternatives', 59),
        ('Plan, delegate and orchestrate', 72),
        ('Implement and debug a bounded change', 88),
        ('Verify the contract independently', 103),
        ('Review, integrate and release with evidence', 120),
        ('Evolve with compatible history', 136),
        ('Diagnose the system that actually ran', 150),
        ('Learning, adoption and the whole cost', 161),
    ],
}

PUBLICATION = {"PACKT": "PUB:PACKT", "NDSE2": "PUB:NDSE2", "SDD": "PUB:V11:V03", "ESA": "PUB:ESA"}


def check_edition_maps(site, normalized, raw, review, historic, audit):
    nodes = indexed(raw["nodes"])
    new_edges = [e for e in raw["edges"] if e["id"] not in historic]
    actual = collections.Counter((e["source"], e["relation"], e["target"]) for e in new_edges)
    outgoing = collections.defaultdict(list)
    for e in new_edges:
        outgoing[(e["source"], e["relation"], e["target"])].append(e)
        audit.check("new relationship documented", bool(e.get("rationale") and e.get("source_locator")
                    and (site / e["provenance"]).is_file()), e["id"])
    expected = collections.Counter()
    def relationship(source, rel, target, locator=None, rationale=None):
        key = (source, rel, target)
        expected[key] += 1
        audit.check("reviewed endpoint and locator", any((locator is None or e.get("source_locator") == locator)
                    and (rationale is None or e.get("rationale") == rationale) for e in outgoing[key]), list(key))
    pub_catalogue = indexed_by_volume(load(site / "source/book_publications.json")["books"])
    registered = load(site / "source/book_publications.json")["archived_books"]
    audit.check("active and historical Loop editions", pub_catalogue["V05"]["node_id"] == "PUB:PACKT" and
                "V05-H" not in pub_catalogue and any(x["volume_id"] == "V05-H" for x in registered) and
                nodes["PUB:V11:V05"]["kind"] == "archived_book_edition")
    unique_topics = set()
    known_chapters = set()
    for book in review["books"]:
        code, vol = book["code"], book["volume"]
        owner = PUBLICATION[code]
        audit.check("active book metadata", nodes[owner]["title"] == book["title"] and
                    nodes[owner]["url"] == book["url"] and nodes[owner]["subtitle"] == book["subtitle"] and
                    nodes[vol]["label"] == book["title"], owner)
        pub_row = pub_catalogue[vol]
        audit.check("edition cover bytes", (site / pub_row["cover_image"]).is_file() and
                    sha(site / pub_row["cover_image"]) == pub_row["cover_sha256"], vol)
        if code == "PACKT":
            audit.check("Packt edition identifiers", nodes[owner].get("isbn") == "9781808766411" and
                        nodes[owner].get("ebook_isbn") == "9781808766404" and "packtpub.com" in book["url"])
        else:
            audit.check("ESA edition identifier", pub_row["amazon_asin"] == "B0HSPH86CG")
        relationship(owner, "BOOK_PUBLICATION_VOLUME", vol)
        starts = CHAPTER_STARTS[code]
        rows = book["chapters"]
        audit.check("TOC cardinality", len(rows) == len(starts), code)
        covered = set()
        for number, ((title, page), c) in enumerate(zip(starts, rows), 1):
            nid = f"{code}:C{number:02}"
            known_chapters.add(nid)
            n = nodes[nid]
            audit.check("TOC identity and print location", c["id"] == nid and c["number"] == n["chapter_number"] == number
                        and c["title"] == n["label"] == title and c["print_page"] == n["print_page"] == page and
                        n["volume_id"] == vol and n["volume_title"] == book["title"] and n["kind"] == "published_book_chapter", nid)
            if code == "ESA":
                audit.check("EPUB chapter anchor", n.get("epub_locator", "").endswith(f"#chapter-{number}"), nid)
            relationship(nid, "BOOK_CHAPTER_OF", owner, c["source_locator"])
            if c.get("predecessor_card"):
                relationship(nid, "HISTORICAL_CHAPTER_COUNTERPART", c["predecessor_card"])
            audit.check("distinct chapter topics and streams", bool(c["topics"] and c["streams"]) and
                        len({t["id"] for t in c["topics"]}) == len(c["topics"]) and
                        len(set(c["streams"])) == len(c["streams"]), nid)
            for t in c["topics"]:
                covered.add(t["id"])
                relationship(nid, "BOOK_CHAPTER_TOPIC", t["id"], c["source_locator"], t["rationale"])
            for stream in c["streams"]:
                relationship(nid, "BOOK_CHAPTER_STREAM", stream)
            audit.check("chapter display classifications", set(n["atlas_display"]["topics"]) == {t["id"] for t in c["topics"]}
                        and set(n["atlas_display"]["streams"]) == set(c["streams"]), nid)
            for field, kind in (("related_reading", "BOOK_RELATED_READING"), ("external_reading", "BOOK_CHAPTER_COMPANION_READING"),
                                ("practice", "BOOK_CHAPTER_PRACTICE")):
                r = c[field]
                relationship(nid, kind, r["id"], c["source_locator"], r["rationale"])
        audit.check("exact aggregate book topics", covered == set(nodes[owner]["atlas_display"]["topics"]), owner)
        for topic in covered:
            relationship(owner, "BOOK_COVERS_TOPIC", topic)
        unique_topics.update(covered)
    audit.check("only the eighteen numbered chapters", {n["id"] for n in raw["nodes"]
                if n.get("kind") == "published_book_chapter" and n.get("volume_id") in ("V05", "V07")} == known_chapters)
    for t in review["new_topics"]:
        audit.check("new topic is defined, discoverable and used", nodes[t["id"]].get("definition") == t["definition"] and
                    t["id"] in unique_topics and indexed(normalized["topics"])[t["id"]]["label"] == t["label"], t["id"])
    relationship("PUB:V11:V05", "BOOK_EDITION_SUCCESSOR", "PUB:PACKT")
    for edition in ("PUB:V11:V01", "PUB:NDSE2"):
        relationship(edition, "BOOK_EDITION_OF_WORK", "WORK:NDSE")
    packt = next(b for b in review["books"] if b["code"] == "PACKT")
    for r in packt["intellectual_lineage"]:
        relationship("PUB:PACKT", r["relation"], r["target"], packt["lineage_locator"], r["rationale"])
    esa = next(b for b in review["books"] if b["code"] == "ESA")
    for group, prefix, kind in (("missions", "M", "book_mission"), ("appendices", "A", "book_appendix")):
        wanted_codes = ({f"{route}{i}" for route in "GB" for i in range(1, 5)} if group == "missions" else set("ABC"))
        audit.check("supplement inventory", {r["id"] for r in esa[group]} == wanted_codes, group)
        for r in esa[group]:
            sid = f"ESA:{prefix}:{r['id']}"
            s = nodes[sid]
            audit.check("supplement is located in correct edition", s["volume_id"] == "V07" and s["kind"] == kind and
                        s["label"] == r["title"] and s["print_page"] == r["print_page"] and
                        r["epub_locator"] in s["source_locator"], sid)
            relationship(sid, "BOOK_SUPPLEMENT_OF", "PUB:ESA")
            for c in r.get("preparatory_chapters", []):
                relationship(f"ESA:C{c:02}", "BOOK_CHAPTER_PREPARES_MISSION", sid)
    for r in esa["explicit_preface_relations"]:
        relationship("PUB:ESA", "BOOK_PREFACE_RELATES_VOLUME", PUBLICATION[r["target"]], r["source"])
    for group in ("explicit_cross_references", "front_and_back_matter_crossrefs"):
        for r in esa[group]:
            code = r.get("target_book", r.get("target"))
            targets = r.get("atlas_target_chapter_ids") or [f"{code}:C{i:02}" for i in r["target_chapters"]]
            source = f"ESA:C{r['esa_chapter']:02}" if "esa_chapter" in r else "PUB:ESA"
            rel = "BOOK_CITES_CHAPTER" if targets else "BOOK_CITES_VOLUME"
            for target in targets or [PUBLICATION[code]]:
                if code == "SDD" and target.startswith("B"):
                    audit.check("SDD citation resolves to second edition", nodes[target].get("source_path", "").startswith("AI_SDD_ENG_V2/"), target)
                relationship(source, rel, target, r.get("source", r.get("esa_locator")), r["description"])
    audit.check("exact reviewed relationship multiset", actual == expected, {
        "missing": [[*k, n] for k, n in (expected - actual).items()],
        "extra": [[*k, n] for k, n in (actual - expected).items()]})
    return dict(nodes=len(nodes), edges=len(raw["edges"]), preserved_edges=len(historic), new_edges=len(new_edges),
                chapters=len(known_chapters), topics=len(unique_topics), supplements=len(esa["missions"]) + len(esa["appendices"]))


def indexed_by_volume(rows):
    return {r["volume_id"]: r for r in rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit = Audit()
    counts = {}
    try:
        site, baseline = args.site.resolve(), args.baseline.resolve()
        normalized = load(site / "data/graph/atlas_payload_current.json")
        raw = load(site / "data/graph/knowledge_graph_current.json")
        review = load(site / "source/book_chapter_review.json")
        check_exports(site, normalized, raw, audit)
        historic = check_prior_graph(baseline, site, normalized, raw, review, audit)
        counts = check_edition_maps(site, normalized, raw, review, historic, audit)
        check_archive(site, audit)
    except (ValueError, KeyError, TypeError, IndexError, OSError, ET.ParseError, zipfile.BadZipFile) as exc:
        audit.check("readable complete release", False, f"{type(exc).__name__}: {exc}")
    result = {"passed": not audit.failures, "counts": counts, "checks": dict(audit.checks),
              "failures": audit.failures}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{sum(audit.checks.values()):,} assertions; {len(audit.failures)} failures")
    return int(bool(audit.failures))


if __name__ == "__main__":
    sys.exit(main())
