#!/usr/bin/env python3
"""Extract a reviewable NDSE2 catalogue from the final EN/ITA LaTeX trees.

No source version, publication date, chapter count, summary or learning objective
is invented. Bibliographic publication assertions come from explicit metadata;
literal use comes from the active bounded source parser. Editorial descriptions
are reused only when every contributing chapter source remains byte-identical.
"""
from __future__ import annotations

import collections
import copy
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

from extract_ndse2_base import (BookParser, IDENTIFIER_MACROS, METADATA_MACROS,
                               clean_tex, combine_units, config_values, sha)

EDITORIAL_FIELDS = ("summary", "summary_it", "learning_goals", "learning_goals_it")


def _digest(value):
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _date(value, name):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{name} must be an explicit date in YYYY-MM-DD format")
    dt.date.fromisoformat(value)
    return value


def chapter_source_fingerprint(chapter):
    """Hash EN/ITA root identities plus every actively included chapter file.

    Paths are part of this identity because moved files can invalidate locators
    even when their bytes are identical. This catches edits to included didactic
    material that would be missed by hashing only chapterNN.tex.
    """
    rows = []
    for suffix in ("", "_it"):
        rows.append((chapter.get("root_file" + suffix), chapter.get("root_sha256" + suffix)))
        rows.extend((f.get("file"), f.get("sha256")) for f in chapter.get("source_files" + suffix, []))
    if any(not path or not re.fullmatch(r"[a-fA-F0-9]{64}", digest or "") for path, digest in rows):
        raise ValueError(f"Incomplete chapter source manifest: {chapter.get('id')}")
    return _digest(sorted(set(rows)))


def _validate_editorial(record, chapter_id, fingerprint):
    if not isinstance(record, dict):
        raise ValueError(f"chapter_editorial.{chapter_id} must be an object")
    if record.get("source_fingerprint") != fingerprint:
        raise ValueError(f"Editorial text for {chapter_id} was not reviewed against the current source_fingerprint")
    if not isinstance(record.get("reviewed_by"), str) or not record["reviewed_by"].strip():
        raise ValueError(f"Editorial review for {chapter_id} needs reviewed_by")
    _date(record.get("reviewed_on"), f"chapter_editorial.{chapter_id}.reviewed_on")
    for field in ("summary", "summary_it"):
        if not isinstance(record.get(field), str) or not record[field].strip():
            raise ValueError(f"Editorial review for {chapter_id} needs a nonempty {field}")
    for field in ("learning_goals", "learning_goals_it"):
        if not isinstance(record.get(field), list) or not record[field] or any(not isinstance(v, str) or not v.strip() for v in record[field]):
            raise ValueError(f"Editorial review for {chapter_id} needs a nonempty list of {field}")


def _editorial(chapter, previous_by_id, reviews):
    cid = chapter["id"]
    fingerprint = chapter_source_fingerprint(chapter)
    chapter["source_fingerprint"] = fingerprint
    reviewed = reviews.get(cid)
    if reviewed is not None:
        _validate_editorial(reviewed, cid, fingerprint)
        chapter.update({key: copy.deepcopy(reviewed[key]) for key in EDITORIAL_FIELDS})
        chapter.update(editorial_review_required=False, editorial_status="reviewed_against_current_sources",
                       editorial_review={key: reviewed[key] for key in ("reviewed_by", "reviewed_on", "source_fingerprint")})
        return
    previous = previous_by_id.get(cid)
    reusable = False
    if previous and not previous.get("editorial_review_required"):
        try:
            reusable = chapter_source_fingerprint(previous) == fingerprint and all(previous.get(key) for key in EDITORIAL_FIELDS)
        except ValueError:
            reusable = False
    if reusable:
        chapter.update({key: copy.deepcopy(previous[key]) for key in EDITORIAL_FIELDS})
        for key in ("summary_basis", "summary_basis_it", "learning_goals_locator", "learning_goals_locator_it", "editorial_review"):
            if key in previous:
                chapter[key] = copy.deepcopy(previous[key])
        chapter.update(editorial_review_required=False, editorial_status="reused_from_byte_identical_chapter_sources",
                       editorial_reuse_basis="Both language roots and all actively included chapter files have unchanged path and SHA-256")
        return
    chapter.update(summary="", summary_it="", learning_goals=[], learning_goals_it=[],
                   editorial_review_required=True, editorial_status="review_required_after_source_change" if previous else "first_editorial_review_required",
                   editorial_review_reason="No reviewed prior summary/goals cover these exact bilingual source files; supply chapter_editorial with this source_fingerprint")


