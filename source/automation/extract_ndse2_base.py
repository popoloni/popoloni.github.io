#!/usr/bin/env python3
"""Low-level bounded parser for active bilingual NDSE2 LaTeX source trees.

Extracted from the audited parser; it contains no editorial summaries, fixed
chapter count, publication assertion or release version. It is not a TeX engine. It walks the active input /
include tree in execution order, keeps physical locations, excludes comments,
verbatim and macro definitions, and distinguishes body citations from index
links and bibliography-loading directives. Unexpected conditionals fail rather
than silently inventing which branch was printed.
"""
from __future__ import annotations

import collections
import hashlib
import json
import re
import unicodedata
from pathlib import Path


BASE_CITATIONS = {
    'cite', 'Cite', 'autocite', 'Autocite', 'parencite', 'Parencite',
    'textcite', 'Textcite', 'footcite', 'footcitetext', 'smartcite',
    'supercite', 'citet', 'citep', 'citealt', 'citealp', 'fullcite',
}
IDENTIFIER_MACROS = {'workref'}
METADATA_MACROS = {'citeauthor', 'Citeauthor', 'citetitle', 'citeyear', 'citeyearpar', 'citedate'}
DEFINITIONS = {'newcommand', 'renewcommand', 'providecommand', 'DeclareRobustCommand'}

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def blank(text: str) -> str:
    return ''.join('\n' if c == '\n' else ' ' for c in text)


def mask_noncode(text: str) -> str:
    """Mask ignored TeX text without changing character or physical line offsets."""
    chars = list(text)
    for m in re.finditer(r'\\begin\s*\{(verbatim\*?|Verbatim|lstlisting|minted|comment)\}', text):
        end = re.search(r'\\end\s*\{' + re.escape(m.group(1)) + r'\}', text[m.end():])
        if not end:
            raise ValueError('Unclosed non-executable environment: ' + m.group(1))
        stop = m.end() + end.end()
        chars[m.start():stop] = blank(text[m.start():stop])
    interim = ''.join(chars)
    # Percent starts a comment unless preceded by an odd run of backslashes.
    for m in re.finditer('%', interim):
        i = m.start() - 1
        while i >= 0 and interim[i] == '\\':
            i -= 1
        if (m.start() - 1 - i) % 2 == 0:
            stop = interim.find('\n', m.start())
            if stop < 0:
                stop = len(interim)
            chars[m.start():stop] = ' ' * (stop - m.start())
    interim = ''.join(chars)
    for m in re.finditer(r'\\(?:verb|lstinline)\*?([^\w\s])', interim):
        delim = m.group(1)
        stop = interim.find(delim, m.end())
        if stop >= 0:
            chars[m.start():stop+1] = blank(interim[m.start():stop+1])
    return ''.join(chars)


def skip_space(text: str, i: int) -> int:
    while i < len(text) and text[i].isspace():
        i += 1
    return i


def argument(text: str, i: int, opening: str = '{', closing: str = '}'):
    i = skip_space(text, i)
    if i >= len(text) or text[i] != opening:
        raise ValueError(f'Expected {opening} at {i}: {text[max(0, i-30):i+80]!r}')
    start = i + 1
    depth = 1
    i += 1
    while i < len(text):
        if text[i] == '\\':
            # Escaped brace is a printable character, not structural nesting.
            if i + 1 < len(text) and text[i+1] in '{}[]%\\':
                i += 2
                continue
        if text[i] == opening:
            depth += 1
        elif text[i] == closing:
            depth -= 1
            if depth == 0:
                return text[start:i], i + 1, start
        i += 1
    raise ValueError('Unclosed argument')


def optional_args(text: str, i: int):
    args = []
    i = skip_space(text, i)
    if i < len(text) and text[i] == '*':
        i += 1
    while True:
        i = skip_space(text, i)
        if i < len(text) and text[i] == '[':
            val, i, _ = argument(text, i, '[', ']')
            args.append(val)
        else:
            return args, i


