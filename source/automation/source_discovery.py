#!/usr/bin/env python3
"""Discover Atlas source candidates; never edit the graph or infer citations.

Python 3.10+, standard library only. Feed metadata is a discovery hint, not an
article review. The ``discover`` API accepts normalized Atlas payloads or raw
graph JSON containing ``atlas_display`` node metadata. Dates are deliberately
kept as publication vs update, and feed authors are not treated as bylines.

Offline replay: pass a snapshot mapping (endpoint ID -> response), or a JSON
manifest path. Responses accept ``body_file`` (relative to the manifest),
``body_text``, ``entries`` (metadata-only replay), or ``error``. Missing snapshots
are errors: offline mode NEVER silently falls back to the network.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import email.utils
import hashlib
import html
from html.parser import HTMLParser
import ipaddress
import json
from pathlib import Path
import re
import socket
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

SCHEMA_VERSION = "1.0"
USER_AGENT = "KnowledgeAtlasUpdater/1.0 (public feed discovery)"
MAX_BYTES = 8 * 1024 * 1024
MAX_ITEMS = 5000
TRACKING_KEYS = {"fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid", "igshid", "_hsenc", "_hsmi"}
ATOM = "{http://www.w3.org/2005/Atom}"
DC = "{http://purl.org/dc/elements/1.1/}"
ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


def normalize_url(value: str) -> str:
    """Conservative article identity: retain meaningful queries and path case.

    Fragments identify passages within an article, and are removed. Only known
    tracking parameters are removed; ``ref``, ``open``, query order, duplicate
    query parameters, percent encoding and trailing slashes remain meaningful.
    """
    value = str(value or "").strip()
    parts = urllib.parse.urlsplit(value)
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("URL must be an absolute HTTP(S) URL")
    if parts.username or parts.password:
        raise ValueError("Credentials in URLs are not allowed")
    host = parts.hostname.encode("idna").decode("ascii").lower()
    port = parts.port
    if ":" in host:
        host = "[" + host + "]"
    if port and not ((parts.scheme.lower() == "https" and port == 443) or (parts.scheme.lower() == "http" and port == 80)):
        host += ":" + str(port)
    # Do not parse/re-encode the surviving values: signatures and literal '+'
    # versus '%20' may be meaningful to a publisher.
    kept = []
    for pair in parts.query.split("&") if parts.query else []:
        key = urllib.parse.unquote_plus(pair.split("=", 1)[0]).lower()
        if not (key.startswith("utm_") or key in TRACKING_KEYS):
            kept.append(pair)
    return urllib.parse.urlunsplit((parts.scheme.lower(), host, parts.path or "/", "&".join(kept), ""))


def title_key(value: str) -> str:
    value = unicodedata.normalize("NFKC", html.unescape(value or "")).casefold()
    value = value.translate(str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"}))
    return re.sub(r"\s+", " ", value).strip()


def date_day(value) -> str | None:
    """Return the publisher's calendar date, without relabelling updated as pub."""
    if not value:
        return None
    text = str(value).strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return dt.date.fromisoformat(text).isoformat()
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        pass
    try:
        parsed = email.utils.parsedate_to_datetime(text)
        if parsed:
            return parsed.date().isoformat()
    except (ValueError, TypeError, OverflowError):
        pass
    months = {name: i for i, name in enumerate(("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"), 1)}
    match = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", text)
    if match and match[2].lower() in months:
        try:
            return dt.date(int(match[3]), months[match[2].lower()], int(match[1])).isoformat()
        except ValueError:
            pass
    return None


def _text(element) -> str:
    return " ".join("".join(element.itertext()).split()) if element is not None else ""


def _child_text(element, *names) -> str:
    for name in names:
        child = element.find(name)
        if child is not None and _text(child):
            return _text(child)
    return ""