def _totals(parser):
    chapters = [unit for unit in parser.units if unit["kind"] == "chapter"]
    other = [unit for unit in parser.units if unit["kind"] not in {"chapter", "identifier_index"}]
    ids = {citation["source_id"] for chapter in chapters for citation in chapter["citations"] if citation["source_id"]}
    return {
        "active_tex_files": len(parser.manifest), "chapters": len(chapters), "nonchapter_units": len(parser.units) - len(chapters),
        "chapter_citation_occurrences": sum(len(c["citations"]) for c in chapters),
        "chapter_unique_source_ids": len(ids), "chapter_primary_catalogue_unique_source_ids": sum(not i.startswith("BIB:") for i in ids),
        "chapter_resolved_auxiliary_unique_source_ids": sum(i.startswith("BIB:") for i in ids),
        "chapter_unique_bibkeys": len({o["bibkey"] for c in chapters for o in c["citations"]}),
        "chapter_identifier_mentions": sum(len(c["identifier_mentions"]) for c in chapters),
        "chapter_figure_caption_citations": sum(o["container"] == "figure_caption" for c in chapters for o in c["citations"]),
        "chapter_figure_caption_identifier_mentions": sum(o["container"] == "figure_caption" for c in chapters for o in c["identifier_mentions"]),
        "nonchapter_body_citation_occurrences": sum(len(c["citations"]) for c in other),
        "bibliography_loaded_entries": len(parser.bibliography["entries"]), "identifier_index_entries": len(parser.bibliography["index_keys"]),
        "chapter_source_ids": sorted(ids),
        "chapter_auxiliary_bibkeys": sorted({o["bibkey"] for c in chapters for o in c["citations"] if o["resolution"] == "existing_auxiliary_bibliography_node"}),
        "chapter_unresolved_bibkeys": sorted({o["bibkey"] for c in chapters for o in c["citations"] if not o["source_id"]}),
        "unloaded_reference_warnings": [w for w in parser.warnings if w["type"] == "unloaded_bibkey"],
    }


