"""Independent checks against frozen bilingual book metadata and graph exports."""
import collections
import hashlib
import json
import xml.etree.ElementTree as ET


def validate(root, graph, check):
    read = lambda p: json.loads((root / p).read_text(encoding="utf-8"))
    nodes = {n["id"]: n for n in graph["nodes"]}
    check("No duplicate node or keyed-edge IDs", len(nodes) == len(graph["nodes"]) and
          len({e["id"] for e in graph["edges"]}) == len(graph["edges"]))
    check("All edge endpoints resolve", all(isinstance(e[k], int) and 0 <= e[k] < len(nodes)
          for e in graph["edges"] for k in ("source", "target")))
    book = read("source/ndse2_book.json")
    chapters = book["chapters"]
    ids = [f"NDSE2:C{i:02}" for i in range(1, 14)]
    check("Thirteen published chapters retain stable hub associations", [c["id"] for c in chapters] == ids and
          [c["hub_id"] for c in chapters] == [f"C:C{i:02}" for i in range(1, 14)] and
          [n["id"] for n in graph["nodes"] if n.get("collection") == "N"] == ids)
    sections = [s for c in chapters for s in c["sections"]]
    check("All 149 final headings have edition-specific section nodes", len(sections) == 149 and
          {s["id"] for s in sections} == {n["id"] for n in graph["nodes"] if n["kind"] == "published_book_section"})
    check("English and Italian chapter source sets and heading IDs align", all(
          c["source_ids"] == c["source_ids_it"] and [s["id"] for s in c["sections"]] ==
          [s["id"] for s in c["sections_it"]] for c in chapters))

    membership = collections.defaultdict(set)
    expected = {r: collections.defaultdict(list) for r in
                ("NDSE2_CHAPTER_CITES", "NDSE2_SECTION_CITES", "NDSE2_DOCUMENT_CITES")}
    occurrences, totals = [], collections.Counter()
    for unit in chapters + [u for u in book["nonchapter_units"] if u["id"] != "NDSE2:INDEX"]:
        is_chapter = unit["id"] in ids
        for language, field in (("EN", "citations"), ("ITA", "citations_it")):
            for citation in unit[field]:
                sid = citation["source_id"]
                relation = "NDSE2_CHAPTER_CITES" if is_chapter else "NDSE2_DOCUMENT_CITES"
                expected[relation][(unit["id"], sid, language)].append(citation)
                if is_chapter:
                    membership[sid].add(unit["hub_id"])
                    totals[language] += 1
                    if citation.get("section_id"):
                        expected["NDSE2_SECTION_CITES"][(citation["section_id"], sid, language)].append(citation)
                occurrences.append({**citation, "language": language, "owner_id": unit["id"]})
    check("302 chapter citation occurrences per language and 158 distinct cited sources",
          totals == {"EN": 302, "ITA": 302} and len(membership) == 158,
          {"occurrences_by_language": dict(totals), "unique_sources": len(membership)})
    bib_ids = {e["source_id"] for e in book["bibliography"]["EN"]["entries"]}
    current_ids = {n["id"] for n in graph["nodes"] if n.get("collection") in ("W", "O", "P", "F")} | set(membership) | bib_ids
    faults = [nid for nid in current_ids if nid not in nodes or set(nodes[nid]["actual"]) != membership.get(nid, set())]
    check("Every current actual membership equals literal manuscript use", not faults, faults)
    faults = [nid for nid in current_ids if nid not in nodes or nodes[nid]["printed"] != (nid in bib_ids)]
    check("All 241 loaded bibliography entries, including auxiliaries, retain correct printed flags",
          len(bib_ids) == 241 and not faults, faults)
    check("Literal current citations remain in the broader mapped reading view",
          all(set(nodes[sid]["actual"]).issubset(nodes[sid]["mapped"]) for sid in current_ids))
    check("Fowler bibliography and actual chapter use remain distinct",
          sum(n["printed"] for n in nodes.values() if n.get("collection") == "F") == 11 and
          sum(bool(n["actual"]) for n in nodes.values() if n.get("collection") == "F") == 9)
    added = read("source/article_update_20261018.json")["meta"]["source_additions"]
    check("Four online additions are not falsely cited in the published book",
          set(added) == {"O051", "F034", "F035", "P124"} and all(
              not nodes[nid]["actual"] and not nodes[nid]["printed"] and nid not in bib_ids for nid in added))
    check("Publication records author confirmation without an invented date or ISBN",
          book["book"]["publication_date"] is None and book["book"]["isbn"] is None and
          nodes["V06"]["attributes"]["status"] == "PUBLISHED_AUTHOR_CONFIRMED" and
          nodes["PUB:NDSE2"]["kind"] == "published_book")

    fields = ("file", "line", "macro", "bibkey", "sha256", "section_id")
    normalize = lambda rows: [{k: row.get(k) for k in fields} for row in rows]
    for relation, wanted in expected.items():
        found, errors = {}, []
        for edge in graph["edges"]:
            if edge["relation"] != relation:
                continue
            attrs = edge["attributes"]
            key = (graph["nodes"][edge["source"]]["id"], graph["nodes"][edge["target"]]["id"], attrs.get("language"))
            if key in found:
                errors.append([key, "duplicate edge"])
            found[key] = edge
            locators = json.loads(attrs.get("locators_json", "[]"))
            if attrs.get("citation_count") != len(wanted.get(key, [])) or normalize(locators) != normalize(wanted.get(key, [])):
                errors.append([key, "count or locator differs"])
            if attrs.get("literal_citation") is not True or attrs.get("source_version") != "13.7.1":
                errors.append([key, "literal-use provenance missing"])
        check(relation + " exact endpoints, languages, occurrence counts and locators",
              set(found) == set(wanted) and not errors,
              {"edges": len(found), "expected_edges": len(wanted), "errors": errors})
    frozen_occurrences = read("data/updates/ndse2_citation_occurrences.json")["occurrences"]
    serial = lambda row: json.dumps(row, ensure_ascii=False, sort_keys=True)
    check("All 882 bilingual body occurrences match; index, nocite and workref excluded",
          len(frozen_occurrences) == 882 and collections.Counter(map(serial, frozen_occurrences)) ==
          collections.Counter(map(serial, occurrences)) and all(r["owner_id"] != "NDSE2:INDEX" for r in frozen_occurrences))
    check("Delivered extractor matches the parser hash recorded in book metadata",
          hashlib.sha256((root / "source/extract_ndse2.py").read_bytes()).hexdigest() == book["meta"]["parser_sha256"])

    raw = read("data/graph/knowledge_graph_v13.json")
    check("Raw JSON reconstructs every normalized current node and its raw attributes",
          len(raw["nodes"]) == len(graph["nodes"]) and all(
              r["id"] == n["id"] and r["atlas_display"] == {k: v for k, v in n.items() if k != "attributes"} and
              all(r.get(k) == v for k, v in n["attributes"].items()) for r, n in zip(raw["nodes"], graph["nodes"])))
    check("Raw JSON retains every keyed edge, endpoint, family and attribute",
          len(raw["edges"]) == len(graph["edges"]) and all(
              r["id"] == e["id"] and r["key"] == e["key"] and r["source"] == graph["nodes"][e["source"]]["id"] and
              r["target"] == graph["nodes"][e["target"]]["id"] and r["atlas_family"] == e["family"] and
              all(r.get(k) == v for k, v in e["attributes"].items()) for r, e in zip(raw["edges"], graph["edges"])))
    check("Current relation counts are exact", {r["id"]: r["count"] for r in graph["relations"]} ==
          dict(collections.Counter(e["relation"] for e in graph["edges"])))
    check_graphml(root, graph, raw, check)