def _podcast_evidence(element) -> list[str]:
    """An audio enclosure alone may be article narration, so it is only a flag."""
    evidence = []
    for tag in ("episode", "episodeType", "season"):
        value = _child_text(element, ITUNES + tag)
        if value:
            evidence.append("itunes:" + tag + "=" + value)
    for category in element.findall("category") + element.findall(ATOM + "category"):
        name = category.get("term", "") or _text(category)
        if title_key(name) in {"podcast", "podcasts", "podcast episode", "podcast episodes"}:
            evidence.append("explicit_feed_category=" + name)
    return evidence


def parse_feed(body: bytes, endpoint: dict) -> list[dict]:
    if re.search(br"<!\s*(DOCTYPE|ENTITY)\b", body, re.I):
        raise ValueError("DTD/entity declarations are not accepted")
    root = ET.fromstring(body)
    if root.tag == ATOM + "feed":
        items = root.findall(ATOM + "entry")
        kind = "atom"
    elif root.tag == "rss":
        items = root.findall("./channel/item")
        kind = "rss"
    else:
        raise ValueError("Expected an RSS or Atom feed; received " + root.tag)
    if len(items) > MAX_ITEMS:
        raise ValueError("Feed entry limit exceeded")
    result = []
    for item in items:
        if kind == "atom":
            links = item.findall(ATOM + "link")
            link = next((x.get("href", "") for x in links if x.get("rel", "alternate") == "alternate" and x.get("type", "text/html") in {"text/html", "application/xhtml+xml"}), "")
            author = "; ".join(_child_text(x, ATOM + "name") for x in item.findall(ATOM + "author"))
            published = _child_text(item, ATOM + "published")
            updated = _child_text(item, ATOM + "updated")
            enclosures = [{"type": x.get("type", ""), "url": x.get("href", "")} for x in links if x.get("rel") == "enclosure"]
        else:
            link = _child_text(item, "link")
            if not link:
                guid = item.find("guid")
                if guid is not None and guid.get("isPermaLink", "true") == "true":
                    link = _text(guid)
            author = _child_text(item, DC + "creator", "author")
            published = _child_text(item, "pubDate", DC + "date")
            updated = _child_text(item, ATOM + "updated", "updated")
            enclosures = [{"type": x.get("type", ""), "url": x.get("url", "")} for x in item.findall("enclosure")]
        title = _child_text(item, ATOM + "title", "title")
        if not link or not title:
            # Missing article identity is an observable parser/coverage warning.
            result.append({"parse_error": "entry_missing_title_or_article_link"})
            continue
        result.append({
            "title": html.unescape(title), "url": urllib.parse.urljoin(endpoint["url"], link),
            "publication_date": date_day(published), "updated_date": date_day(updated),
            "published_raw": published or None, "updated_raw": updated or None,
            "feed_authors": author or None, "author_basis": "Feed metadata; verify the actual article byline",
            "podcast_evidence": _podcast_evidence(item),
            "has_audio_enclosure": any(x["type"].lower().startswith("audio/") for x in enclosures),
            "format_basis": "Feed metadata only; an audio enclosure alone is not proof of a podcast",
        })
    return result


