"""Small presentation changes to the preserved Atlas application.

The original default state and all original relationship switches are retained.
Data remain separate from the application template.
"""
import collections
import re


def patch_template(base, data):
    text = re.sub(
        r'(<script id="graph-data" type="application/json">).*?(</script>)',
        lambda m: m.group(1) + "{}" + m.group(2), base, count=1, flags=re.S
    )
    old_default = re.search(r"const defaultState=.*?;", text).group(0)
    counts = collections.Counter(n.get("collection") for n in data["nodes"])
    node_count, edge_count = len(data["nodes"]), len(data["edges"])
    relation_count = len(data["relations"])
    num = lambda value: f"{value:,}"

    text = text.replace(
        "<title>AI & Software Engineering · Knowledge Atlas v12 · Exploring Gen AI</title>",
        "<title>AI & Software Engineering · Knowledge Atlas v13 · Published NDSE2</title>"
    )
    for code in ("O", "P", "F", "B", "W"):
        pattern = r'(<label class="source-row"[^>]*><input id="source' + code + r'".*?<span class="count">)\d+(</span></label>)'
        text, matches = re.subn(pattern, lambda m: m.group(1) + str(counts[code]) + m.group(2), text, count=1)
        assert matches == 1, code
    new_row = (
        '<label class="source-row" style="--source:#b28724"><input id="sourceN" type="checkbox" data-collection="N">'
        '<span class="prefix">N</span><span><b>NDSE2 · Second edition</b><small>13 published chapters · EN / ITA</small></span>'
        '<span class="count">13</span></label>\n'
    )
    text = text.replace(
        '<div class="button-row"><button id="fowlerOnly"',
        new_row + '<div class="button-row"><button id="ndse2Only" class="small">Explore NDSE2 chapters</button></div>\n'
        '<div class="button-row"><button id="fowlerOnly"', 1
    )
    text = text.replace("Exploring Gen AI · credited authors", "Essays · credited authors")
    text = text.replace("F:'#a25643'}", "F:'#a25643',N:'#b28724'}")
    text = text.replace("F:'F · martinfowler.com essays'}",
                        "F:'F · martinfowler.com essays',N:'N · Published NDSE2 chapters'}")
    text = text.replace("F:'martinfowler.com essays'}",
                        "F:'martinfowler.com essays',N:'Published NDSE2 chapter'}")
    text = text.replace("['W','O','P','B','F']", "['W','O','P','B','F','N']")
    text = text.replace("['W','O','P','F','B']", "['W','O','P','F','B','N']")
    text = text.replace("r.id,r.label,r.authors,r.summary,r.year,",
                        "r.id,r.label,r.attributes.title_it||'',r.authors,r.summary,r.year,")
    text = text.replace("isSource=!!r.collection;", "isSource=!!r.collection&&r.collection!=='N';")
    text = text.replace("let label=n.id;", "let label=n.r.collection==='N'?'N'+n.id.slice(-2):n.id;")
    text = text.replace("const label=n.r.collection?n.id:",
                        "const label=n.r.collection?(n.r.collection==='N'?'N'+n.id.slice(-2):n.id):")
    text = text.replace("if(i>=0)return palette[i];", "if(i>=0)return palette[i%palette.length];")

    citation_text = {
        "Actual citations · v11 text layer": "Actual citations · published NDSE2",
        "Actual v11 chapter citations": "Published NDSE2 chapter citations",
        "Actual chapter citations · v11": "Actual chapter citations · NDSE2 13.7.1",
        "actual v11 chapter-bundle citations": "literal citations in the published NDSE2 sources",
        "Current membership comes from v11 literal citation records and the citing file’s chapter. Bibliography-only references may have no chapter citation.":
            "Current membership comes from literal citations in the final EN/ITA 13.7.1 source tree. Index links and bibliography-only entries do not create chapter citations.",
        "Earlier-book records belong to their source volume. W/O/P sources are associated through recorded prior-book citations and current chapter use. New F essays have proposed chapter mappings only and no source-volume association.":
            "Earlier-book records retain their source volume. N records are the published NDSE2 chapters. Current citations and suggested companion readings remain separate.",
        "Derived only from current chapter-bundle citation links; not all printed references have a chapter citation.":
            "Derived from active literal citations in the final EN/ITA 13.7.1 sources. Source-index links and nocite are excluded; not all bibliography entries are cited in a chapter.",
        "This source has not been inserted into the book bibliography.":
            "Its published-book bibliography and chapter status are listed below; newer companion readings remain distinct.",
        "Exploring Gen AI · credited authors": "Fowler website · credited authors",
        "F chapter mappings are suggestions, not printed citations.":
            "F sources actually present in the published bibliography and chapters are marked; new F034/F035 records remain companion readings.",
        "All original graph attributes": "Graph attributes and retained history",
    }
    for before, after in citation_text.items():
        text = text.replace(before, after)
    text = text.replace(
        "Static release v12 preserves the complete v11.2 web graph and adds the 33-source Exploring Gen AI overlay. The linked book remains v11.2; its bibliography and citation layer were not rewritten. The opening 193-source filter and original clustering logic come from the supplied v6 page. Original attributes are retained; historical records remain historical.",
        "Release v13.0 extends the supplied v12.1 package with four reviewed source records and the published NDSE2 13.7.1 chapter and citation layer. F034 and F035 explicitly extend the Fowler collection beyond its original series index. All historical nodes and keyed edges remain; current chapter membership is reconciled from the final bilingual sources. The original 193-source opening view is preserved."
    )
    text = text.replace(
        "<p>F001–F033 are independent atlas identifiers.",
        "<p>F001–F035 are independent atlas identifiers; F034/F035 are explicitly adjacent-site additions."
    )
    text = text.replace(
        "W / O / P / F: source provenance · B: earlier-book records.",
        "W / O / P / F: source provenance · B: earlier books · N: published NDSE2 chapters."
    )
    text = text.replace(
        "33 essays from martinfowler.com. Authorship is credited individually.",
        "35 essays from martinfowler.com. Authorship and publication/revision dates are credited individually."
    )
    text = text.replace(
        "$('allSources').onclick=",
        "$('ndse2Only').onclick=()=>{S=defaultState();S.collections=new Set(['N']);S.grouping='chapter';"
        "S.chapterBasis='actual';selected=null;selectedEdge=null;rebuild();toast('13 published NDSE2 chapters. Open a node for its catalogue and source links.');};\n"
        "$('allSources').onclick=", 1
    )
    text = text.replace("1247</span></summary>", str(counts[None]) + "</span></summary>")
    text = text.replace("1,757", num(node_count)).replace("12,188", num(edge_count))
    text = text.replace("297", str(relation_count))
    text = text.replace("V12 ·", "V13 ·").replace("v12 static graph", "v13 static graph")
    text = text.replace("V13 · FOWLER SERIES", "V13 · NDSE2 &amp; SOURCES")
    text = text.replace("— v12 filtered graph", "— v13 filtered graph")
    text = text.replace("AI_SWE_Atlas_v12_", "AI_SWE_Atlas_v13_")
    # Complete graph exports carry the normalized current view as well as every
    # retained raw attribute, so citation display information is not lost.
    text = text.replace(
        "({id:n.id,...n.r.attributes})",
        "({id:n.id,...n.r.attributes,atlas_display:Object.fromEntries(Object.entries(n.r).filter(([k])=>k!=='attributes'))})"
    )
    assert re.search(r"const defaultState=.*?;", text).group(0) == old_default
    assert 'id="sourceN"' in text
    return text
