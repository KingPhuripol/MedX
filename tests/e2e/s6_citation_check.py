"""s6 checker (A08): every NI/CP code used in gold has >=1 ref with PMID or https URL and an accessed date;
spot-check 100% of refs used by gold codes against PubMed E-utilities esummary (title) / live URL fetch.

Usage: python tests/e2e/s6_citation_check.py data/synthetic/v1 data_factory/templates OUT.json
"""
import json, re, sys, time, urllib.request
from pathlib import Path

DS, TPL, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
refs = {r["ref_id"]: r for r in json.loads((TPL / "references.json").read_text())}
ni = {c["code"]: c for c in json.loads((TPL / "next_info_codes.json").read_text())["codes"]}
cp = {c["code"]: c for c in json.loads((TPL / "care_pathways.json").read_text())["pathways"]}

used_ni, used_cp, gold_src = set(), set(), {}
for g in (DS / "gold").glob("*/*.json"):
    d = json.loads(g.read_text())
    for r in d["decision_times"]:
        c = r["care"]
        used_ni |= set(c["next_info"])
        if c["pathway"]:
            used_cp.add(c["pathway"])
        for code, rs in c["next_info_sources"].items():
            gold_src.setdefault(code, set()).update(rs)

def valid(rid):
    r = refs.get(rid)
    if not r:
        return False
    has_id = bool(re.fullmatch(r"\d{7,8}", r.get("pmid", ""))) or r.get("url", "").startswith("https://")
    return has_id and bool(r.get("accessed"))

failures, per_code = [], {}
for code in sorted(used_ni | used_cp):
    srcs = set(gold_src.get(code, set()))
    srcs |= set((ni.get(code) or cp.get(code) or {}).get("source_refs", []))
    ok = [s for s in sorted(srcs) if valid(s)]
    per_code[code] = {"refs": sorted(srcs), "valid_refs": ok}
    if not ok:
        failures.append({"code": code, "problem": "no ref with PMID/https URL + accessed date", "refs": sorted(srcs)})

all_used = sorted({s for v in per_code.values() for s in v["refs"]})
lookups = []
pmids = [refs[r]["pmid"] for r in all_used if r in refs and refs[r].get("pmid")]
if pmids:
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&retmode=json&id=" + ",".join(pmids)
    try:
        res = json.loads(urllib.request.urlopen(url, timeout=30).read())["result"]
    except Exception as e:  # noqa: BLE001
        res = {"error": str(e)}
    for rid in all_used:
        r = refs.get(rid, {})
        if not r.get("pmid"):
            continue
        s = res.get(r["pmid"], {}) if isinstance(res, dict) else {}
        title = s.get("title", "")
        norm = lambda t: re.sub(r"[^a-z0-9 ]", " ", t.lower())
        # main title only (before the subtitle after ": " or ". "); citations abbreviate subtitles
        main = re.split(r":\s|\.\s", title)[0]
        tw = [w for w in norm(main).split() if len(w) > 3]
        cw = set(norm(r["citation"]).split())
        overlap = sum(w in cw for w in tw) / max(1, len(tw))
        first_author = (s.get("sortfirstauthor") or "").split(" ")[0]
        ok = bool(title) and overlap >= 0.6 and first_author.lower() in r["citation"].lower()
        lookups.append({"ref_id": rid, "pmid": r["pmid"], "pubmed_title": title, "pubmed_first_author": s.get("sortfirstauthor"),
                        "pubmed_source": s.get("source"), "pubdate": s.get("pubdate"), "title_word_overlap": round(overlap, 2), "match": ok})
        if not ok:
            failures.append({"ref_id": rid, "problem": "PubMed title/author does not match citation", "pubmed_title": title,
                             "citation": r["citation"]})
for rid in all_used:
    r = refs.get(rid, {})
    if r.get("pmid") or not r.get("url"):
        continue
    try:
        req = urllib.request.Request(r["url"], headers={"User-Agent": "Mozilla/5.0 s6-checker"})
        body = urllib.request.urlopen(req, timeout=30).read(400000).decode("utf-8", "replace")
        m = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
        st = "200"
        title = (m.group(1).strip() if m else body[:120])
    except Exception as e:  # noqa: BLE001
        st, title = f"error: {e}", ""
    lookups.append({"ref_id": rid, "url": r["url"], "fetch": st, "page_title": title[:200]})
    time.sleep(0.3)

out = {"used_ni": len(used_ni), "used_cp": len(used_cp), "refs_used": all_used, "per_code": per_code,
       "lookups": lookups, "failures": failures}
OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False))
print(json.dumps({"used_ni": len(used_ni), "used_cp": len(used_cp), "refs_used": all_used,
                  "lookups": lookups, "failures": failures}, indent=1, ensure_ascii=False))