class _IndexParser(HTMLParser):
    """Small metadata-only parser; never evaluate scripts or fetch linked pages."""
    def __init__(self, endpoint):
        super().__init__(convert_charrefs=True)
        self.endpoint = endpoint
        self.stack = []
        self.card = None
        self.field = None
        self.anchor = None
        self.entries = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()
        if tag in {"script", "style"}:
            self.skip_depth += 1
        if self.endpoint["kind"] == "fowler_index":
            if tag == "div" and "page" in classes and self.card is None:
                self.card = {"title": "", "byline": "", "date": "", "url": ""}
                self.stack = ["div"]
            elif self.card is not None and tag == "div":
                self.stack.append("div")
            if self.card is not None and tag == "p":
                self.field = next((x for x in ("title", "byline", "date") if x in classes), None)
            if self.card is not None and self.field == "title" and tag == "a":
                self.card["url"] = urllib.parse.urljoin(self.endpoint["url"], attrs.get("href", ""))
        elif tag == "a" and attrs.get("href"):
            self.anchor = {"url": urllib.parse.urljoin(self.endpoint["url"], attrs["href"]), "title": ""}

    def handle_data(self, data):
        if self.skip_depth:
            return
        if self.card is not None and self.field:
            self.card[self.field] += data
        if self.anchor is not None:
            self.anchor["title"] += data

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.skip_depth = max(0, self.skip_depth - 1)
        if self.endpoint["kind"] == "fowler_index":
            if tag == "p":
                self.field = None
            if tag == "div" and self.card is not None:
                if self.stack:
                    self.stack.pop()
                if not self.stack:
                    c = self.card
                    if c["url"] and c["title"].strip():
                        self.entries.append({"url": c["url"], "title": " ".join(c["title"].split()), "publication_date": date_day(c["date"].strip()), "updated_date": None, "published_raw": c["date"].strip() or None, "updated_raw": None, "feed_authors": " ".join(c["byline"].split()) or None, "author_basis": "Official series index byline; confirm against article", "series_membership_evidence": self.endpoint["url"]})
                    self.card = None
        elif tag == "a" and self.anchor is not None:
            c = self.anchor
            c["title"] = " ".join(c["title"].split())
            if c["title"]:
                c.update({"publication_date": None, "updated_date": None, "feed_authors": None, "author_basis": "Not supplied by index link", "metadata_requires_article_review": True})
                self.entries.append(c)
            self.anchor = None


def parse_index(body: bytes, endpoint: dict) -> list[dict]:
    parser = _IndexParser(endpoint)
    parser.feed(body.decode("utf-8", "replace"))
    prefixes = endpoint.get("article_path_prefixes", [])
    entries = []
    seen = set()
    for entry in parser.entries:
        try:
            url = normalize_url(entry["url"])
        except ValueError:
            continue
        path = urllib.parse.urlsplit(url).path
        if url == normalize_url(endpoint["url"]) or (prefixes and not any(path.startswith(p) for p in prefixes)):
            continue
        if url not in seen:
            seen.add(url)
            entries.append(entry)
    if not entries:
        raise ValueError("No recognizable article metadata; page may require JavaScript or its structure changed")
    if len(entries) > MAX_ITEMS:
        raise ValueError("Index entry limit exceeded; use an explicitly bounded archive review")
    return entries


def _validate_public_url(url, allowed_hosts, resolve=True):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.port not in {None, 443}:
        raise ValueError("Fetches require credential-free HTTPS on port 443")
    host = parts.hostname.lower()
    if host not in allowed_hosts:
        raise ValueError("Fetch/redirect host is outside the explicit allowlist: " + host)
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Local and internal host names are not allowed")
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None
    if literal and not literal.is_global:
        raise ValueError("Private or special-purpose addresses are not allowed")
    if resolve:
        addresses = {x[4][0] for x in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
        if not addresses or any(not ipaddress.ip_address(addr).is_global for addr in addresses):
            raise ValueError("Endpoint DNS did not resolve exclusively to public addresses")


class _PublicRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts, resolve=True):
        self.allowed_hosts = allowed_hosts
        self.resolve = resolve

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_public_url(newurl, self.allowed_hosts, resolve=self.resolve)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch(endpoint, sources):
    hosts = set(sources["allowed_fetch_hosts"])
    # In a configured HTTPS proxy environment the proxy resolves destination
    # DNS. Local resolution may intentionally be unavailable. We retain the
    # explicit hostname allowlist, HTTPS certificate checks, forbidden literal
    # addresses and redirect checks; we never print proxy values/credentials.
    resolve = not bool(urllib.request.getproxies().get("https"))
    _validate_public_url(endpoint["url"], hosts, resolve=resolve)
    opener = urllib.request.build_opener(_PublicRedirect(hosts, resolve=resolve))
    request = urllib.request.Request(endpoint["url"], headers={"User-Agent": USER_AGENT, "Accept": "application/atom+xml,application/rss+xml,application/xml,text/xml,text/html;q=0.8"})
    with opener.open(request, timeout=sources.get("timeout_seconds", 20)) as response:
        _validate_public_url(response.url, hosts, resolve=resolve)
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("Response exceeded the 8 MiB limit")
        return {"body": body, "http_status": response.status, "final_url": response.url, "content_type": response.headers.get("Content-Type", "")}


