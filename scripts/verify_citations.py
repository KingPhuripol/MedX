#!/usr/bin/env python3
"""Re-check the literature registry against the primary sources it claims to cite.

Two modes. Offline (the default) proves the registry is internally consistent: the
formatted APA string, the structured fields and the identifiers must agree. Online
(`--online`) goes back to Crossref, the arXiv API and PubMed E-utilities and diffs
what they return against what the registry records.

This is deliberately not part of `run_smoke_test.sh`. A network call in the smoke
test makes "offline" indistinguishable from "broken", and a citation check that
fails on a train is a check people learn to ignore.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "project_state/literature.json"
USER_AGENT = "SeniorProjectHarness/1.0 (citation verification)"
TIMEOUT = 20


def normalize(value: str) -> str:
    """Compare titles by their letters, not by their punctuation or case."""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def from_crossref(doi: str) -> dict[str, str]:
    payload = json.loads(fetch(f"https://api.crossref.org/works/{urllib.parse.quote(doi)}"))["message"]
    found: dict[str, str] = {}
    if payload.get("title"):
        found["title"] = payload["title"][0]
    dates = payload.get("published-print") or payload.get("published-online") or payload.get("issued") or {}
    parts = dates.get("date-parts", [[]])
    if parts and parts[0]:
        found["year"] = str(parts[0][0])
    if payload.get("container-title"):
        found["container"] = payload["container-title"][0]
    for source, target in (("volume", "volume"), ("issue", "issue"), ("page", "pages"), ("article-number", "article_number")):
        if payload.get(source):
            found[target] = str(payload[source])
    if payload.get("author"):
        found["author_count"] = str(len(payload["author"]))
    return found


def from_arxiv(arxiv_id: str) -> dict[str, str]:
    root = ElementTree.fromstring(fetch(f"http://export.arxiv.org/api/query?id_list={arxiv_id}"))
    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    entry = root.find("atom:entry", namespace)
    if entry is None:
        return {}
    found: dict[str, str] = {}
    title = entry.find("atom:title", namespace)
    if title is not None and title.text:
        found["title"] = " ".join(title.text.split())
    published = entry.find("atom:published", namespace)
    if published is not None and published.text:
        found["year"] = published.text[:4]
    found["author_count"] = str(len(entry.findall("atom:author", namespace)))
    return found


def from_pubmed(pmid: str) -> dict[str, str]:
    root = ElementTree.fromstring(fetch(f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&retmode=xml&id={pmid}"))
    found: dict[str, str] = {}
    for item in root.iter("Item"):
        name, text = item.get("Name"), (item.text or "").strip()
        if not text:
            continue
        if name == "Title":
            found["title"] = text.rstrip(".")
        elif name == "PubDate":
            found["year"] = text[:4]
        elif name == "FullJournalName":
            # esummary's "Source" is the ISO abbreviation ("JAMA Netw Open"); APA 7 wants
            # the full journal name, which this field carries.
            found["container"] = text
        elif name == "Volume":
            found["volume"] = text
        elif name == "Issue":
            found["issue"] = text
        elif name == "Pages":
            found["pages"] = text
    return found


def offline_problems(record: dict) -> list[str]:
    """The checks that need no network: the string, the fields and the ids must agree."""
    problems: list[str] = []
    lid = record["reference_id"]
    citation, identifiers = record["citation"], record["identifiers"]
    apa = citation["apa7"]

    if str(citation["year"]) not in apa:
        problems.append(f"{lid}: apa7 does not contain the recorded year {citation['year']}")
    if identifiers["doi"] and identifiers["doi"] not in apa:
        problems.append(f"{lid}: apa7 does not contain the recorded DOI {identifiers['doi']}")
    for field in ("container", "pages", "article_number", "publisher"):
        value = citation.get(field)
        if value and value not in apa:
            problems.append(f"{lid}: apa7 does not contain the recorded {field} {value!r}")
    if citation["authors"] and citation["authors"][0].split(",")[0] not in apa:
        problems.append(f"{lid}: apa7 does not open with the recorded first author")
    if not any(identifiers[key] for key in ("doi", "arxiv_id", "pmid", "url")):
        problems.append(f"{lid}: carries no identifier of any kind")
    return problems


def online_problems(record: dict) -> list[str]:
    lid = record["reference_id"]
    citation, identifiers = record["citation"], record["identifiers"]
    try:
        # PubMed first when we have a PMID: JAMA-family deposits truncate the title at the
        # subtitle in Crossref, and PubMed carries it in full.
        if identifiers["pmid"]:
            found, source = from_pubmed(identifiers["pmid"]), "PubMed"
        elif identifiers["arxiv_id"]:
            found, source = from_arxiv(identifiers["arxiv_id"]), "arXiv API"
        elif identifiers["doi"]:
            found, source = from_crossref(identifiers["doi"]), "Crossref"
        else:
            return [f"{lid}: no identifier to verify against"]
    except (urllib.error.URLError, urllib.error.HTTPError, ElementTree.ParseError, ValueError, KeyError) as exc:
        return [f"{lid}: could not reach the primary source ({exc})"]

    if not found:
        return [f"{lid}: the primary source returned no record for this identifier"]

    problems: list[str] = []
    if "title" in found and normalize(found["title"]) != normalize(citation["title"]):
        # A source that stops at the subtitle is depositing less metadata, not describing a
        # different paper. Say so on stdout so the difference stays visible, but do not fail.
        stem = citation["title"].split(":", 1)[0]
        if normalize(found["title"]) == normalize(stem):
            print(f"  note {lid}: {source} deposits the title without its subtitle; the recorded full title stands")
        else:
            problems.append(f"{lid}: {source} title {found['title']!r} != recorded {citation['title']!r}")
    if "year" in found and found["year"] != str(citation["year"]):
        problems.append(f"{lid}: {source} year {found['year']} != recorded {citation['year']}")
    for field in ("container", "volume", "issue", "pages", "article_number"):
        recorded = citation.get(field)
        if recorded and field in found and normalize(found[field]) != normalize(recorded):
            problems.append(f"{lid}: {source} {field} {found[field]!r} != recorded {recorded!r}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--online", action="store_true", help="Re-fetch every record from its primary source")
    parser.add_argument("--stale-days", type=int, default=None, help="Only re-verify records last verified more than N days ago")
    parser.add_argument("--reference", action="append", help="Limit the run to these reference IDs")
    args = parser.parse_args()

    if not REGISTRY.is_file():
        print(f"no literature registry at {REGISTRY.relative_to(ROOT)}")
        return 0
    references = json.loads(REGISTRY.read_text(encoding="utf-8"))["references"]

    selected = [item for item in references if item["verdict"] == "ACCEPTED"]
    if args.reference:
        wanted = set(args.reference)
        selected = [item for item in selected if item["reference_id"] in wanted]
    if args.stale_days is not None:
        cutoff = date.today() - timedelta(days=args.stale_days)
        selected = [
            item for item in selected
            if not item["verification"]["verified_on"] or date.fromisoformat(item["verification"]["verified_on"]) < cutoff
        ]

    problems: list[str] = []
    for record in selected:
        problems.extend(offline_problems(record))
        if args.online:
            problems.extend(online_problems(record))

    mode = "online" if args.online else "offline"
    if problems:
        print(f"CITATION VERIFICATION FAILED ({len(problems)} problems across {len(selected)} accepted references, {mode})")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print(f"CITATION VERIFICATION PASSED ({len(selected)} accepted references checked, {mode})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