def clean_tex(text: str) -> str:
    text = text.replace('\\textquotesingle{}', "'").replace('\\textquotesingle', "'")
    text = text.replace('\\textquoteright', "'").replace('\\&', '&')
    text = text.replace('\\_', '_').replace('\\%', '%').replace('~', ' ')
    accents = {'"': '\u0308', "'": '\u0301', '`': '\u0300', '^': '\u0302', '~': '\u0303', 'c': '\u0327'}
    def accent(m):
        return unicodedata.normalize('NFC', m.group(2) + accents[m.group(1)])
    text = re.sub(r'''\\(["'`^~c])\s*\{?([A-Za-z])\}?''', accent, text)
    text = re.sub(r'\\(?:label|ref|pageref|cite\w*|autocite)\s*\{[^{}]*\}', '', text)
    text = re.sub(r'\\(?:begin|end)\s*\{[^{}]*\}(?:\[[^\]]*\])?', '', text)
    text = re.sub(r'\\[A-Za-z]+\*?', '', text)
    text = text.replace('---', '—').replace('--', '–')
    text = text.replace('``', '“').replace("''", '”')
    text = text.replace('{', '').replace('}', '').replace('\\', '')
    return re.sub(r'\s+', ' ', text).strip()


def read_definitions(text: str):
    out = []
    pat = re.compile(r'\\(newcommand|renewcommand|providecommand|DeclareRobustCommand)\*?\s*\{\\([A-Za-z]+)\}')
    for m in pat.finditer(text):
        _, pos = optional_args(text, m.end())
        body, end, _ = argument(text, pos)
        out.append({'name': m.group(2), 'body': body, 'offset': m.start(), 'end': end})
    return out


def config_values(path: Path):
    text = mask_noncode(path.read_text())
    return {x['name']: clean_tex(x['body']) for x in read_definitions(text)}


def parse_bib_fields(body: str):
    values = {}
    pos = 0
    while pos < len(body):
        m = re.search(r'\b([A-Za-z][A-Za-z0-9_]*)\s*=\s*', body[pos:])
        if not m:
            break
        key = m.group(1).lower()
        start = pos + m.end()
        if start < len(body) and body[start] == '{':
            value, pos, _ = argument(body, start)
        elif start < len(body) and body[start] == '"':
            end = start + 1
            while end < len(body) and (body[end] != '"' or body[end-1] == '\\'):
                end += 1
            value, pos = body[start+1:end], end + 1
        else:
            end = body.find(',', start)
            if end < 0:
                end = len(body)
            value, pos = body[start:end].strip(), end + 1
        values[key] = value.strip()
    return values


