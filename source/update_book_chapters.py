#!/usr/bin/env python3
"""Rebuild the v13.6 book graph from the published v13.5 tree and the reviewed edition map."""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from hashlib import sha256
import json
import re
from pathlib import Path
import sys

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parent
sys.path.insert(0, str(SOURCE / "automation"))
from atlas_graph import export_raw, render_current_atlas, validate_payload, write_graphml

RELATIONS = {
    "BOOK_PUBLICATION_VOLUME": ("Volume catalogue entry", "provenance"),
    "BOOK_EDITION_SUCCESSOR": ("Succeeded in the catalogue by", "provenance"),
    "HISTORICAL_CHAPTER_COUNTERPART": ("Corresponding chapter in the earlier edition", "provenance"),
    "BOOK_CHAPTER_OF": ("Numbered chapter of", "provenance"),
    "BOOK_SUPPLEMENT_OF": ("Practice or reference material in", "provenance"),
    "BOOK_CHAPTER_TOPIC": ("Chapter covers topic", "classification"),
    "BOOK_CHAPTER_STREAM": ("Chapter relates to research stream", "classification"),
    "BOOK_COVERS_TOPIC": ("Book covers topic through identified chapters", "classification"),
    "BOOK_RELATED_READING": ("Related chapter for comparison", "reading"),
    "BOOK_CHAPTER_COMPANION_READING": ("Related article for comparison", "reading"),
    "BOOK_CHAPTER_PRACTICE": ("Engineering practice to explore", "mapping"),
    "BOOK_CHAPTER_PREPARES_MISSION": ("Prepares the reader for mission", "mapping"),
    "BOOK_EXTENDS_VOLUME": ("Develops ideas from the named book", "provenance"),
    "BOOK_EXTENDS_WORK": ("Develops ideas from the named work, edition unspecified", "provenance"),
    "BOOK_EDITION_OF_WORK": ("Edition of the named work", "provenance"),
    "BOOK_PREFACE_RELATES_VOLUME": ("Book discussed in preface", "actual"),
    "BOOK_CITES_CHAPTER": ("Explicit reference to a chapter or section", "actual"),
    "BOOK_CITES_VOLUME": ("Explicit reference to a book", "actual"),
}
COVERS = {"PACKT": ("loop-engineering-packt.jpg", 768, 957), "ESA": ("engineering-software-agentic-ai.jpg", 1600, 2400)}
PUB_IDS = {"PACKT": "PUB:PACKT", "ESA": "PUB:ESA", "NDSE2": "PUB:NDSE2", "SDD": "PUB:V11:V03"}
REVIEW_PATH = "source/book_chapter_review.json"

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def fingerprint(path):
    return sha256(path.read_bytes()).hexdigest()

def node(nid, label, kind, *, attributes=None, **fields):
    data = dict(id=nid, label=label, kind=kind, collection=None, category=None,
                streams=[], topics=[], volumes=[], mapped=[], actual=[], printed=False,
                summary="", limitation="", authors="", url="", year="")
    data.update(fields)
    data["attributes"] = {"label": label, "kind": kind, **(attributes or {})}
    if data["collection"]:
        data["attributes"]["collection"] = data["collection"]
    return data

def move_historical_volume(graph, nodes):
    """Move the old volume hub’s endpoints; keep the old publication ID for the book actually cited."""
    original_hub = nodes["V05"]
    archive = deepcopy(original_hub)
    archive.update(id="V05-H", label=archive["label"] + " (self-published edition)")
    archive["attributes"].update(label=archive["label"], volume_id="V05-H", original_atlas_volume_id="V05")
    old_index = graph["nodes"].index(original_hub)
    archive_index = len(graph["nodes"])
    graph["nodes"].append(archive)
    nodes[archive["id"]] = archive
    for edge in graph["edges"]:
        for end in ("source", "target"):
            if edge[end] == old_index:
                edge[end] = archive_index
    for n in graph["nodes"]:
        if "V05" not in n["volumes"]:
            continue
        n["volumes"] = ["V05-H" if v == "V05" else v for v in n["volumes"]]
        a = n["attributes"]
        if a.get("volume_id") == "V05":
            a.update(volume_id="V05-H", original_atlas_volume_id="V05")
        if n.get("book", {}).get("volume") == "V05":
            n["book"]["volume"] = "V05-H"
        if n["kind"] == "practice_occurrence":
            n["summary"] = n["summary"].replace("retained V05 source", "retained self-published Loop Engineering source")
    old = nodes["PUB:V11:V05"]
    old["kind"] = old["attributes"]["kind"] = "archived_book_edition"
    old["attributes"]["edition_status"] = "Historical self-published edition"
    graph["volumes"].append({"id": archive["id"], "label": archive["label"]})

