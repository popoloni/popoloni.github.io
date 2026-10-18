#!/usr/bin/env python3
"""Independent offline checks for a generated Knowledge Atlas successor release.

Python 3.10+, standard library only. No network access and no baseline mutation.
Import validate_site(site_root, baseline_payload=None, expected_changes=None,
book=None), or run with --site/--baseline/--changes/--book/--output. Inputs can
be dictionaries or JSON paths; a baseline can also be an HTML graph or site
directory. Output counts always come from the supplied artifact and manuscript.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import html.parser
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

GRAPH_RE = re.compile(r'<script\b[^>]*\bid=["\']graph-data["\'][^>]*>(.*?)</script>', re.S | re.I)
EXCLUDED_PARTS = {"__pycache__", ".git", ".pytest_cache", "node_modules"}
GRAPH_NS = {"g": "http://graphml.graphdrawing.org/xmlns"}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def artifact_inventory(root):
    """Content binding shared with browser_check.js; reports/checksums excluded."""
    root = Path(root).resolve()
    rows = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if (EXCLUDED_PARTS.intersection(rel.parts) or rel.parts[0] == "verification"
                or rel.as_posix() == "SHA256SUMS.txt" or path.name == ".DS_Store"
                or path.suffix in (".pyc", ".pyo")):
            continue
        if path.is_symlink():
            raise ValueError("Artifact has a symbolic link: " + rel.as_posix())
        if path.is_file():
            rows.append({"path": rel.as_posix(), "sha256": digest(path), "size": path.stat().st_size})
    return sorted(rows, key=lambda row: row["path"])


def artifact_sha256(root):
    data = json.dumps(artifact_inventory(root), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def extract_graph(text):
    found = GRAPH_RE.search(text)
    if not found:
        raise ValueError("HTML does not contain a graph-data JSON script")
    return json.loads(found.group(1))


def load_input(value, *, graph=False):
    if value is None or isinstance(value, dict):
        return value
    path = Path(value)
    if path.is_dir():
        path = path / "swe_knowledge_graph.html"
    text = path.read_text(encoding="utf-8")
    return extract_graph(text) if graph and path.suffix.lower() in (".html", ".htm") else json.loads(text)


def canonical_url(value):
    if not value:
        return ""
    u = urlsplit(value.strip())
    query = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    return urlunsplit((u.scheme.lower(), u.netloc.lower(), u.path.rstrip("/") or "/", urlencode(sorted(query)), ""))


class PageParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids, self.links, self.records, self.images = [], [], [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.append(attrs["id"])
        if "data-record" in attrs:
            self.records.append(attrs.get("id"))
        for attribute in ("href", "src", "poster"):
            if attrs.get(attribute):
                self.links.append((tag, attribute, attrs[attribute]))
        if tag == "img":
            self.images.append(attrs)


def validate_site(site_root, baseline_payload=None, expected_changes=None, book=None):
    root = Path(site_root).resolve()
    checks, fatal, graph, config = [], None, {}, {}
    stats = {}

    def check(name, passed, detail=None):
        result = {"check": name, "passed": bool(passed)}
        if detail is not None:
            result["detail"] = detail
        checks.append(result)
        return bool(passed)

    try:
        config = read_json(root / "source/site_config.json")
        changes = load_input(expected_changes) or {}
        book = load_input(book) or read_json(root / config.get("book_json", "source/ndse2_book.json"))
        html_path = root / config.get("graph_html", "swe_knowledge_graph.html")
        graph_html = html_path.read_text(encoding="utf-8")
        graph = extract_graph(graph_html)
        baseline = load_input(baseline_payload, graph=True)
        baseline_html = None
        if isinstance(baseline, dict) and "payload" in baseline:
            baseline_html = baseline.get("html")
            baseline = load_input(baseline["payload"], graph=True)
        if baseline_payload is not None and not isinstance(baseline_payload, dict):
            path = Path(baseline_payload)
            if path.is_dir():
                path = path / "swe_knowledge_graph.html"
            if path.suffix.lower() in (".html", ".htm"):
                baseline_html = path.read_text(encoding="utf-8")
        if changes.get("baseline_html"):
            baseline_html = Path(changes["baseline_html"]).read_text(encoding="utf-8")
        if baseline_html is None:
            original_template = root / config.get("original_template", "source/atlas_v12_original.html")
            if original_template.exists():
                baseline_html = original_template.read_text(encoding="utf-8")
        if baseline is None and baseline_html:
            baseline = extract_graph(baseline_html)

        nodes = graph["nodes"]
        edges = graph["edges"]
        by_id = {n["id"]: n for n in nodes}
        check("Node IDs are unique", len(by_id) == len(nodes))
        check("Keyed-edge IDs are unique", len({e["id"] for e in edges}) == len(edges))
        check("Every graph edge endpoint is a valid node index", all(type(e[k]) is int and 0 <= e[k] < len(nodes) for e in edges for k in ("source", "target")))
        counts = dict(collections.Counter(n.get("collection") for n in nodes if n.get("collection")))
        relations = dict(collections.Counter(e["relation"] for e in edges))
        check("Relation metadata and counts equal the exact graph", {r["id"]: r["count"] for r in graph["relations"]} == relations)
        if baseline is None:
            check("A baseline payload is available for preservation checks", False)
        else:
            check("Every baseline node ID retains its original position", [n["id"] for n in nodes[:len(baseline["nodes"])]] == [n["id"] for n in baseline["nodes"]])
            check("Every baseline keyed edge remains byte-equivalent as the graph prefix", edges[:len(baseline["edges"])] == baseline["edges"], {"baseline_edges": len(baseline["edges"])})
        before = re.search(r"const defaultState\s*=.*?;", baseline_html or "")
        after = re.search(r"const defaultState\s*=.*?;", graph_html)
        check("Original Polimi defaultState is unchanged", bool(before and after and before.group() == after.group()))

        template_path = root / "source" / config["atlas_source"]
        check("The configured source template embeds the delivered graph", extract_graph(template_path.read_text(encoding="utf-8")) == graph)
        raw_path = root / config["graph_json"]
        raw = read_json(raw_path)
        payload_setting = config.get("payload_json") or config.get("atlas_payload_json") or config.get("graph_payload")
        payload_path = root / payload_setting if payload_setting else raw_path.with_name(raw_path.name.replace("knowledge_graph", "atlas_payload"))
        check("The normalized JSON export equals the delivered graph", payload_path.exists() and read_json(payload_path) == graph, str(payload_path.relative_to(root)))
        validate_exports(root, config, graph, raw, check)
        validate_book(root, config, graph, book, changes, check)
        if config.get('practice_content_schema') or graph.get('meta', {}).get('practices') or any(n.get('collection') == 'PAT' for n in nodes) or (baseline and any(n.get('collection') == 'PAT' for n in baseline['nodes'])):
            from practices_checks import validate_practices
            practice_report = validate_practices(graph, baseline, book, required=bool(config.get('practice_content_schema')))
            for item in practice_report['checks']:
                check('Practices: ' + item['check'], item['passed'], item.get('detail'))
            expected_sources = [n for n in nodes if n.get('collection') in {c['code'] for c in config['collections']} and n.get('collection') != 'PAT']
            source_export = read_json(root / 'data/catalogues/all-sources.json')
            check('All-sources export keeps bibliographic and chapter records separate from practices', source_export['records'] == expected_sources)

        added = changes.get("source_additions", changes.get("new_source_ids", changes.get("additions", changes.get("meta", {}).get("source_additions", []))))
        added = [v.get("id") if isinstance(v, dict) else v for v in added]
        if not added and baseline:
            prior = {n["id"] for n in baseline["nodes"]}
            added = [n["id"] for n in nodes if n["id"] not in prior and n.get("collection") in ("O", "P", "F", "W")]
        check("Declared new source IDs are unique and present", len(added) == len(set(added)) and all(i in by_id for i in added), added)
        urls = collections.defaultdict(list)
        for node in nodes:
            if node.get("collection") in ("O", "P", "F", "W"):
                url = canonical_url(node.get("attributes", {}).get("canonical_url") or node.get("url", ""))
                if url:
                    urls[url].append(node["id"])
        duplicates = {u: ids for u, ids in urls.items() if len(ids) > 1 and set(ids).intersection(added)}
        check("New source URLs do not duplicate an existing catalogue record", not duplicates, duplicates)
        malformed = [i for i in added if i in by_id and urlsplit(by_id[i].get("url", "")).scheme not in ("http", "https")]
        check("New source URLs are explicit HTTP or HTTPS sources", not malformed, malformed)

        parsed = {}
        for file in sorted(root.rglob("*.html")):
            rel = file.relative_to(root)
            if rel.parts[0] in ("source", "data") or EXCLUDED_PARTS.intersection(rel.parts):
                continue
            parser = PageParser()
            parser.feed(file.read_text(encoding="utf-8"))
            parsed[rel.as_posix()] = parser
            check("Unique HTML anchors: " + rel.as_posix(), len(parser.ids) == len(set(parser.ids)))
            check("Images have an alt attribute: " + rel.as_posix(), all("alt" in a for a in parser.images))
        problems, external, runtime_remote, local_count = [], set(), [], 0
        for name, parser in list(parsed.items()):
            for tag, attribute, link in parser.links:
                u = urlsplit(link)
                if u.scheme in ("http", "https") or u.netloc:
                    external.add(link)
                    if tag in ("script", "img", "link", "iframe", "source", "video", "audio"):
                        runtime_remote.append([name, link])
                    continue
                if u.scheme:
                    continue
                part = unquote(u.path)
                dest = (root / part.lstrip("/")).resolve() if part.startswith("/") else ((root / name).parent / part).resolve() if part else (root / name).resolve()
                if not dest.is_relative_to(root):
                    problems.append([name, link, "escapes website root"])
                    continue
                if dest.is_dir():
                    dest /= "index.html"
                if not dest.is_file():
                    problems.append([name, link, "missing file"])
                    continue
                local_count += 1
                if u.fragment and dest.suffix.lower() in (".html", ".htm"):
                    key = dest.relative_to(root).as_posix()
                    if key not in parsed:
                        parser2 = PageParser()
                        parser2.feed(dest.read_text(encoding="utf-8"))
                        parsed[key] = parser2
                    if unquote(u.fragment) not in parsed[key].ids:
                        problems.append([name, link, "missing fragment"])
        check("All published HTML local links and anchors resolve", not problems, {"checked": local_count, "errors": problems})
        check("Published HTML declares no external runtime dependency", not runtime_remote, runtime_remote)
        config_codes = {c["code"] for c in config["collections"]}
        check("Every graph collection has a configured static catalogue", set(counts).issubset(config_codes))
        for collection in config["collections"]:
            code, slug = collection["code"], collection["slug"]
            wanted = [n for n in nodes if n.get("collection") == code]
            page_name = "catalogues/" + slug + ".html"
            check("Static catalogue IDs match graph: " + code, page_name in parsed and parsed[page_name].records == [n["id"] for n in wanted])
            catalogue = read_json(root / "data/catalogues" / (slug + ".json"))
            check("Catalogue JSON preserves all graph display attributes: " + code, catalogue["records"] == wanted)
        for slug, kind in (("practices", "practice_descriptor"), ("occurrences", "practice_occurrence")):
            name = "catalogues/" + slug + ".html"
            check("Static catalogue IDs match graph: " + slug, name in parsed and parsed[name].records == [n["id"] for n in nodes if n["kind"] == kind])
        markdown_errors = []
        for doc in ("README.md", "DEPLOYMENT.md", "ATTRIBUTION.md"):
            file = root / doc
            if not file.exists():
                markdown_errors.append([doc, "missing document"])
                continue
            for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", file.read_text(encoding="utf-8")):
                u = urlsplit(link)
                if not u.scheme and not u.netloc:
                    target = (root / unquote(u.path)).resolve()
                    if not target.is_relative_to(root) or not target.is_file():
                        markdown_errors.append([doc, link])
        check("Top-level documentation local file links resolve", not markdown_errors, markdown_errors)
        check("GitHub Pages nojekyll marker is retained", (root / ".nojekyll").is_file())
        check("No book manuscripts or third-party full-text PDFs are packaged", not any(p.is_file() and p.suffix.lower() in (".tex", ".pdf") for p in root.rglob("*")))
        check("Every site file stays below the configured upload size limit", all(p.stat().st_size < config.get("max_file_bytes", 25 * 1024 * 1024) for p in root.rglob("*") if p.is_file()))
        # Frozen original assets remain a regression contract, independent of a release date.
        for manifest_name, entries in frozen_manifests(root):
            errors = [p for p, sha in entries if not (root / p).is_file() or digest(root / p) != sha]
            check("Frozen source bytes retained: " + manifest_name, not errors, errors)
        stats = {"graph_nodes": len(nodes), "graph_edges": len(edges), "graph_relation_types": len(relations), "source_counts": counts,
                 "html_pages_checked": len(parsed), "internal_links_checked": local_count, "distinct_external_links": len(external),
                 "new_source_ids": added, "graph_html_sha256": digest(html_path), "artifact_sha256": artifact_sha256(root)}
    except Exception as error:
        fatal = {"type": type(error).__name__, "message": str(error)}
        check("Validation completed without a fatal error", False, fatal)
    return {"schema_version": 1, "kind": "atlas_structural_validation", "complete": fatal is None,
            "checked_at": datetime.now(timezone.utc).isoformat(), "site_version": config.get("site_version"),
            "graph_snapshot": graph.get("meta", {}).get("date"), "passed": sum(c["passed"] for c in checks),
            "failed": sum(not c["passed"] for c in checks), "checks": checks, "error": fatal,
            "artifact_scope": "All site file paths, SHA-256 and sizes except verification/, SHA256SUMS.txt and development caches.",
            "external_urls_live_checked": False, **stats}


def frozen_manifests(root):
    path = root / "source/baseline_provenance.json"
    if path.exists():
        rows = read_json(path).get("preserved_files", {})
        yield path.name, [(name, row["sha256"]) for name, row in rows.items()]
    path = root / "source/original_catalogue_provenance.json"
    if path.exists():
        yield path.name, [(row["file"], row["sha256"]) for row in read_json(path)]


def validate_book(root, config, graph, book, changes, check):
    nodes = {n["id"]: n for n in graph["nodes"]}
    chapters = book["chapters"]
    ids = [c["id"] for c in chapters]
    check("Published chapter records exactly match the supplied book", [n["id"] for n in graph["nodes"] if n.get("collection") == "N"] == ids and len(ids) == len(set(ids)), {"chapters": len(ids)})
    sections = [s for c in chapters for s in c["sections"]]
    check("Published section nodes exactly match the supplied book", {s["id"] for s in sections} == {n["id"] for n in graph["nodes"] if n["kind"] == "published_book_section"}, {"sections": len(sections)})
    check("English and Italian chapter source sets and section IDs align", all(set(c["source_ids"]) == set(c["source_ids_it"]) and [s["id"] for s in c["sections"]] == [s["id"] for s in c["sections_it"]] for c in chapters))
    membership, expected, occurrences, totals = collections.defaultdict(set), collections.defaultdict(lambda: collections.defaultdict(list)), [], collections.Counter()
    defaults = {"chapter": "NDSE2_CHAPTER_CITES", "section": "NDSE2_SECTION_CITES", "document": "NDSE2_DOCUMENT_CITES"}
    supplied_relations = changes.get("current_citation_relations")
    names = supplied_relations if isinstance(supplied_relations, dict) else defaults
    for unit in chapters + [u for u in book.get("nonchapter_units", []) if u["id"] != "NDSE2:INDEX"]:
        is_chapter = unit["id"] in ids
        for language, field in (("EN", "citations"), ("ITA", "citations_it")):
            for citation in unit.get(field, []):
                sid = citation["source_id"]
                relation = names["chapter"] if is_chapter else names["document"]
                expected[relation][(unit["id"], sid, language)].append(citation)
                if is_chapter:
                    membership[sid].add(unit["hub_id"])
                    totals[language] += 1
                    if citation.get("section_id"):
                        expected[names["section"]][(citation["section_id"], sid, language)].append(citation)
                occurrences.append({**citation, "language": language, "owner_id": unit["id"]})
    bib_ids = {e["source_id"] for e in book["bibliography"]["EN"]["entries"]}
    check("Book citations and bibliography resolve to graph nodes", set(membership).union(bib_ids).issubset(nodes))
    current_ids = {n["id"] for n in graph["nodes"] if n.get("collection") in ("W", "O", "P", "F")} | set(membership) | bib_ids
    current_ids |= {n["id"] for n in graph["nodes"] if n["id"].startswith("BIB:") or n["id"].startswith("PUB:V11:")}
    faults = [nid for nid in sorted(current_ids) if nid not in nodes or set(nodes[nid].get("actual", [])) != membership.get(nid, set())]
    check("Every current chapter membership equals literal manuscript use", not faults, {"errors": faults, "occurrences_by_language": dict(totals), "distinct_cited_sources": len(membership)})
    faults = [nid for nid in sorted(current_ids) if nid not in nodes or nodes[nid].get("printed") != (nid in bib_ids)]
    check("Current printed flags equal loaded bibliography membership, including auxiliaries", not faults, {"entries": len(bib_ids), "errors": faults})
    check("Literal chapter citations remain in the broader mapped reading view", all(set(nodes[sid].get("actual", [])).issubset(nodes[sid].get("mapped", [])) for sid in current_ids if sid in nodes))
    version = changes.get("current_book_version") or book["book"].get("source_version")
    selection = changes.get("current_citation_edge_ids")
    selection = set(selection) if selection is not None else None
    fields = ("file", "line", "macro", "bibkey", "sha256", "section_id")
    normalize = lambda rows: [{k: row.get(k) for k in fields} for row in rows]
    selected_edges = [e for e in graph["edges"] if e["id"] in selection] if selection is not None else [e for e in graph["edges"] if e["relation"] in names.values() and e.get("attributes", {}).get("source_version") == version]
    if selection is not None:
        check("Audited current citation-edge IDs resolve exactly", {e["id"] for e in selected_edges} == selection and all(e["relation"] in names.values() for e in selected_edges))
    for relation in names.values():
        wanted, found, faults = expected[relation], {}, []
        for edge in selected_edges:
            if edge["relation"] != relation:
                continue
            attrs = edge["attributes"]
            key = (graph["nodes"][edge["source"]]["id"], graph["nodes"][edge["target"]]["id"], attrs.get("language"))
            if key in found:
                faults.append([key, "duplicate current citation edge"])
            found[key] = edge
            locators = attrs.get("locators_json", "[]")
            locators = json.loads(locators) if isinstance(locators, str) else locators
            if attrs.get("citation_count") != len(wanted.get(key, [])) or normalize(locators) != normalize(wanted.get(key, [])):
                faults.append([key, "count or literal source locator differs"])
            if attrs.get("literal_citation") is not True or attrs.get("source_version") != version:
                faults.append([key, "current literal-use provenance differs"])
        check("Current " + relation + " has exact endpoints, languages, counts and locators", set(found) == set(wanted) and not faults, {"edges": len(found), "expected": len(wanted), "errors": faults})
    path = root / config.get("book_occurrences_json", "data/updates/ndse2_citation_occurrences.json")
    published = read_json(path)
    published = published["occurrences"] if isinstance(published, dict) else published
    serial = lambda row: json.dumps(row, ensure_ascii=False, sort_keys=True)
    check("Occurrence export matches literal bilingual body citations and excludes index/workref/nocite", collections.Counter(map(serial, published)) == collections.Counter(map(serial, occurrences)) and all(r["owner_id"] != "NDSE2:INDEX" for r in published), {"occurrences": len(occurrences)})
    parser_path = root / config.get("book_extractor", "source/extract_ndse2.py")
    check("Book extraction metadata identifies the delivered parser bytes", parser_path.is_file() and digest(parser_path) == book["meta"].get("parser_sha256"))


def validate_exports(root, config, payload, raw, check):
    nodes, edges = payload["nodes"], payload["edges"]
    check("Raw JSON reconstructs every current display node and raw attribute", len(raw["nodes"]) == len(nodes) and all(r["id"] == n["id"] and r.get("atlas_display") == {k: v for k, v in n.items() if k != "attributes"} and all(r.get(k) == v for k, v in n["attributes"].items()) for r, n in zip(raw["nodes"], nodes)))
    check("Raw JSON reconstructs every keyed edge, endpoint, family and attribute", len(raw["edges"]) == len(edges) and all(r["id"] == e["id"] and r["key"] == e["key"] and r["source"] == nodes[e["source"]]["id"] and r["target"] == nodes[e["target"]]["id"] and r["atlas_family"] == e["family"] and all(r.get(k) == v for k, v in e["attributes"].items()) for r, e in zip(raw["edges"], edges)))
    path = root / config["graph_graphml"]
    tree = ET.parse(path).getroot()
    keys = {k.attrib["id"]: k.attrib for k in tree.findall("g:key", GRAPH_NS)}
    graph = tree.find("g:graph", GRAPH_NS)
    errors = []

    def values(element):
        output = {}
        for item in element.findall("g:data", GRAPH_NS):
            key, value = keys[item.attrib["key"]], item.text or ""
            output[key["attr.name"]] = value
            try:
                if key["attr.type"] in ("long", "int"):
                    int(value)
                elif key["attr.type"] in ("double", "float"):
                    float(value)
                elif key["attr.type"] == "boolean" and value not in ("true", "false", "0", "1"):
                    raise ValueError(value)
            except ValueError:
                errors.append([element.attrib.get("id"), key["attr.name"], "invalid GraphML typed value"])
        return output

    def as_text(attrs):
        output = {}
        for key, value in attrs.items():
            if value is None:
                text = "null"
            elif type(value) is bool:
                text = str(value).lower()
            elif isinstance(value, (dict, list)):
                text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            else:
                text = str(value)
            output[key] = text
        return output

    xml_nodes, xml_edges = graph.findall("g:node", GRAPH_NS), graph.findall("g:edge", GRAPH_NS)
    if values(graph) != as_text(raw["graph"]):
        errors.append(["graph", "metadata differs"])
    for element, node in zip(xml_nodes, raw["nodes"]):
        if element.attrib.get("id") != node["id"] or values(element) != as_text({k: v for k, v in node.items() if k != "id"}):
            errors.append([node["id"], "node data differs"])
    for element, edge in zip(xml_edges, raw["edges"]):
        expected = {k: v for k, v in edge.items() if k not in ("source", "target", "key", "id")}
        expected.update(atlas_original_key_json=json.dumps(edge["key"], ensure_ascii=False), atlas_edge_id=edge["id"])
        data = values(element)
        if element.attrib != {"id": edge["id"], "source": edge["source"], "target": edge["target"]} or data != as_text(expected):
            errors.append([edge["id"], "edge identity or data differs"])
        try:
            if json.loads(data.get("atlas_original_key_json", "null")) != edge["key"]:
                errors.append([edge["id"], "original mixed-type multiedge key differs"])
        except ValueError:
            errors.append([edge["id"], "original multiedge key is not valid JSON"])
    check("GraphML preserves all current graph, node, edge and mixed-key data", len(xml_nodes) == len(raw["nodes"]) and len(xml_edges) == len(raw["edges"]) and not errors, {"nodes": len(xml_nodes), "edges": len(xml_edges), "errors": errors})
    check("Payload metadata contains the current GraphML SHA-256", payload["meta"].get("graphSha256") == digest(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--changes", type=Path)
    parser.add_argument("--book", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = validate_site(args.site, args.baseline, args.changes, args.book)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in ("complete", "passed", "failed", "artifact_sha256", "error")}, indent=2))
    if report["failed"]:
        print(json.dumps([c for c in report["checks"] if not c["passed"]], ensure_ascii=False, indent=2))
    return 0 if report["complete"] and not report["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
