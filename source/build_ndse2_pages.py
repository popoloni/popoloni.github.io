"""Render concise NDSE2 companion material from extracted, traceable book metadata.

This helper does not parse manuscripts, infer citations or reproduce chapter bodies.
All HTML remains useful without JavaScript. The caller supplies site-relative links.
"""
from __future__ import annotations

import collections
import html
import json
import posixpath
from pathlib import Path
from urllib.parse import urlsplit


def esc(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def valid_url(value):
    try:
        parsed = urlsplit(value or "")
        return value if parsed.scheme in {"http", "https"} and parsed.netloc else ""
    except (TypeError, ValueError):
        return ""


def publication_fields(publication):
    """Keep storefront presentation separate from bibliographic and citation data."""
    fields = {"cover_image", "cover_alt", "cover_width", "cover_height", "companion_url", "kindle_url"}
    return {key: value for key, value in (publication or {}).items()
            if key.startswith("amazon_") or key in fields}


def book_cover(path, link, book, *, caption=""):
    """Show the supplied local artwork at its original aspect ratio."""
    source = book.get("cover_image", "")
    if not source:
        return ""
    if not source.startswith("assets/books/") or ".." in source.split("/"):
        raise ValueError(f"Book artwork must be a local assets/books/ file: {source}")
    dimensions = ""
    for key, attribute in [("cover_width", "width"), ("cover_height", "height")]:
        value = int(book.get(key) or 0)
        if value > 0:
            dimensions += f' {attribute}="{value}"'
    image = (f'<img src="{esc(posixpath.relpath(source, posixpath.dirname(path) or "."))}"'
             f' alt="{esc(book.get("cover_alt") or book.get("title", "Book cover"))}"'
             f'{dimensions} loading="lazy" decoding="async">')
    destination = valid_url(book.get("amazon_url"))
    if destination:
        image = link(path, destination, image, "book-cover-link", external=True)
    return '<figure class="book-cover">' + image + (f'<figcaption>{esc(caption)}</figcaption>' if caption else '') + '</figure>'


class BookCompanion:
    def __init__(self, source: Path, *, required=False, metadata_link="source/ndse2_book.json", collection_path="catalogues/ndse2.html", publication=None):
        if required and not source.is_file():
            raise FileNotFoundError(f"NDSE2 chapter metadata is required: {source}")
        self.data = json.loads(source.read_text(encoding="utf-8")) if source.is_file() else {}
        self.book = dict(self.data.get("book", {}))
        self.book.update(publication_fields(publication))
        self.metadata_link = metadata_link
        self.collection_path = collection_path
        self.volume_id = self.book.get("id", "V06")
        self.volume_path = f"catalogues/volumes/{self.volume_id.lower()}.html"
        self.chapters = sorted(self.data.get("chapters", []), key=lambda c: c["number"])
        self.by_id = {}
        for chapter in self.chapters:
            self.by_id[chapter["id"]] = chapter
            self.by_id[chapter["hub_id"]] = chapter
        self.bibliography = {}
        for language, data in self.data.get("bibliography", {}).items():
            for entry in data.get("entries", []):
                self.bibliography[(language, entry["bibkey"])] = entry

    def publication_note(self):
        """Describe supplied metadata without inventing a confirmation or date."""
        status = self.book.get("publication_status")
        parts = [f"Publication status as recorded: {str(status).rstrip('.')}."] if status else ["Publication status is not recorded in the supplied metadata."]
        if self.book.get("source_version"):
            parts.append(f"Source edition version: {self.book['source_version']}.")
        if self.book.get("publication_date"):
            parts.append(f"Publication date as recorded: {self.book['publication_date']}.")
        return " ".join(parts)

    def chapter(self, identifier):
        return self.by_id.get(identifier)

    @staticmethod
    def chapter_path(chapter):
        return f'catalogues/chapters/{chapter["hub_id"].split(":")[-1].lower()}.html'

    @staticmethod
    def cited_ids(chapter):
        return sorted(set(chapter.get("source_ids", [])) | set(chapter.get("source_ids_it", [])))

    def introduction(self, path, link, *, heading=False):
        if not self.chapters:
            return ""
        book = self.book
        text = '<section class="section book-feature ndse2-feature">'
        text += book_cover(path, link, book, caption="Non-Deterministic Software Engineering · Second Edition")
        text += '<div class="book-feature-copy"><p class="eyebrow">NDSE2 · Published second edition</p>'
        text += f'<h2>{esc(book.get("title", "Non-Deterministic Software Engineering"))}</h2>'
        if book.get("subtitle"):
            text += f'<p class="book-subtitle">{esc(book["subtitle"])}</p>'
        if book.get("author"):
            text += f'<p class="book-author">By {esc(book["author"])}</p>'
        if book.get("title_it"):
            text += f'<p lang="it">{esc(book["title_it"])}'
            if book.get("subtitle_it"):
                text += f' — {esc(book["subtitle_it"])}'
            text += '</p>'
        text += (
            f'<p class="note">{esc(self.publication_note())} '
            f'{len(self.chapters)} chapter guides connect the English and Italian editions '
            'to their cited sources. Each guide includes an outline, learning goals and citation provenance.</p>'
        )
        text += '<div class="actions">'
        destination = valid_url(book.get("amazon_url"))
        if destination:
            text += link(path, destination, 'View this book on Amazon.com ↗', 'button primary', external=True)
        text += link(path, self.collection_path + '#chapter-guides', 'Browse the chapter guides', 'button' if destination else 'button primary')
        text += '</div><div class="book-reference-links">'
        text += link(path, self.volume_path, 'Edition and source details')
        text += link(path, self.metadata_link, 'Book metadata and citation evidence')
        text += '</div></div></section>'
        return text

    @staticmethod
    def goals(chapter, language="EN"):
        suffix = "_it" if language == "ITA" else ""
        goals = chapter.get("learning_goals" + suffix, [])
        if not goals:
            return ""
        title = "Obiettivi di apprendimento" if language == "ITA" else "Learning goals"
        lang = "it" if language == "ITA" else "en"
        rendered = []
        for goal in goals:
            value = goal.get("text", goal.get("title", "")) if isinstance(goal, dict) else goal
            if value:
                rendered.append(f'<li>{esc(value)}</li>')
        return f'<section lang="{lang}"><h3>{title}</h3><ul>' + ''.join(rendered) + '</ul></section>'

    @staticmethod
    def outline(chapter, language="EN"):
        suffix = "_it" if language == "ITA" else ""
        sections = chapter.get("sections" + suffix, [])
        if not sections:
            return ""
        lang = "it" if language == "ITA" else "en"
        label = "Struttura del capitolo" if language == "ITA" else "Chapter outline"
        parts = []
        for section in sections:
            number = section.get("number", "")
            title = section.get("title", "")
            if not title:
                continue
            # Section numbering is copied from the extraction, never recomputed here.
            prefix = f'<span class="mono">{esc(number)}</span> ' if number else ""
            parts.append('<li>' + prefix + esc(title) + '</li>')
        return f'<details lang="{lang}"><summary>{label}</summary><ul class="compact-list">' + ''.join(parts) + '</ul></details>'

    def chapter_content(self, chapter, path, link, by_id, record_file, *, include_summary=True, include_evidence=True):
        result = ''
        if include_summary:
            result += f'<p class="intro">{esc(chapter.get("summary", ""))}</p>'
            if chapter.get("title_it"):
                result += f'<p class="byline" lang="it"><strong>{esc(chapter["title_it"])}</strong></p>'
            if chapter.get("summary_it"):
                result += f'<details lang="it"><summary>Sintesi in italiano</summary><p>{esc(chapter["summary_it"])}</p></details>'
        result += self.goals(chapter)
        if chapter.get("learning_goals_it"):
            result += '<details><summary lang="it">Obiettivi in italiano</summary>' + self.goals(chapter, 'ITA') + '</details>'
        result += self.outline(chapter)
        if chapter.get("sections_it"):
            result += self.outline(chapter, 'ITA')
        if include_evidence:
            result += self.citation_evidence(chapter, path, link, by_id, record_file)
        return result

    def citation_evidence(self, chapter, path, link, by_id, record_file):
        grouped = collections.defaultdict(list)
        for language, key in [('EN', 'citations'), ('ITA', 'citations_it')]:
            for citation in chapter.get(key, []):
                # Only the extractor's literal chapter citation list is used here.
                # Bibliography membership and identifier mentions do not become citations.
                ident = citation.get('source_id') or 'BIB:' + citation.get('bibkey', '')
                grouped[ident].append((language, citation))
        if not grouped:
            return '<p class="note">No literal source citations were recorded for this chapter.</p>'
        parts = []
        for ident, occurrences in sorted(grouped.items()):
            language, first = occurrences[0]
            entry = self.bibliography.get((language, first.get('bibkey')), {})
            node = by_id.get(ident)
            if node:
                source = link(path, record_file(node), f'<span class="mono">{esc(ident)}</span> · {esc(node["label"])}')
            else:
                title = entry.get('title') or first.get('bibkey') or 'Auxiliary reference'
                href = valid_url(entry.get('url'))
                source = link(path, href, esc(title) + ' ↗', external=True) if href else esc(title)
                source += '<br><span class="micro">Auxiliary bibliography reference; no atlas source ID assigned.</span>'
            locations = []
            seen = set()
            for lang, citation in occurrences:
                loc = (lang, citation.get('section_title'), citation.get('file'), citation.get('line'), citation.get('macro'), citation.get('container'))
                if loc in seen:
                    continue
                seen.add(loc)
                section = citation.get('section_title') or 'Chapter text'
                suffix = ' · figure caption' if citation.get('container') == 'figure_caption' else ''
                text = f'{lang} · {section}{suffix}'
                provenance = f'{citation.get("file", "")}:{citation.get("line", "")}'
                locations.append(f'<li>{esc(text)}<br><span class="micro mono">{esc(provenance)}</span></li>')
            parts.append('<li>' + source + '<ul class="compact-list">' + ''.join(locations) + '</ul></li>')
        return (
            '<details class="section"><summary>Trace literal citations to chapter sections</summary>'
            '<p class="note">Locations come from the supplied English and Italian source files. '
            'Chapter text and figure captions are identified separately; identifier-index references '
            'and general bibliography membership are not treated as chapter citations.</p>'
            '<ul class="compact-list">' + ''.join(parts) + '</ul><p>'
            + link(path, self.metadata_link, 'Complete citation locators and source hashes')
            + '</p></details>'
        )

    def edition_metadata(self, path, link):
        book = self.book
        fields = [
            ('title', 'English title'), ('title_it', 'Italian title'),
            ('subtitle', 'English subtitle'), ('subtitle_it', 'Italian subtitle'),
            ('author', 'Author'), ('publisher', 'Publisher'), ('edition', 'Edition'),
            ('publication_status', 'Publication status'), ('publication_date', 'Publication date'),
            ('isbn', 'ISBN, as recorded'), ('source_version', 'Source edition version'),
        ]
        rows = []
        for key, label in fields:
            value = book.get(key)
            if value not in (None, '', [], {}):
                rows.append(f'<dt>{esc(label)}</dt><dd>{esc(value)}</dd>')
        result = '<dl class="metadata">' + ''.join(rows) + '</dl>'
        if not book.get('publication_date'):
            result += '<p class="micro">No first-publication date is recorded in the supplied metadata.</p>'
        result += '<p>' + link(path, self.metadata_link, 'Edition sources, manifests and citation extraction') + '</p>'
        return result