def _load_json(value):
    return json.loads(Path(value).read_text(encoding="utf-8")) if isinstance(value, (str, Path)) else value


def _snapshot_response(snapshot, directory):
    if isinstance(snapshot, str):
        snapshot = {"body_file": snapshot}
    data = copy.deepcopy(snapshot)
    if data.get("error"):
        raise ValueError(str(data["error"]))
    if int(data.get("http_status", 200)) >= 400:
        raise ValueError("Snapshot HTTP " + str(data["http_status"]))
    if "entries" in data:
        if not isinstance(data["entries"], list) or len(data["entries"]) > MAX_ITEMS:
            raise ValueError("Invalid metadata snapshot entries")
        return data
    if "body_file" in data:
        data["body"] = (directory / data["body_file"]).read_bytes()
    elif "body_text" in data:
        data["body"] = data["body_text"].encode("utf-8")
    else:
        raise ValueError("Snapshot has no body, entries or error")
    if len(data["body"]) > MAX_BYTES:
        raise ValueError("Snapshot exceeded the 8 MiB limit")
    return data


def _nodes(graph):
    for raw in graph.get("nodes", graph.get("records", [])):
        display = raw.get("atlas_display")
        if isinstance(display, str):
            try:
                display = json.loads(display)
            except json.JSONDecodeError:
                display = None
        if isinstance(display, dict):
            yield {"id": raw.get("id"), **display, "attributes": {**{k: v for k, v in raw.items() if k != "atlas_display"}, **display.get("attributes", {})}}
        else:
            yield raw


def _urls(value):
    if isinstance(value, dict):
        for key in ("url", "canonical_url", "source_url"):
            yield from _urls(value.get(key))
    elif isinstance(value, list):
        for entry in value:
            yield from _urls(entry)
    elif isinstance(value, str):
        text = value.strip()
        if text.startswith(("[", "{")):
            try:
                yield from _urls(json.loads(text))
            except json.JSONDecodeError:
                pass
        else:
            for url in re.split(r"[;\n]\s*", text):
                try:
                    yield normalize_url(url)
                except ValueError:
                    pass


def _baseline_indices(graph):
    primary, titles, related = {}, {}, {}
    for node in _nodes(graph):
        attrs = node.get("attributes", {})
        collection = node.get("collection", attrs.get("collection"))
        if collection not in {"O", "P", "F"}:
            continue
        for container in (node, attrs):
            for field in ("url", "canonical_url", "source_url", "source", "alternate_urls", "alternate_publications_json"):
                for url in _urls(container.get(field)):
                    primary.setdefault(url, {})[node["id"]] = node
            for field in ("latest_version_url", "superseded_by_url"):
                for url in _urls(container.get(field)):
                    related.setdefault(url, {})[node["id"]] = node
        label = node.get("label", attrs.get("label", ""))
        if label:
            titles.setdefault((collection, title_key(label)), {})[node["id"]] = node
    return primary, titles, related