def check_graphml(root, payload, raw, check):
    path = root / "data/graph/knowledge_graph_v13.graphml"
    tree = ET.parse(path).getroot()
    ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
    keys = {k.attrib["id"]: k.attrib for k in tree.findall("g:key", ns)}
    graph = tree.find("g:graph", ns)
    errors = []

    def values(element):
        result = {}
        for item in element.findall("g:data", ns):
            key, value = keys[item.attrib["key"]], item.text or ""
            result[key["attr.name"]] = value
            try:
                if key["attr.type"] == "long":
                    int(value)
                elif key["attr.type"] == "double":
                    float(value)
                elif key["attr.type"] == "boolean" and value not in ("true", "false", "0", "1"):
                    raise ValueError(value)
            except ValueError:
                errors.append([element.attrib.get("id"), key["attr.name"], "invalid typed value"])
        return result

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

    xml_nodes, xml_edges = graph.findall("g:node", ns), graph.findall("g:edge", ns)
    if values(graph) != as_text(raw["graph"]):
        errors.append(["graph", "metadata differs"])
    for element, node in zip(xml_nodes, raw["nodes"]):
        if element.attrib["id"] != node["id"] or values(element) != as_text({k: v for k, v in node.items() if k != "id"}):
            errors.append([node["id"], "node differs"])
    for element, edge in zip(xml_edges, raw["edges"]):
        expected = {k: v for k, v in edge.items() if k not in ("source", "target", "key", "id")}
        expected.update(atlas_original_key_json=json.dumps(edge["key"], ensure_ascii=False), atlas_edge_id=edge["id"])
        data = values(element)
        if element.attrib != {"id": edge["id"], "source": edge["source"], "target": edge["target"]} or data != as_text(expected):
            errors.append([edge["id"], "edge identity or data differs"])
        if json.loads(data["atlas_original_key_json"]) != edge["key"]:
            errors.append([edge["id"], "semantic key differs"])
    check("GraphML preserves all graph, node and edge data and mixed multiedge keys",
          len(xml_nodes) == len(raw["nodes"]) and len(xml_edges) == len(raw["edges"]) and not errors,
          {"nodes": len(xml_nodes), "edges": len(xml_edges), "errors": errors})
    check("Graph metadata contains the exact current GraphML SHA-256",
          payload["meta"]["graphSha256"] == hashlib.sha256(path.read_bytes()).hexdigest())
