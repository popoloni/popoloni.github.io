#!/usr/bin/env python3
"""Extract source metadata and literal citation provenance from NDSE2 LaTeX.

This is a bounded source parser, not a TeX engine. It walks the active input /
include tree in execution order, keeps physical locations, excludes comments,
verbatim and macro definitions, and distinguishes body citations from index
links and bibliography-loading directives. Unexpected conditionals fail rather
than silently inventing which branch was printed.
"""
from __future__ import annotations

import argparse
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

SUMMARIES = {
    1: (
        'Defines an accepted, operable change as the unit of engineering work. The approval-routing case separates business intention, implementation, verification and acceptance, showing why brownfield understanding and explicit decision rights still matter when an AI agent generates the patch.',
        "Definisce il cambiamento accettato e gestibile come unità del lavoro ingegneristico. Il caso di instradamento delle approvazioni distingue intenzione di business, implementazione, verifica e accettazione, mostrando il ruolo della comprensione del sistema e delle responsabilità decisionali anche quando la patch viene generata da un agent."
    ),
    2: (
        'Examines productivity measures from generated output to accepted releases. It distinguishes randomized evidence from observational comparisons and develops a pilot that records review, rework, quality and hidden human effort before an adoption decision.',
        "Esamina la produttività dal codice generato ai rilasci accettati. Distingue le evidenze randomizzate dai confronti osservazionali e sviluppa un progetto pilota che misura revisione, rilavorazione, qualità e lavoro umano poco visibile prima di decidere sull'adozione."
    ),
    3: (
        'Turns agent capability into a bounded engineering hypothesis. Permissions, tools, budgets, stopping rules and escalation constrain execution; the chapter compares execution routes and parallel work while keeping technical completion separate from authorized acceptance.',
        "Trasforma la capacità degli agent in un'ipotesi ingegneristica delimitata. Permessi, strumenti, budget, condizioni di arresto ed escalation vincolano l'esecuzione; il capitolo confronta percorsi operativi e lavoro parallelo distinguendo il completamento tecnico dall'accettazione autorizzata."
    ),
    4: (
        'Develops a versioned intention contract for an existing service. Behavioral examples and acceptance rules are established independently of implementation, while late policy changes trigger targeted impact analysis and invalidate only the decisions and evidence they affect.',
        "Sviluppa un contratto di intenzione versionato per un servizio esistente. Esempi comportamentali e regole di accettazione vengono stabiliti indipendentemente dall'implementazione; le modifiche tardive della policy richiedono un'analisi d'impatto e invalidano solo decisioni ed evidenze coinvolte."
    ),
    5: (
        'Separates immediate correctness from architectural fit and maintenance obligations. Through duplication, post-merge evidence and a second change to the running service, it develops fitness checks and explicit stewardship instead of treating a passing test suite as complete quality assurance.',
        "Distingue la correttezza immediata dalla coerenza architetturale e dagli obblighi di manutenzione. Duplicazioni, evidenze successive al merge e un secondo cambiamento al servizio guidano controlli di adeguatezza e responsabilità di manutenzione esplicite."
    ),
    6: (
        'Threat-models two distinct surfaces: the generated application and the agent runtime. Dependency provenance, prompt injection, tool permissions and external services become enforceable boundaries, with security evidence tied to the release decision.',
        "Analizza due superfici di attacco distinte: l'applicazione generata e il runtime dell'agent. Provenienza delle dipendenze, prompt injection, permessi degli strumenti e servizi esterni diventano vincoli applicabili, collegando le evidenze di sicurezza alla decisione di rilascio."
    ),
    7: (
        'Builds independent verification around authorized behavior. Regression cases, properties, counterexamples and mutants expose circular testing; correlated checker errors and benchmark limits motivate an evidence dossier that supports review without granting the maker acceptance authority.',
        "Costruisce la verifica indipendente a partire dal comportamento autorizzato. Regressioni, proprietà, controesempi e mutanti rivelano i test circolari; errori correlati dei checker e limiti dei benchmark motivano un dossier di evidenze senza attribuire al maker l'autorità di accettazione."
    ),
    8: (
        'Allocates review effort by consequence and uncertainty. It examines human and AI reviewers, false positives, shared blind spots and automation bias, then separates finding disposition, coverage of acceptance obligations and the accountable release verdict.',
        "Distribuisce il lavoro di revisione in base a conseguenze e incertezza. Esamina reviewer umani e AI, falsi positivi, punti ciechi condivisi e automation bias, distinguendo la gestione delle osservazioni, la copertura degli obblighi di accettazione e il verdetto di rilascio."
    ),
    9: (
        'Treats context and persistent memory as claims with provenance, ownership and expiry. It develops software-specific knowledge records and invalidation rules, then uses a handoff and an explicitly limited retrieval comparison to test what a successor can reconstruct.',
        "Tratta context e memoria persistente come affermazioni con provenienza, responsabilità e validità. Sviluppa registrazioni della conoscenza software e regole di invalidazione, usando un passaggio di consegne e un confronto di recupero esplicitamente limitato per verificare ciò che un successore può ricostruire."
    ),
    10: (
        'Distinguishes assisted task completion from retained competence. Mentoring, explanations, repairs and deliberate practice lead to delayed retention and transfer checks; proposed competence measures remain instruments to validate rather than established scores.',
        "Distingue il completamento assistito di un compito dalla competenza conservata. Mentoring, spiegazioni, correzioni e pratica deliberata conducono a verifiche differite di ritenzione e trasferimento; le misure di competenza proposte restano strumenti da validare."
    ),
    11: (
        'Moves from individual output to team throughput and decision rights. Policy owners, makers, checkers and release authorities coordinate parallel work and late intention changes, with operational feedback and review capacity governing staged, reversible adoption.',
        "Passa dall'output individuale alla capacità di consegna del team e ai diritti decisionali. Responsabili delle policy, maker, checker e autorità di rilascio coordinano lavoro parallelo e cambiamenti tardivi delle intenzioni, governando un'adozione graduale e reversibile con feedback operativo e capacità di revisione."
    ),
    12: (
        'Evaluates the economics of the whole engineering loop, including human effort, failed attempts, maintenance and risk. Employment evidence and alternative explanations remain separate from forecasts; adoption requires a counterfactual, uncertainty bounds and a reversal condition.',
        "Valuta l'economia dell'intero ciclo ingegneristico, includendo lavoro umano, tentativi falliti, manutenzione e rischio. Mantiene separate evidenze sul lavoro, spiegazioni alternative e previsioni; l'adozione richiede un controfattuale, limiti d'incertezza e una condizione di reversibilità."
    ),
    13: (
        'Selects and combines practices from the observed problem rather than a fixed workflow. It compares proportionate responses, exposes over-engineering and unsafe shortcuts, and connects earlier volumes while asking which mechanisms can be omitted without losing the change obligations.',
        "Seleziona e combina le pratiche a partire dal problema osservato. Confronta risposte proporzionate, rende visibili sovraingegnerizzazione e scorciatoie rischiose e collega i volumi precedenti, chiedendo quali meccanismi si possano omettere preservando gli obblighi del cambiamento."
    ),
}


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
        self.root = root
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
        rel = str(Path(rel))
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
        if re.fullmatch(r'V0[1-5]', key):
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
                if env == 'document':
                    self.body = name == 'begin'
                    if self.body:
                        self.mode = 'front'
                continue
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
            if name in self.citation_macros | IDENTIFIER_MACROS | METADATA_MACROS:
                _, p = optional_args(text, i)
                keys, i, _ = argument(text, p)
                self.cite(name, keys, rel, start)
                continue

    def read_bibliography(self):
        resources, entries = [], []
        for rel, inclusion in self.loaded_resources:
            path = self.root / rel
            text = path.read_text()
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
            if unit['kind'] == 'chapter':
                n = unit['number']
                rel = f'didactics/learning{n:02d}.tex'
                txt = self.load(rel)
                content = clean_tex(txt)
                goals = re.split(r'\([123]\)\s*', content)[1:]
                connector = 'and' if self.language == 'EN' else 'e'
                goals = [re.sub(r'(?:,\s*|\s+)' + connector + r'\s*$', '', x).strip(' ,.;') for x in goals]
                unit['learning_goals'] = goals
                unit['learning_goals_locator'] = self.loc(rel, txt.find('\n')+1)
                unit['summary'] = SUMMARIES[n][0 if self.language == 'EN' else 1]
                unit['summary_basis'] = [unit['title_locator'], unit['learning_goals_locator']] + [{k:s[k] for k in ['file','line','sha256']} for s in unit['sections'] if s['level']=='section']
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