def set_publications(baseline, review):
    registry = read(baseline / "source/book_publications.json")
    old = next(x for x in registry["books"] if x["volume_id"] == "V05")
    registry["archived_books"] = [{**old, "volume_id": "V05-H", "original_atlas_volume_id": "V05"}]
    registry["books"].remove(old)
    for key in ["baseline_name","baseline_package_sha256","baseline_payload_sha256"]:
        registry.pop(key, None)
    registry.update(kind="atlas_publication_registry/2",schema_version=2,release=review["release"],
                    baseline_release="13.5",date=review["date"],reviewed_on=review["date"],baseline_commit=review["baseline_commit"],
                    evidence_note="Book links and chapter locators for ESA and Packt follow the edition evidence in source/book_chapter_review.json. Earlier artwork is identified as series artwork.")
    for b in review["books"]:
        code=b["code"]; name,w,h=COVERS[code]; cover="assets/books/"+name
        record=dict(volume_id=b["volume"],node_id=PUB_IDS[code],companion_url=b["companion_url"],
                    cover_image=cover,cover_width=w,cover_height=h,cover_sha256=fingerprint(ROOT/cover),
                    cover_alt=b["title"]+" by Enrico Papalini")
        registry["cover_provenance"]["files"].append({"site_path":cover,"sha256":record["cover_sha256"],"source":b["cover_provenance"]})
        if code=="PACKT":
            record.update(publisher_url=b["url"],amazon_url="https://www.amazon.com/dp/1808766415",amazon_asin="1808766415",amazon_verification="Print ISBN-10 product and matching jacket.")
        else:
            record.update(amazon_url=b["url"],amazon_asin=b["asin"],amazon_verification="Exact product destination supplied by the author.")
        registry["books"].append(record)
    registry["books"].sort(key=lambda r:r["volume_id"])
    registry["cover_provenance"]["origin"]="Each artwork is identified by its file record; the original series and NDSE2 artwork was supplied on 18 October 2026."
    save(SOURCE/"book_publications.json",registry)
    return {r["volume_id"]:r for r in registry["books"]}