def discover(graph, as_of, sources, snapshots=None, since=None) -> dict:
    """Return deterministic candidate metadata, endpoint diagnostics and gaps.

    ``as_of`` and optional ``since`` are inclusive ISO calendar dates. No date
    is derived from wall-clock time. IDs are preserved as ``baseline_ids``;
    new IDs, summaries and mappings are exclusively the later review step.
    """
    graph, sources = _load_json(graph), _load_json(sources)
    as_of = dt.date.fromisoformat(as_of).isoformat()
    since = since or sources.get("since") or graph.get("meta", {}).get("date")
    since = dt.date.fromisoformat(since).isoformat() if since else None
    if since and since > as_of:
        raise ValueError("since must not be after as_of")
    snapshot_directory = Path(snapshots).resolve().parent if isinstance(snapshots, (str, Path)) else Path.cwd()
    snapshots = _load_json(snapshots) if snapshots is not None else None
    if snapshots is not None:
        snapshots = snapshots.get("endpoints", snapshots)
    primary, titles, related = _baseline_indices(graph)
    endpoint_reports, observations, ignored, replay = [], [], [], {}
    for endpoint in sources["endpoints"]:
        if not endpoint.get("enabled", True):
            continue
        report = {"id": endpoint["id"], "url": endpoint["url"], "collection": endpoint["collection"], "kind": endpoint["kind"], "status": "error", "article_count": 0, "warnings": [], "manual_fallback_urls": endpoint.get("manual_fallback_urls", [])}
        try:
            if snapshots is not None:
                if endpoint["id"] not in snapshots:
                    raise ValueError("missing_snapshot; offline mode does not fetch the network")
                saved_response = snapshots[endpoint["id"]]
                if isinstance(saved_response, dict) and saved_response.get("error"):
                    # A response can be HTTP 200 yet fail XML/HTML parsing.
                    # Preserve its fingerprint when replaying that same error.
                    for key in ("response_sha256", "http_status", "final_url", "content_type"):
                        if key in saved_response:
                            report[key] = saved_response[key]
                response = _snapshot_response(saved_response, snapshot_directory)
            else:
                response = _fetch(endpoint, sources)
            if "entries" in response:
                entries = response["entries"]
                report["response_sha256"] = response.get("response_sha256")
            else:
                body = response["body"]
                report["response_sha256"] = hashlib.sha256(body).hexdigest()
                entries = parse_feed(body, endpoint) if endpoint["kind"] in {"rss", "atom"} else parse_index(body, endpoint)
            if not entries:
                raise ValueError("Empty feed/index; coverage cannot be confirmed")
            report.update({"status": "ok", "http_status": response.get("http_status", 200), "final_url": response.get("final_url", endpoint["url"]), "content_type": response.get("content_type", ""), "article_count": len(entries)})
            replay[endpoint["id"]] = {k: report.get(k) for k in ("http_status", "final_url", "content_type", "response_sha256")}
            replay[endpoint["id"]]["entries"] = entries
            dates = []
            for original in entries:
                entry = copy.deepcopy(original)
                if entry.get("parse_error"):
                    report["warnings"].append(entry["parse_error"])
                    continue
                try:
                    url = normalize_url(entry.get("url", ""))
                except ValueError:
                    report["warnings"].append("entry_invalid_article_url")
                    continue
                if not entry.get("title"):
                    report["warnings"].append("entry_missing_title")
                    continue
                allowed = endpoint.get("allowed_article_hosts", sources["allowed_fetch_hosts"])
                if urllib.parse.urlsplit(url).hostname not in allowed:
                    ignored.append({"url": url, "endpoint": endpoint["id"], "reason": "out_of_scope_article_host"})
                    continue
                entry.update({"normalized_url": url, "endpoint": endpoint["id"], "source_url": endpoint["url"], "collection": endpoint["collection"], "scope": endpoint.get("scope", "")})
                entry["publication_date"] = date_day(entry.get("publication_date"))
                entry["updated_date"] = date_day(entry.get("updated_date"))
                dates.extend(d for d in (entry["publication_date"], entry["updated_date"]) if d and d <= as_of)
                observations.append(entry)
            report["oldest_metadata_date"] = min(dates) if dates else None
            report["newest_metadata_date"] = max(dates) if dates else None
            report["baseline_url_overlap"] = len({e["normalized_url"] for e in observations if e["endpoint"] == endpoint["id"] and e["normalized_url"] in primary})
            if endpoint["kind"] in {"rss", "atom"}:
                report["warnings"].append("Rolling feed: archive completeness and silent revisions are not guaranteed")
                if since and (not dates or min(dates) > since):
                    report["warnings"].append("Feed date range does not reach the requested start; inspect the official archive")
            if endpoint["kind"] == "link_index":
                report["warnings"].append("Index links do not establish dates, bylines or complete archive coverage")
            report["warnings"] = sorted(set(report["warnings"]))
        except (ValueError, OSError, ET.ParseError, urllib.error.URLError, KeyError, TypeError) as exc:
            report["error"] = str(exc)
            replay[endpoint["id"]] = {k: report[k] for k in ("response_sha256", "http_status", "final_url", "content_type") if k in report}
            replay[endpoint["id"]]["error"] = str(exc)
        endpoint_reports.append(report)

    grouped = {}
    for entry in observations:
        grouped.setdefault((entry["collection"], entry["normalized_url"]), []).append(entry)
    candidates, known, excluded = [], [], []
    for (collection, url), entries in sorted(grouped.items()):
        # Prefer structured dates/byline metadata over an undated index link.
        entries.sort(key=lambda x: (not bool(x.get("publication_date")), not bool(x.get("updated_date")), x["endpoint"], x["title"]))
        first = entries[0]
        baseline = primary.get(url, {})
        matched_titles = {}
        for entry in entries:
            matched_titles.update(titles.get((collection, title_key(entry["title"])), {}))
        edition_matches = related.get(url, {})
        pub_dates = sorted({e["publication_date"] for e in entries if e.get("publication_date")})
        update_dates = sorted({e["updated_date"] for e in entries if e.get("updated_date")})
        eligible_dates = [d for d in pub_dates + update_dates if d <= as_of]
        flags = []
        record = {
            "candidate_key": collection + ":" + hashlib.sha256(url.encode()).hexdigest()[:16],
            "collection": collection, "title": first["title"], "url": url,
            "publication_date": pub_dates[0] if len(pub_dates) == 1 else None,
            "updated_date": update_dates[-1] if update_dates else None,
            "publication_dates_observed": pub_dates, "updated_dates_observed": update_dates,
            "baseline_ids": sorted(baseline), "possible_syndication_ids": sorted(matched_titles) if not baseline else [],
            "related_edition_ids": sorted(edition_matches),
            "observations": entries, "flags": flags,
            "review_status": "pending_editorial_review", "manuscript_citation_status": "NOT_INFERRED",
            "activity_in_requested_window": bool(eligible_dates and (not since or max(eligible_dates) >= since)),
        }
        if collection == "P" and any(title_key(e["title"]).startswith("the pulse") for e in entries):
            record["decision"] = "exclude_pulse_title_prefix"
            excluded.append(record)
            continue
        evidence = sorted({x for e in entries for x in e.get("podcast_evidence", [])})
        if collection == "P" and evidence:
            record.update({"decision": "exclude_podcast_metadata", "exclusion_evidence": evidence})
            excluded.append(record)
            continue
        if pub_dates and min(pub_dates) > as_of:
            record["decision"] = "outside_as_of_future_publication"
            excluded.append(record)
            continue
        if any(e.get("has_audio_enclosure") for e in entries):
            flags.append("audio_enclosure_requires_format_review; not automatically excluded")
        if not pub_dates:
            flags.append("publication_date_requires_primary_article_verification")
        if len(pub_dates) > 1:
            flags.append("conflicting_publication_dates; do not overwrite baseline")
        if any(d > as_of for d in update_dates):
            flags.append("future_updated_date_is_outside_cutoff")
        if len({title_key(e["title"]) for e in entries}) > 1:
            flags.append("feed_or_index_title_variants")
        if baseline:
            revised = False
            for node in baseline.values():
                attrs = node.get("attributes", {})
                known_update = date_day(attrs.get("updated_date"))
                review = max(filter(None, [since, date_day(attrs.get("review_date")), date_day(attrs.get("snapshot_date")), date_day(attrs.get("atlas_added_on"))]), default=None)
                compared_to = known_update or review or date_day(attrs.get("publication_date"))
                if any(d <= as_of and (not compared_to or d > compared_to) for d in update_dates):
                    revised = True
                known_pub = date_day(attrs.get("publication_date")) or date_day(node.get("year"))
                if known_pub and pub_dates and any(d != known_pub for d in pub_dates):
                    flags.append("publication_date_differs_from_baseline")
                if any(title_key(e["title"]) != title_key(node.get("label", "")) for e in entries):
                    flags.append("title_differs_from_baseline; may be a section announcement")
            record["decision"] = "known_revision_review" if revised else "known_metadata_review" if any("differs_from_baseline" in f for f in flags) else "already_in_baseline"
            (candidates if record["decision"] != "already_in_baseline" else known).append(record)
        else:
            record["decision"] = "possible_syndication_review" if matched_titles else "related_edition_review" if edition_matches else "new_url_review"
            if eligible_dates and since and max(eligible_dates) < since:
                flags.append("older_than_requested_window; possible_backfill")
            candidates.append(record)
        record["flags"] = sorted(set(flags))

    failures = [r["id"] for r in endpoint_reports if r["status"] != "ok"]
    successful = len(endpoint_reports) - len(failures)
    gaps = [{"endpoint": r["id"], "reason": r.get("error", ""), "fallback_urls": r["manual_fallback_urls"]} for r in endpoint_reports if r["status"] != "ok"]
    for r in endpoint_reports:
        if any("does not reach" in w for w in r["warnings"]):
            gaps.append({"endpoint": r["id"], "reason": "feed_window_does_not_reach_since", "fallback_urls": r["manual_fallback_urls"]})
    return {
        "schema_version": SCHEMA_VERSION, "as_of": as_of, "since": since,
        "mode": "offline_snapshot" if snapshots is not None else "live_public_endpoints",
        "status": "blocked_sources" if not successful else "partial" if gaps else "review_required",
        "candidates": candidates, "known_records": known, "excluded": excluded, "ignored_links": ignored,
        "endpoints": endpoint_reports,
        "coverage": {"complete": False, "successful_endpoints": successful, "failed_endpoints": failures, "gaps": gaps,
            "limitations": ["RSS/Atom lists are rolling windows; an overlapping date range is not proof that all publications or revisions were observed.", "Feed entry titles, timestamps and authors can describe announcements or sections; verify the primary article before updating a record.", "Possible syndication, guest authorship, access limits and chapter mappings require editorial review.", "Only public feeds and configured indexes are requested. Embedded feed content is not retained in reports/snapshots; article pages and linked media are not fetched. No manuscript citations or new stable IDs are assigned."]},
        "counts": {"candidates": len(candidates), "known_records": len(known), "excluded": len(excluded), "ignored_links": len(ignored)},
        "metadata_snapshot": {"schema_version": SCHEMA_VERSION, "as_of": as_of, "endpoints": replay},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--as-of", required=True, help="Inclusive ISO date, e.g. 2026-11-18")
    parser.add_argument("--since", help="Inclusive ISO date; default: baseline meta.date")
    parser.add_argument("--sources", type=Path, default=Path(__file__).resolve().parents[1] / "assets" / "sources.json")
    parser.add_argument("--snapshot", type=Path, help="Offline response manifest; no live fallback")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--save-snapshot", type=Path, help="Save metadata-only replay input; no article body")
    parser.add_argument("--require-endpoints", action="store_true", help="Return exit 2 when any endpoint/window is incomplete (report is still written)")
    args = parser.parse_args(argv)
    report = discover(args.graph, args.as_of, args.sources, args.snapshot, args.since)
    snapshot = report.pop("metadata_snapshot")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.save_snapshot:
        args.save_snapshot.parent.mkdir(parents=True, exist_ok=True)
        args.save_snapshot.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "status": report["status"], **report["counts"]}, ensure_ascii=False))
    return 2 if args.require_endpoints and report["status"] in {"partial", "blocked_sources"} else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print("Discovery failed: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