class BookParser:
    def __init__(self, root: Path, language: str, graph_ids: set[str], auxiliary_mapping: dict[str, str]):
        self.root = Path(root).resolve()
        self.language = language
        self.graph_ids = graph_ids
        self.auxiliary_mapping = auxiliary_mapping
        self.cache = {}
        self.manifest = {}
        self.includes = []
        self.units = []
        self.current = None
        self.current_section = None
        self.section_counts = [0, 0, 0]
        self.mode = 'preamble'
        self.body = False
        self.part = None
        self.chapter_number = 0
        self.appendix_number = 0
        self.caption_regions = []
        self.last_structure = None
        self.loaded_resources = []
        self.nocites = []
        self.bibliography_prints = []
        self.definitions = []
        self.warnings = []
        self.citation_macros = set(BASE_CITATIONS)
        pre = self.load('preamble.tex')
        for d in read_definitions(pre):
            invoked = set(re.findall(r'\\([A-Za-z]+)', d['body']))
            if invoked & (BASE_CITATIONS | METADATA_MACROS) and d['name'] not in IDENTIFIER_MACROS:
                self.citation_macros.add(d['name'])
                self.definitions.append({'macro': d['name'], 'expands_to': sorted(invoked & (BASE_CITATIONS | METADATA_MACROS | IDENTIFIER_MACROS)), **self.loc('preamble.tex', d['offset'])})
        self.bibliography = None

    def load(self, rel):
        candidate = (self.root / rel).resolve()
        if not candidate.is_relative_to(self.root):
            raise ValueError('LaTeX source escapes its supplied language root: ' + str(rel))
        rel = candidate.relative_to(self.root).as_posix()
        if rel not in self.cache:
            p = self.root / rel
            if not p.is_file():
                raise FileNotFoundError(p)
            raw = p.read_text(encoding='utf-8')
            self.cache[rel] = mask_noncode(raw)
            self.manifest[rel] = {'file': f'{self.language}/{rel}', 'sha256': sha(p), 'physical_lines': len(raw.splitlines()), 'bytes': p.stat().st_size}
        return self.cache[rel]

    def loc(self, rel, pos):
        text = self.load(rel)
        return {'file': f'{self.language}/{rel}', 'line': text.count('\n', 0, pos) + 1, 'sha256': self.manifest[rel]['sha256']}

    def resolve_id(self, key):
        if key in self.auxiliary_mapping:
            return self.auxiliary_mapping[key], 'existing_auxiliary_bibliography_node'
        if re.fullmatch(r'V\d{2,}', key):
            candidate = 'PUB:V11:' + key
            if candidate in self.graph_ids:
                return candidate, 'earlier_published_volume'
        if key in self.graph_ids:
            return key, 'existing_graph_node'
        return None, 'auxiliary_bibkey_without_graph_node'

    def touch(self, rel):
        if self.current and rel != 'main.tex' and rel not in self.current['_files']:
            self.current['_files'].append(rel)

    def new_unit(self, title, starred, rel, pos, end):
        if self.mode == 'main' and not starred:
            self.chapter_number += 1
            n = self.chapter_number
            uid, kind, hub = f'NDSE2:C{n:02d}', 'chapter', f'C:C{n:02d}'
        elif self.mode == 'appendix' and not starred:
            self.appendix_number += 1
            n = chr(64 + self.appendix_number)
            uid, kind, hub = 'NDSE2:APP:' + n, 'appendix', None
        elif 'work_id_index' in rel:
            n, uid, kind, hub = None, 'NDSE2:INDEX', 'identifier_index', None
        else:
            n, uid, kind, hub = None, 'NDSE2:INTRO', 'introduction', None
        self.current = {
            'id': uid, 'hub_id': hub, 'number': n, 'kind': kind, 'title': clean_tex(title),
            'part': self.part, 'root_file': f'{self.language}/{rel}',
            'root_sha256': self.manifest[rel]['sha256'], 'title_locator': self.loc(rel, pos),
            'sections': [], 'citations': [], 'identifier_mentions': [],
            'metadata_references': [], 'index_citations': [], '_files': [], 'labels': [],
        }
        self.units.append(self.current)
        self.current_section = None
        self.section_counts = [0, 0, 0]
        self.last_structure = (self.current, rel, end)
        self.touch(rel)

    def new_section(self, name, title, starred, rel, pos, end):
        if not self.current:
            return
        depth = ['section', 'subsection', 'subsubsection'].index(name)
        if not starred:
            self.section_counts[depth] += 1
            for k in range(depth+1, 3):
                self.section_counts[k] = 0
            number_parts = [str(self.current['number'])] + [str(x) for x in self.section_counts[:depth+1]]
            number = '.'.join(number_parts) if self.current['number'] is not None else None
        else:
            number = None
        if self.current['kind'] == 'chapter':
            stem = f'NDSE2:S{self.current["number"]:02d}'
        else:
            stem = self.current['id'] + ':S'
        if number:
            sid = stem + '.' + '.'.join(f'{x:02d}' for x in self.section_counts[:depth+1])
        else:
            sid = stem + '.s' + f'{len(self.current["sections"])+1:02d}'
        record = {'id': sid, 'level': name, 'number': number, 'title': clean_tex(title), 'label': None, 'labels': [], 'starred': starred, **self.loc(rel, pos)}
        self.current['sections'].append(record)
        self.current_section = record
        self.last_structure = (record, rel, end)
        self.touch(rel)

    def cite(self, name, raw_keys, rel, pos):
        if not self.current:
            self.warnings.append({'type': 'citation_outside_unit', 'macro': name, 'argument': raw_keys, **self.loc(rel, pos)})
            return
        for key in [x.strip() for x in raw_keys.split(',') if x.strip()]:
            target, resolution = self.resolve_id(key)
            caption = any(r == rel and a <= pos < b for r, a, b in self.caption_regions)
            record = {
                'bibkey': key, 'source_id': target, 'resolution': resolution, 'macro': name,
                'chapter_hub': self.current['hub_id'], 'unit_id': self.current['id'],
                'unit_kind': self.current['kind'],
                'section_id': self.current_section['id'] if self.current_section else None,
                'section_title': self.current_section['title'] if self.current_section else None,
                'container': 'figure_caption' if caption else 'body', **self.loc(rel, pos),
            }
            if self.current['kind'] == 'identifier_index':
                record['container'] = 'identifier_index'
                bucket = 'identifier_mentions' if name in IDENTIFIER_MACROS else 'index_citations'
            elif name in IDENTIFIER_MACROS:
                bucket = 'identifier_mentions'
            elif name in METADATA_MACROS:
                bucket = 'metadata_references'
            else:
                bucket = 'citations'
            self.current[bucket].append(record)
        self.touch(rel)

    def walk(self, rel, stack=()):
        rel = str(Path(rel).with_suffix('.tex'))
        if rel in stack:
            raise ValueError('Cyclic inclusion: ' + ' -> '.join(stack + (rel,)))
        text = self.load(rel)
        if self.body and not re.search(r'\\chapter\*?\s*\{', text):
            self.touch(rel)
        i = 0
        while i < len(text):
            if text[i] != '\\':
                i += 1
                continue
            m = re.match(r'\\([A-Za-z@]+|.)', text[i:])
            if not m:
                i += 1
                continue
            start, name = i, m.group(1)
            i += m.end()
            if name in DEFINITIONS:
                i = skip_space(text, i)
                if i < len(text) and text[i] == '*':
                    i += 1
                _, p, _ = argument(text, i)
                _, p = optional_args(text, p)
                _, i, _ = argument(text, p)
                continue
            if name in {'input', 'include'}:
                target, i, _ = argument(text, i)
                if '\\' in target or '#' in target:
                    raise ValueError('Unresolved dynamic inclusion: ' + target)
                target = str(Path(target).with_suffix('.tex'))
                self.includes.append({'target_file': f'{self.language}/{target}', **self.loc(rel, start)})
                self.walk(target, stack + (rel,))
                continue
            if name == 'addbibresource':
                _, p = optional_args(text, i)
                resource, i, _ = argument(text, p)
                self.loaded_resources.append((resource, self.loc(rel, start)))
                continue
            if name in {'begin', 'end'}:
                env, i, _ = argument(text, i)
                if env in {'refsection', 'refsegment'}:
                    raise ValueError(f'Unsupported scoped bibliography {env} in {rel}:{self.loc(rel,start)["line"]}')
                if env == 'document':
                    self.body = name == 'begin'
                    if self.body:
                        self.mode = 'front'
                continue
            if name in {'includeonly', 'InputIfFileExists', 'IfFileExists'}:
                raise ValueError(f'Uninterpreted source-selection directive {name} in {rel}:{self.loc(rel,start)["line"]}')
            if not self.body:
                continue
            if name.startswith('if') or name in {'else', 'fi', 'includeonly', 'InputIfFileExists'}:
                raise ValueError(f'Uninterpreted active conditional {name} in {rel}:{self.loc(rel,start)["line"]}')
            if name in {'frontmatter', 'mainmatter', 'appendix', 'backmatter'}:
                self.mode = {'frontmatter':'front','mainmatter':'main','appendix':'appendix','backmatter':'back'}[name]
                if name == 'backmatter':
                    self.current = None
                    self.current_section = None
                continue
            if name in {'part', 'addpart'}:
                _, p = optional_args(text, i)
                title, i, _ = argument(text, p)
                self.part = clean_tex(title)
                continue
            if name in {'chapter', 'section', 'subsection', 'subsubsection'}:
                starred = text[skip_space(text, i):].startswith('*')
                _, p = optional_args(text, i)
                title, i, _ = argument(text, p)
                if name == 'chapter':
                    self.new_unit(title, starred, rel, start, i)
                else:
                    self.new_section(name, title, starred, rel, start, i)
                continue
            if name == 'label':
                label, i, _ = argument(text, i)
                if self.last_structure:
                    record, lastrel, after = self.last_structure
                    if rel == lastrel and not text[after:start].strip():
                        record.setdefault('labels', []).append(label)
                        if 'label' in record and record['label'] is None:
                            record['label'] = label
                        self.last_structure = (record, rel, i)
                continue
            if name == 'caption':
                _, p = optional_args(text, i)
                _, end, begin = argument(text, p)
                self.caption_regions.append((rel, begin, end))
                # Continue lexing inside the caption to collect literal citations.
                i = begin
                continue
            if name == 'nocite':
                _, p = optional_args(text, i)
                value, i, _ = argument(text, p)
                self.nocites.append({'argument': value, 'scope': self.mode, **self.loc(rel, start)})
                continue
            if name == 'printbibliography':
                options, i = optional_args(text, i)
                self.bibliography_prints.append({'options': options, 'scope': self.mode, **self.loc(rel, start)})
                continue
            if name in self.citation_macros | IDENTIFIER_MACROS | METADATA_MACROS:
                _, p = optional_args(text, i)
                keys, i, _ = argument(text, p)
                self.cite(name, keys, rel, start)
                continue

    def read_bibliography(self):
        resources, entries = [], []
        for rel, inclusion in self.loaded_resources:
            path = (self.root / rel).resolve()
            if not path.is_relative_to(self.root):
                raise ValueError('Bibliography escapes its supplied language root: ' + str(rel))
            text = path.read_text(encoding='utf-8')
            digest = sha(path)
            matches = list(re.finditer(r'^[ \t]*@([A-Za-z]+)\s*\{\s*([^,\s]+)\s*,', text, re.M))
            count = 0
            for m in matches:
                if m.group(1).lower() in {'string', 'comment', 'preamble'}:
                    continue
                # Full entry body preserves nested title braces.
                brace = text.index('{', m.start())
                whole, _, _ = argument(text, brace)
                fields = parse_bib_fields(whole.split(',', 1)[1])
                key = m.group(2)
                source, resolution = self.resolve_id(key)
                entries.append({
                    'bibkey': key, 'source_id': source, 'resolution': resolution,
                    'entry_type': m.group(1), 'stable_printed_id': fields.get('usera'),
                    'title': clean_tex(fields.get('title', '')),
                    'authors': clean_tex(fields.get('author', '')),
                    'url': fields.get('url', ''), 'doi': fields.get('doi', ''),
                    'year': fields.get('date', fields.get('year', '')),
                    'file': f'{self.language}/{rel}', 'line': text.count('\n', 0, m.start()) + 1,
                    'sha256': digest,
                })
                count += 1
            resources.append({'file': f'{self.language}/{rel}', 'sha256': digest, 'entry_count': count, 'loaded_at': inclusion})
        keys = [x['bibkey'] for x in entries]
        if len(keys) != len(set(keys)):
            raise ValueError('Duplicate loaded bibliography keys')
        index_units = [u for u in self.units if u['kind'] == 'identifier_index']
        index_keys = sorted({x['bibkey'] for u in index_units for x in u['index_citations']})
        self.bibliography = {
            'resources': resources, 'entries': entries, 'loaded_keys': sorted(keys),
            'index_keys': index_keys, 'nocite_directives': self.nocites,
            'print_directives': self.bibliography_prints,
            'loaded_not_in_identifier_index': sorted(set(keys)-set(index_keys)),
            'index_not_loaded': sorted(set(index_keys)-set(keys)),
            'note': 'Resource/index membership and nocite do not create a literal chapter citation.',
        }

    def finish(self):
        self.walk('main.tex')
        self.read_bibliography()
        loaded = set(self.bibliography['loaded_keys'])
        for unit in self.units:
            unit['source_files'] = [self.manifest[p] for p in unit.pop('_files')]
            unit['source_ids'] = sorted({o['source_id'] for o in unit['citations'] if o['source_id']})
            unit['bibkeys'] = sorted({o['bibkey'] for o in unit['citations']})
            unit['unresolved_bibkeys'] = sorted({o['bibkey'] for o in unit['citations'] if not o['source_id']})
            unit['citation_occurrences'] = len(unit['citations'])
            unit['unique_source_count'] = len(unit['source_ids'])
            for bucket in ['citations', 'identifier_mentions', 'metadata_references', 'index_citations']:
                for occ in unit[bucket]:
                    occ['loaded_in_bibliography'] = occ['bibkey'] in loaded
                    if not occ['loaded_in_bibliography']:
                        self.warnings.append({'type':'unloaded_bibkey','bibkey':occ['bibkey'],'file':occ['file'],'line':occ['line']})
        return self


def combine_units(en, it):
    its = {u['id']:u for u in it}
    result = []
    for source in en:
        entry = dict(source)
        translated = its.pop(source['id'], None)
        if translated is None:
            raise ValueError('Missing Italian unit ' + source['id'])
        for k, v in translated.items():
            if k not in {'id','hub_id','number','kind'}:
                entry[k + '_it'] = v
        result.append(entry)
    if its:
        raise ValueError('Extra Italian units ' + ','.join(its))
    return result