def migrate(baseline, review):
    payload_path=baseline/"data/graph/atlas_payload_current.json"
    if fingerprint(payload_path)!=review["baseline_payload_file_sha256"]:
        raise ValueError("The supplied baseline payload differs from the reviewed v13.5 snapshot")
    graph=read(payload_path)
    by={n["id"]:n for n in graph["nodes"]}
    move_historical_volume(graph,by)
    indexes={n["id"]:i for i,n in enumerate(graph["nodes"])}
    def add(n):
        if n["id"] in by:
            raise ValueError("Duplicate new node "+n["id"])
        indexes[n["id"]]=len(graph["nodes"])
        by[n["id"]]=n
        graph["nodes"].append(n)

    edge_counts=Counter()
    def edge(source,target,relation,why,locator):
        if not why or not locator:
            raise ValueError("A rationale and a locator are required for "+relation)
        identity=json.dumps([source,target,relation,locator],ensure_ascii=False)
        eid="book136_"+sha256(identity.encode()).hexdigest()[:24]
        graph["edges"].append(dict(id=eid,key=eid,source=indexes[source],target=indexes[target],
            relation=relation,family=RELATIONS[relation][1],attributes=dict(relation=relation,rationale=why,
            provenance=REVIEW_PATH,source_locator=locator)))
        edge_counts[relation]+=1

    for t in review["new_topics"]:
        add(node(t["id"],t["label"],"topic",category="topics",summary=t["definition"],
                 attributes={"definition":t["definition"],"provenance":REVIEW_PATH}))
        graph["topics"].append({"id":t["id"],"label":t["label"]})

    pubs=set_publications(baseline,review)
    for b in review["books"]:
        volume=b["volume"]; code=b["code"]; pub_id=PUB_IDS[code]
        hub=node(volume,b["title"],"author_volume",category="volumes",volumes=[volume],authors=b["author"],
                 summary=b["summary"],url=b["url"],year="2026",
                 attributes=dict(volume_id=volume,publication_id=pub_id,source=b["source"]))
        if volume in by:
            by[volume].clear(); by[volume].update(hub)
            next(v for v in graph["volumes"] if v["id"]==volume)["label"]=hub["label"]
        else:
            add(hub)
            graph["volumes"].append({"id":volume,"label":hub["label"]})
        pub_attrs={**pubs[volume], "title":b["title"],"subtitle":b["subtitle"],"author":b["author"],
                   "edition_number":"1","status":"Published","chapter_count":len(b["chapters"]),
                   "metadata_source":b["source"],"url":b["url"],"url_role":"individual_book"}
        if code=="PACKT":
            pub_attrs.update(publisher=b["publisher"],isbn=b["isbn"],ebook_isbn=b["isbn_ebook"])
        book=node(pub_id,b["title"]+": "+b["subtitle"],"published_book",category="volumes",volumes=[volume],
                  summary=b["summary"],year="2026",authors=b["author"],url=b["url"],attributes=pub_attrs)
        add(book)
        edge(pub_id,volume,"BOOK_PUBLICATION_VOLUME","Publication represented by this volume in the current catalogue.",b["source"])
        chapter_topics=defaultdict(list)
        for c in b["chapters"]:
            nid=c["id"]; locator=c["source_locator"]
            attrs=dict(chapter_number=c["number"],chapter_no=c["number"],title=c["title"],volume_id=volume,
                       volume_title=b["title"],print_page=c["print_page"],source_locator=locator)
            for k in ["part","epub_locator"]:
                if k in c: attrs[k]=c[k]
            add(node(nid,c["title"],"published_book_chapter",collection="R",volumes=[volume],
                     summary=c["summary"],year="2026",authors=b["author"],url=c["url"],attributes=attrs,
                     streams=c["streams"],topics=[t["id"] for t in c["topics"]]))
            edge(nid,pub_id,"BOOK_CHAPTER_OF",f"Numbered chapter {c['number']} in the edition’s table of contents.",locator)
            for t in c["topics"]:
                edge(nid,t["id"],"BOOK_CHAPTER_TOPIC",t["rationale"],locator)
                chapter_topics[t["id"]].append(c)
            for stream in c["streams"]:
                edge(nid,stream,"BOOK_CHAPTER_STREAM",c["summary"],locator)
            if "predecessor_card" in c:
                edge(nid,c["predecessor_card"],"HISTORICAL_CHAPTER_COUNTERPART","The earlier edition treats the same chapter subject. Its citations and source files belong to that edition.", locator)
        book["topics"]=list(chapter_topics)
        for tid,chapters in chapter_topics.items():
            numbers=", ".join(str(c["number"]) for c in chapters)
            edge(pub_id,tid,"BOOK_COVERS_TOPIC","Covered in "+("chapter " if len(chapters)==1 else "chapters ")+numbers+".",
                 ", ".join(c["id"] for c in chapters))
    packt=next(b for b in review["books"] if b["code"]=="PACKT")
    work="WORK:NDSE"
    add(node(work,"Non-Deterministic Software Engineering (work)","bibliographic_work",category="volumes",
             authors=packt["author"],summary="Work-level record for a reference that leaves the edition unspecified."))
    for edition in ("PUB:V11:V01","PUB:NDSE2"):
        edge(edition,work,"BOOK_EDITION_OF_WORK","The publication is an identified edition of this work.","Atlas publication registry, V01 and V06")
    for row in packt["intellectual_lineage"]:
        edge("PUB:PACKT",row["target"],row["relation"],row["rationale"],packt["lineage_locator"])
    edge("PUB:V11:V05","PUB:PACKT","BOOK_EDITION_SUCCESSOR","The author designates the Packt book as the current Loop Engineering catalogue entry.","Author instruction and the two edition records")
    for b in review["books"]:
        for c in b["chapters"]:
            for k,relation in [("related_reading","BOOK_RELATED_READING"),("external_reading","BOOK_CHAPTER_COMPANION_READING"),("practice","BOOK_CHAPTER_PRACTICE")]:
                obj=c[k];edge(c["id"],obj["id"],relation,obj["rationale"],c["source_locator"])
    esa=next(b for b in review["books"] if b["code"]=="ESA")
    for bucket,kind,prefix in [("missions","book_mission","M"),("appendices","book_appendix","A")]:
        for item in esa[bucket]:
            nid="ESA:"+prefix+":"+item["id"]
            loc=f"ESA, English 7 × 10 print source, p. {item['print_page']}. EPUB: {item['epub_locator']}"
            add(node(nid,item["title"],kind,category="sections",volumes=["V07"],authors=esa["author"],
                     url=esa["url"],year="2026",summary=item.get("outcome",""),
                     attributes=dict(volume_id="V07",volume_title=esa["title"],code=item["id"],print_page=item["print_page"],source_locator=loc)))
            edge(nid,"PUB:ESA","BOOK_SUPPLEMENT_OF","Listed separately from the twelve numbered chapters in the table of contents.",loc)
            for chapter in item.get("preparatory_chapters",[]):
                edge(f"ESA:C{chapter:02}",nid,"BOOK_CHAPTER_PREPARES_MISSION","The practice guide lists this chapter as preparation for mission "+item["id"]+".","ESA Table P.1, Practice guide")
    for row in esa["explicit_preface_relations"]:
        edge("PUB:ESA",PUB_IDS[row["target"]],"BOOK_PREFACE_RELATES_VOLUME"," ".join(filter(None,[row["nature"],row.get("caveat")])) ,row["source"])
    def crossrefs(source, row, bookcode, locator):
        targets=row.get("atlas_target_chapter_ids") or [f"{bookcode}:C{n:02}" for n in row["target_chapters"]]
        for target in targets:
            edge(source,target,"BOOK_CITES_CHAPTER",row["description"],locator)
        if not targets:
            edge(source,PUB_IDS[bookcode],"BOOK_CITES_VOLUME",row["description"],locator)
    for row in esa["explicit_cross_references"]:
        crossrefs(f"ESA:C{row['esa_chapter']:02}", row, row["target_book"], row["source"])
    for row in esa["front_and_back_matter_crossrefs"]:
        crossrefs("PUB:ESA",row,row["target"],row["esa_locator"])
    for relation,count in edge_counts.items():
        label,family=RELATIONS[relation]
        graph["relations"].append(dict(id=relation,label=label,family=family,count=count))
    totals=Counter(e["family"] for e in graph["edges"])
    groups=Counter(n["category"] for n in graph["nodes"])
    for row in graph["edgeFamilies"]: row["count"]=totals[row["id"]]
    for row in graph["nodeGroups"]: row["count"]=groups[row["id"]]
    meta=graph["meta"]
    meta["atlas_metadata_history"].append(dict(release_before_update=meta["edition"],date_before_update=meta["date"],notes=meta["notes"],publication_navigation=meta["publication_navigation"]))
    meta.update(edition="13.6 · Packt and ESA chapter maps",date=review["date"],nodeCount=len(by),edgeCount=len(graph["edges"]),relationCount=len(graph["relations"]),
                notes=[review["reading_scope"]],publication_navigation=dict(release="13.6",reviewed_on=review["date"],manifest="source/book_publications.json",audit=REVIEW_PATH))
    meta["graphAttributes"].update(portable_atlas_release="13.6",portable_atlas_snapshot_date=review["date"],atlas_update="13.6_20261123",
              portable_atlas_basis="Published v13.5 plus edition-specific book chapters, explicit references and reviewed topic mappings.",
              publication_navigation_release="13.6",book_chapter_review=REVIEW_PATH)
    validate_payload(graph)
    return graph