def read_graph(path):
    text = path.read_text()
    if path.suffix == '.json':
        return json.loads(text)
    m = re.search(r'<script[^>]+id="graph-data"[^>]*>(.*?)</script>', text, re.S)
    if not m:
        raise ValueError('Cannot locate baseline graph payload')
    return json.loads(m.group(1))


def build(args):
    graph = read_graph(args.baseline)
    graph_ids = {n['id'] for n in graph['nodes']}
    auxiliary_mapping = {n['attributes']['original_key']:n['id'] for n in graph['nodes'] if n.get('kind')=='auxiliary_bibliography' and n.get('attributes',{}).get('original_key')}
    parsers = {lang:BookParser(args.book_root/lang, lang, graph_ids, auxiliary_mapping).finish() for lang in ['EN','ITA']}
    merged = combine_units(parsers['EN'].units, parsers['ITA'].units)
    chapters = [u for u in merged if u['kind']=='chapter']
    nonchapters = [u for u in merged if u['kind']!='chapter']
    assert [u['number'] for u in chapters] == list(range(1,14))
    configs = {lang:config_values(args.book_root/lang/'config.tex') for lang in parsers}
    title_changes = []
    old_hubs = {c['id']:c for c in graph['chapters']}
    old_sections = {n['id']:n for n in graph['nodes'] if n['id'].startswith('S:')}
    section_changes = []
    section_additions = []
    alignment = []
    for c in chapters:
        old = old_hubs[c['hub_id']]['label']
        if clean_tex(old) != c['title']:
            title_changes.append({'hub_id':c['hub_id'],'old_title':old,'published_title':c['title']})
        for s in c['sections']:
            if s['level'] != 'section' or not s['number']:
                continue
            old = old_sections.get('S:' + s['number'])
            if old and old['label'] != s['title']:
                section_changes.append({'legacy_section_id':old['id'],'old_title':old['label'],'published_section_id':s['id'],'published_title':s['title'],'published_locator':{k:s[k] for k in ['file','line','sha256']}})
            old_titles={clean_tex(n['label']) for key,n in old_sections.items() if key.startswith('S:'+str(c['number'])+'.')}
            if s['title'] not in old_titles:
                section_additions.append({'chapter_hub':c['hub_id'],'published_section_id':s['id'],'title':s['title'],'locator':{k:s[k] for k in ['file','line','sha256']}})
        a, b = set(c['source_ids']), set(c['source_ids_it'])
        ka, kb = set(c['bibkeys']), set(c['bibkeys_it'])
        count_en = collections.Counter(x['bibkey'] for x in c['citations'])
        count_it = collections.Counter(x['bibkey'] for x in c['citations_it'])
        alignment.append({'chapter':c['id'],'source_ids_match':a==b,'bibkeys_match':ka==kb,'only_en':sorted(ka-kb),'only_it':sorted(kb-ka),'occurrence_counts_match':count_en==count_it,'occurrence_count_differences':[{ 'bibkey':k,'en':count_en[k],'it':count_it[k]} for k in sorted(ka|kb) if count_en[k]!=count_it[k]],'section_counts_en':len(c['sections']),'section_counts_it':len(c['sections_it'])})
    totals = {}
    for lang,p in parsers.items():
        cs = [u for u in p.units if u['kind']=='chapter']
        ns = [u for u in p.units if u['kind']!='chapter' and u['kind']!='identifier_index']
        totals[lang] = {
            'active_tex_files':len(p.manifest),'chapters':len(cs),'nonchapter_units':len(p.units)-len(cs),
            'chapter_citation_occurrences':sum(len(c['citations']) for c in cs),
            'chapter_unique_source_ids':len({o['source_id'] for c in cs for o in c['citations'] if o['source_id']}),
            'chapter_primary_catalogue_unique_source_ids':len({o['source_id'] for c in cs for o in c['citations'] if o['source_id'] and not o['source_id'].startswith('BIB:')}),
            'chapter_resolved_auxiliary_unique_source_ids':len({o['source_id'] for c in cs for o in c['citations'] if o['source_id'] and o['source_id'].startswith('BIB:')}),
            'chapter_unique_bibkeys':len({o['bibkey'] for c in cs for o in c['citations']}),
            'chapter_identifier_mentions':sum(len(c['identifier_mentions']) for c in cs),
            'chapter_figure_caption_citations':sum(o['container']=='figure_caption' for c in cs for o in c['citations']),
            'chapter_figure_caption_identifier_mentions':sum(o['container']=='figure_caption' for c in cs for o in c['identifier_mentions']),
            'nonchapter_body_citation_occurrences':sum(len(c['citations']) for c in ns),
            'bibliography_loaded_entries':len(p.bibliography['entries']),
            'identifier_index_entries':len(p.bibliography['index_keys']),
            'chapter_source_ids':sorted({o['source_id'] for c in cs for o in c['citations'] if o['source_id']}),
            'chapter_auxiliary_bibkeys':sorted({o['bibkey'] for c in cs for o in c['citations'] if o['resolution']!='existing_graph_node' and o['resolution']!='earlier_published_volume'}),
            'chapter_unresolved_bibkeys':sorted({o['bibkey'] for c in cs for o in c['citations'] if not o['source_id']}),
            'unloaded_reference_warnings':[w for w in p.warnings if w['type']=='unloaded_bibkey'],
        }
    book = {
        'id':'V06','title':configs['EN']['booktitle'],'title_it':configs['ITA']['booktitle'],
        'subtitle':configs['EN']['booksubtitle'],'subtitle_it':configs['ITA']['booksubtitle'],
        'author':configs['EN']['authorname'],'publisher':configs['EN']['publishername'],
        'edition':2,'publication_year':configs['EN']['publishyear'],'source_version':'13.7.1',
        'publication_status':'Published — author-confirmed ' + args.confirmation_date,
        'publication_status_basis':'Author states that NDSE2 has been published in the 2026-10-18 task instruction.',
        'publication_date':None,'isbn':None,'languages':['EN','ITA'],
        'config_sources':{lang:{'file':f'{lang}/config.tex','sha256':sha(args.book_root/lang/'config.tex'),'line':1} for lang in parsers},
        'version_sources':{lang:{'file':f'{lang}/RELEASE_NOTES_V13_7_1.md','sha256':sha(args.book_root/lang/'RELEASE_NOTES_V13_7_1.md'),'line':1} for lang in parsers},
        'metadata_note':'config.tex supplies title, subtitle, author, publisher and year; release-note heading supplies source version. No precise publication date or ISBN inferred.',
    }
    manifests={lang:sorted(p.manifest.values(),key=lambda x:x['file']) for lang,p in parsers.items()}
    output = {
        'meta':{'schema_version':'1.0','extracted_on':args.confirmation_date,'source_version':'13.7.1','source_root':'book_sources','scope':'Metadata of the active EN/ITA LaTeX trees; no full chapter text exported','baseline_graph_sha256':sha(args.baseline),'parser_sha256':sha(Path(__file__))},
        'book':book,'chapters':chapters,'nonchapter_units':nonchapters,
        'bibliography':{lang:p.bibliography for lang,p in parsers.items()},
        'source_manifest':manifests,'include_tree':{lang:p.includes for lang,p in parsers.items()},
        'citation_macro_rules':{
            'literal_macros':sorted(parsers['EN'].citation_macros),
            'custom_wrappers':parsers['EN'].definitions,'identifier_links':sorted(IDENTIFIER_MACROS),
            'metadata_only_macros':sorted(METADATA_MACROS),
            'excluded':'Macro definitions, comments, verbatim/listing content, nocite directives and source-identifier-index citation calls do not form chapter citation edges.',
            'earlier_volume_mapping':{f'V{i:02d}':f'PUB:V11:V{i:02d}' for i in range(1,6)},
            'auxiliary_bibliography_mapping':auxiliary_mapping,
            'scope_note':'Occurrences inside chapters include actively imported learning boxes, examples, exercises and figure captions; appendices and introduction keep their own scope.',
        },
        'audit':{'totals':totals,'chapter_alignment':alignment,'all_chapter_source_sets_match':all(a['source_ids_match'] and a['bibkeys_match'] for a in alignment),'all_chapter_occurrence_counts_match':all(a['occurrence_counts_match'] for a in alignment),'chapter_title_changes_from_baseline':title_changes,'section_title_changes_at_legacy_positions':section_changes,'new_numbered_section_titles':section_additions,'bibliography_keys_align':parsers['EN'].bibliography['loaded_keys']==parsers['ITA'].bibliography['loaded_keys'],'nonchapter_alignment':[{'unit_id':u['id'],'kind':u['kind'],'source_ids_match':u['source_ids']==u['source_ids_it'],'only_en':sorted(set(u['bibkeys'])-set(u['bibkeys_it'])),'only_it':sorted(set(u['bibkeys_it'])-set(u['bibkeys']))} for u in nonchapters],'limitations':['This parser establishes source-level citation occurrence and active inclusion, not empirical verification of a cited claim.','It is not a general TeX interpreter. Unexpected active conditionals raise an error. No such conditionals were found in this source tree.','Translation alignment checks source IDs and occurrence counts, not semantic equivalence of all prose.','A printed bibliography entry does not establish that the work was cited in any chapter.','The numbered chapter hubs stay stable; section numbers are position-specific and are not permanent semantic identifiers.']},
    }
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'out':str(args.out),'totals':{k:{kk:vv for kk,vv in v.items() if kk not in {'chapter_source_ids'}} for k,v in totals.items()},'source_alignment':output['audit']['all_chapter_source_sets_match'],'occurrence_alignment':output['audit']['all_chapter_occurrence_counts_match'],'title_changes':len(title_changes),'section_changes':len(section_changes)},ensure_ascii=False,indent=2))


def main():
    default=Path(__file__).resolve().parent.parent
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--book-root',type=Path,default=default/'book_sources')
    ap.add_argument('--baseline',type=Path,default=default/'baseline/library/source/atlas_v12_original.html')
    ap.add_argument('--out',type=Path,default=default/'research/ndse2_book.json')
    ap.add_argument('--confirmation-date',default='2026-10-18')
    build(ap.parse_args())


if __name__=='__main__':
    main()