def extract_book(book_root, metadata, baseline_payload, previous=None, extracted_on=None):
    """Return a final-source metadata/citation draft; never write files.

    Required metadata fields:
      source_version, publication_status, publication_status_basis.
    ``extracted_on`` or metadata.extracted_on must explicitly name the extraction
    date. Titles, subtitles, author, publisher and year default to config.tex;
    explicit metadata overrides are permitted and recorded. Date/ISBN are never
    inferred. Optional ``bibliography_id_map`` maps explicit bibkeys to existing
    baseline IDs. Optional ``chapter_editorial`` supplies reviewed current text.

    The result remains review-blocked while any chapter has
    editorial_review_required=true, or structural/source-reference blockers exist.
    """
    if not isinstance(metadata, dict):
        raise ValueError("Explicit book metadata JSON is required")
    for key in ("source_version", "publication_status", "publication_status_basis"):
        if not isinstance(metadata.get(key), str) or not metadata[key].strip():
            raise ValueError(f"Explicit book metadata.{key} is required; no publication assertion or version is inferred")
    version = metadata["source_version"]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", version):
        raise ValueError("metadata.source_version is not a safe edition identifier")
    extraction_date = _date(extracted_on or metadata.get("extracted_on"), "extracted_on")
    if metadata.get("publication_date") is not None:
        _date(metadata["publication_date"], "metadata.publication_date")
    root = Path(book_root).resolve()
    if not isinstance(baseline_payload, dict) or not isinstance(baseline_payload.get("nodes"), list):
        raise ValueError("A normalized baseline graph payload is required to resolve citation IDs")
    graph_ids = {n["id"] for n in baseline_payload["nodes"]}
    auxiliary = {n["attributes"]["original_key"]: n["id"] for n in baseline_payload["nodes"]
                 if n.get("kind") == "auxiliary_bibliography" and n.get("attributes", {}).get("original_key")}
    for bibkey, source_id in metadata.get("bibliography_id_map", {}).items():
        if source_id not in graph_ids:
            raise ValueError(f"bibliography_id_map target is absent from the supplied graph: {bibkey} -> {source_id}")
        auxiliary[bibkey] = source_id
    for lang in ("EN", "ITA"):
        for name in ("main.tex", "preamble.tex", "config.tex"):
            if not (root / lang / name).is_file():
                raise FileNotFoundError(f"Expected bilingual LaTeX source file: {root / lang / name}")
    parsers = {lang: BookParser(root / lang, lang, graph_ids, auxiliary).finish() for lang in ("EN", "ITA")}
    merged = combine_units(parsers["EN"].units, parsers["ITA"].units)
    if len({u["id"] for u in merged}) != len(merged):
        raise ValueError("Duplicate book unit identities; introduce an explicit structural/parser migration")
    chapters = [u for u in merged if u["kind"] == "chapter"]
    if not chapters or [u["number"] for u in chapters] != list(range(1, len(chapters) + 1)):
        raise ValueError("No sequential active main-matter chapters were found")
    nonchapters = [u for u in merged if u["kind"] != "chapter"]
    previous_by_id = {c["id"]: c for c in (previous or {}).get("chapters", [])}
    reviews = metadata.get("chapter_editorial", {})
    if not isinstance(reviews, dict) or set(reviews) - {c["id"] for c in chapters}:
        raise ValueError("chapter_editorial must be keyed by current chapter IDs only")
    for chapter in chapters:
        _editorial(chapter, previous_by_id, reviews)
    configs = {lang: config_values(root / lang / "config.tex") for lang in parsers}
    config_fields = {"title": ("EN", "booktitle"), "title_it": ("ITA", "booktitle"),
                     "subtitle": ("EN", "booksubtitle"), "subtitle_it": ("ITA", "booksubtitle"),
                     "author": ("EN", "authorname"), "publisher": ("EN", "publishername"), "publication_year": ("EN", "publishyear")}
    book = {key: copy.deepcopy(metadata.get(key, configs[lang].get(source, ""))) for key, (lang, source) in config_fields.items()}
    for key in ("title", "title_it", "author", "publisher", "publication_year"):
        if not str(book[key]).strip():
            raise ValueError(f"Book {key} is absent from config.tex and explicit metadata")
    if not re.fullmatch(r"\d{4}", str(book["publication_year"])):
        raise ValueError("Book publication_year must be an explicit four-digit year")
    edition = metadata.get("edition", (previous or {}).get("book", {}).get("edition"))
    if edition is None:
        raise ValueError("Explicit metadata.edition is required when there is no prior book metadata")
    book.update(id=metadata.get("id", (previous or {}).get("book", {}).get("id", "V06")), edition=edition,
                source_version=version, publication_status=metadata["publication_status"],
                publication_status_basis=metadata["publication_status_basis"], publication_date=metadata.get("publication_date"),
                isbn=metadata.get("isbn"), languages=["EN", "ITA"],
                config_sources={lang: {"file": f"{lang}/config.tex", "sha256": sha(root / lang / "config.tex"), "line": 1} for lang in parsers},
                metadata_note="Titles, author, publisher and year come from config.tex unless explicitly overridden; version and publication assertion come only from supplied metadata. No publication date or ISBN is inferred.")
    for optional in ("publication_confirmation_date", "version_sources", "url"):
        if optional in metadata:
            book[optional] = copy.deepcopy(metadata[optional])
    alignment = []
    blockers = []
    old_hubs = {c["id"]: c for c in baseline_payload.get("chapters", [])}
    title_changes = []
    for chapter in chapters:
        old = old_hubs.get(chapter["hub_id"])
        if old is None or clean_tex(old["label"]) != chapter["title"]:
            title_changes.append({"hub_id": chapter["hub_id"], "old_title": old["label"] if old else None, "published_title": chapter["title"]})
        counts = {lang: collections.Counter(c["bibkey"] for c in chapter["citations" + suffix]) for lang, suffix in (("EN", ""), ("ITA", "_it"))}
        en_ids, it_ids = set(chapter["source_ids"]), set(chapter["source_ids_it"])
        en_keys, it_keys = set(chapter["bibkeys"]), set(chapter["bibkeys_it"])
        en_sections = [(s["id"], s["level"], s["number"], s["label"], s["starred"]) for s in chapter["sections"]]
        it_sections = [(s["id"], s["level"], s["number"], s["label"], s["starred"]) for s in chapter["sections_it"]]
        entry = {"chapter": chapter["id"], "source_ids_match": en_ids == it_ids, "bibkeys_match": en_keys == it_keys,
                 "only_en": sorted(en_keys - it_keys), "only_it": sorted(it_keys - en_keys),
                 "occurrence_counts_match": counts["EN"] == counts["ITA"],
                 "occurrence_count_differences": [{"bibkey": key, "en": counts["EN"][key], "it": counts["ITA"][key]} for key in sorted(en_keys | it_keys) if counts["EN"][key] != counts["ITA"][key]],
                 "section_counts_en": len(en_sections), "section_counts_it": len(it_sections), "section_identities_match": en_sections == it_sections}
        alignment.append(entry)
        if not all(entry[key] for key in ("source_ids_match", "bibkeys_match", "occurrence_counts_match", "section_identities_match")):
            blockers.append({"kind": "bilingual_alignment", "chapter": chapter["id"], "detail": entry})
    for lang, parser in parsers.items():
        unresolved = sorted({entry["bibkey"] for entry in parser.bibliography["entries"] if not entry["source_id"]})
        if unresolved:
            blockers.append({"kind": "unresolved_bibliography", "language": lang, "bibkeys": unresolved})
        if parser.warnings:
            blockers.append({"kind": "source_reference_warnings", "language": lang, "warnings": copy.deepcopy(parser.warnings)})
        # The normalized Atlas field `printed` describes bibliography presence,
        # not merely a loaded .bib file. This adapter supports a complete printed
        # bibliography, as in the supplied book. A filtered/incomplete print route
        # needs a reviewed adapter instead of silently marking every loaded entry.
        selected = {key.strip() for directive in parser.nocites for key in directive["argument"].split(",")}
        cited = {citation["bibkey"] for unit in parser.units for bucket in ("citations", "index_citations") for citation in unit[bucket]}
        complete = "*" in selected or set(parser.bibliography["loaded_keys"]).issubset(selected | cited)
        filtered = any(re.search(r"(?:^|,)\s*(?:type|nottype|keyword|notkeyword|category|notcategory|segment|section|filter|check)\s*=", option)
                       for directive in parser.bibliography_prints for option in directive["options"])
        if not parser.bibliography_prints or not complete or filtered:
            blockers.append({"kind": "bibliography_print_scope_requires_review", "language": lang,
                             "reason": "Loaded bibliography entries cannot all be marked printed without an unfiltered complete print route",
                             "all_loaded_entries_selected": complete, "filtered_print": filtered,
                             "print_directives": copy.deepcopy(parser.bibliography_prints)})
    bibliography_keys_align = parsers["EN"].bibliography["loaded_keys"] == parsers["ITA"].bibliography["loaded_keys"]
    if not bibliography_keys_align:
        blockers.append({"kind": "bilingual_bibliography_mismatch"})
    for unit in nonchapters:
        en = collections.Counter(c["bibkey"] for c in unit["citations"])
        it = collections.Counter(c["bibkey"] for c in unit["citations_it"])
        if en != it:
            blockers.append({"kind": "bilingual_nonchapter_citations", "unit_id": unit["id"],
                             "en_counts": dict(en), "it_counts": dict(it)})
    pending = [c["id"] for c in chapters if c["editorial_review_required"]]
    manifests = {lang: sorted(parser.manifest.values(), key=lambda f: f["file"]) for lang, parser in parsers.items()}
    return {
        "meta": {"schema_version": "1.0", "extracted_on": extraction_date, "source_version": version,
                 "source_root": "supplied_bilingual_sources", "scope": "Metadata and literal source locators of the active EN/ITA LaTeX trees; no full chapter bodies exported",
                 "baseline_payload_sha256": _digest(baseline_payload), "parser_sha256": sha(Path(__file__).with_name("extract_ndse2_base.py")),
                 "extractor_sha256": sha(Path(__file__)), "explicit_metadata_sha256": _digest(metadata),
                 "editorial_review_required": bool(pending), "editorial_pending_chapters": pending,
                 "build_blocked": bool(pending or blockers), "extraction_blockers": blockers},
        "book": book, "chapters": chapters, "nonchapter_units": nonchapters,
        "bibliography": {lang: parser.bibliography for lang, parser in parsers.items()}, "source_manifest": manifests,
        "include_tree": {lang: parser.includes for lang, parser in parsers.items()},
        "citation_macro_rules": {
            "literal_macros": sorted(set.union(*(parser.citation_macros for parser in parsers.values()))),
            "custom_wrappers": {lang: parser.definitions for lang, parser in parsers.items()}, "identifier_links": sorted(IDENTIFIER_MACROS),
            "metadata_only_macros": sorted(METADATA_MACROS),
            "excluded": "Definitions, comments, verbatim/listing content, nocite directives and source-identifier-index calls do not form chapter citation edges.",
            "earlier_volume_mapping": {nid.rsplit(":", 1)[-1]: nid for nid in graph_ids if re.fullmatch(r"PUB:V11:V\d{2,}", nid)},
            "auxiliary_bibliography_mapping": auxiliary,
            "scope_note": "Actively imported learning material, examples, exercises and captions keep literal source use; introduction and appendices retain separate scopes."},
        "audit": {"totals": {lang: _totals(parser) for lang, parser in parsers.items()}, "chapter_alignment": alignment,
            "all_chapter_source_sets_match": all(a["source_ids_match"] and a["bibkeys_match"] for a in alignment),
            "all_chapter_occurrence_counts_match": all(a["occurrence_counts_match"] for a in alignment),
            "all_chapter_section_identities_match": all(a["section_identities_match"] for a in alignment),
            "chapter_title_changes_from_baseline": title_changes, "bibliography_keys_align": bibliography_keys_align,
            "editorial_reused_chapters": [c["id"] for c in chapters if c["editorial_status"] == "reused_from_byte_identical_chapter_sources"],
            "editorial_reviewed_chapters": [c["id"] for c in chapters if c["editorial_status"] == "reviewed_against_current_sources"],
            "editorial_pending_chapters": pending, "extraction_blockers": blockers,
            "nonchapter_alignment": [{"unit_id": u["id"], "kind": u["kind"], "source_ids_match": u["source_ids"] == u["source_ids_it"],
                                     "only_en": sorted(set(u["bibkeys"]) - set(u["bibkeys_it"])), "only_it": sorted(set(u["bibkeys_it"]) - set(u["bibkeys"]))} for u in nonchapters],
            "limitations": ["This bounded source parser establishes active source use, not empirical verification of a cited claim.",
                "It is not a general TeX interpreter. Unexpected active body conditionals fail explicitly.",
                "Bilingual source-ID and occurrence alignment does not prove semantic equivalence of translations.",
                "Bibliography loading and identifier-index links are separate from literal chapter citations.",
                "New or moved chapter/section identities require the separate graph migration review.",
                "Editorial summaries/goals require unchanged source fingerprints or explicit review against the current fingerprint."]},
    }