def interactive(html):
    """Register the additional collection in the existing offline shell."""
    marker='<label class="source-row" style="--source:#795b87">'
    row='<label class="source-row" style="--source:#38687c"><input id="sourceR" type="checkbox" data-collection="R"><span class="prefix">R</span><span><b>Packt and ESA chapters</b><small>Edition-specific chapter records</small></span><span class="count">18</span></label>\n'
    changes={marker:row+marker, "PAT:'#795b87'":"R:'#38687c',PAT:'#795b87'",
        "PAT:'PAT · Practices'":"R:'R · Packt and ESA chapters',PAT:'PAT · Practices'",
        "PAT:'Software Engineering Practice'":"R:'Packt or ESA chapter',PAT:'Software Engineering Practice'",
        "N: published NDSE2 chapters · PAT:":"N: published NDSE2 chapters · R: Packt and ESA chapters · PAT:",
        "volume:'Non-Deterministic series volumes'":"volume:'Book volumes'","Series volumes":"Book volumes",
        "Earlier-book records retain their source volume. N records are the published NDSE2 chapters.":"R records are the numbered Packt and ESA chapters. B records retain their historical source edition. N records are the published NDSE2 chapters.",
        "!['N','PAT'].includes(r.collection)":"!['N','R','PAT'].includes(r.collection)"}
    # Only modify UI code, never an author/source attribute in the graph JSON.
    left,tail=html.split('<script id="graph-data" type="application/json">',1)
    data,right=tail.split('</script>',1)
    changes.update({"data-grouping=\"chapter\">Book chapters":"data-grouping=\"chapter\">NDSE2 chapters",
                    "chapter:'Book chapters'":"chapter:'NDSE2 chapters'",
                    '<div class="button-row"><button id="ndse2Only"': '<div class="button-row"><button id="reviewedBooks" class="small">Explore Packt and ESA connections</button></div>\n<div class="button-row"><button id="ndse2Only"',
                    "$('ndse2Only').onclick=":"$('reviewedBooks').onclick=()=>{S=defaultState();S.collections=new Set(['R']);S.context=new Set(['volumes','topics']);S.grouping='volume';S.hideIsolated=true;selected=null;selectedEdge=null;rebuild();};\n$('ndse2Only').onclick="})
    right=re.sub(r"<p>Release v[0-9.]+,.*?</p>", "<p>Release v13.6, 2026-11-23. The book catalogue identifies the Packt edition and ESA. Historical records retain the self-published edition that their sources cited.</p>", right, count=1)
    for src,sub in changes.items():
        if src not in left+right: raise ValueError("Unrecognized graph shell: "+src)
        left=left.replace(src,sub);right=right.replace(src,sub)
    return left+'<script id="graph-data" type="application/json">'+data+'</script>'+right

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline",type=Path,required=True)
    args=parser.parse_args()
    review=read(ROOT/REVIEW_PATH)
    graph=migrate(args.baseline,review)
    config=read(args.baseline/"source/site_config.json")
    config.update(site_version=review["release"], graph_version=review["release"], graph_snapshot=review["date"],build_date=review["date"],
                  release_notes="UPDATE_v13_6_20261123.html", book_revision_json=REVIEW_PATH,publications_audit_json=REVIEW_PATH)
    next(c for c in config["collections"] if c["code"]=="B")["description"] = (
        "111 chapter and file records from four earlier volumes and the historical self-published loop edition. "
        "These cards retain their original English and Italian catalogue wording and trace the source files used by the Atlas.")
    config["collections"].insert(-1,dict(code="R",slug="reviewed-chapters",title="Packt and ESA chapters",short="Packt and ESA chapters",description="Six chapters from Loop Engineering for AI Agents and twelve from Engineering Software with Agentic AI. Each record identifies the edition, the chapter and its topics.",source_url=""))
    save(SOURCE/"site_config.json",config)
    save(SOURCE/"automation_release.json", dict(kind="atlas_book_chapters_update/1",date=review["date"],
         release=review["release"],baseline_commit=review["baseline_commit"],review_path=REVIEW_PATH,
         chapter_ids=[c["id"] for b in review["books"] for c in b["chapters"]],new_topic_ids=[t["id"] for t in review["new_topics"]]))
    meta=graph["meta"]
    meta.pop("graphSha256",None)
    write_graphml(export_raw(graph),ROOT/config["graph_graphml"])
    meta["graphSha256"]=fingerprint(ROOT/config["graph_graphml"])
    save(ROOT/config["graph_json"],export_raw(graph))
    save(ROOT/config["payload_json"],graph)
    source=(args.baseline/"source/atlas_current.html").read_text()
    html=render_current_atlas(source,graph,review["release"],review["date"])
    (SOURCE/"atlas_current.html").write_text(interactive(html))
    print(f"{len(graph['nodes'])} nodes, {len(graph['edges'])} edges, {len(graph['topics'])} topics")

if __name__=="__main__":
    main()
