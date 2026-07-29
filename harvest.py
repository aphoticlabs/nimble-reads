#!/usr/bin/env python3
"""Build a ~1000-book candidate list by merging Open Library popularity data
with critical-canon lists scraped from Wikipedia.

Every book is keyed by its Open Library *work* id (e.g. OL66554W), which is the
deduplicated work-level identifier -- all 4000 editions of Pride and Prejudice
collapse to one. Books that never resolve to a work key fall back to a slug.

Outputs: candidates.json  (raw pool, with per-source provenance)
"""

import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
os.makedirs(CACHE, exist_ok=True)

UA = "nimble-reads/0.1 (seanmyeh@gmail.com)"
OL = "https://openlibrary.org/search.json"
WP = "https://en.wikipedia.org/w/api.php"

FIELDS = "key,title,author_name,first_publish_year,readinglog_count,ratings_count,edition_count,language"


# --------------------------------------------------------------------------
# plumbing
# --------------------------------------------------------------------------

def fetch(url, params, cache_key, retries=4):
    """GET with on-disk caching so re-runs cost nothing."""
    path = os.path.join(CACHE, cache_key + ".json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)

    full = url + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(full, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=45) as r:
                data = json.loads(r.read().decode())
            with open(path, "w") as f:
                json.dump(data, f)
            return data
        except Exception as e:
            if attempt == retries - 1:
                print(f"  ! failed {cache_key}: {e}", file=sys.stderr)
                return None
            time.sleep(2 * (attempt + 1))
    return None


def slugify(title, author):
    base = f"{title}-{author}" if author else title
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-zA-Z0-9]+", "-", base).strip("-").lower()
    return base[:80]


def norm(s):
    """Aggressive normalisation for fuzzy title matching."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    s = s.lower()
    s = re.sub(r"\(.*?\)", "", s)              # drop "(novel)" disambiguators
    s = re.sub(r"^(the|a|an)\s+", "", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def work_id(key):
    return key.rsplit("/", 1)[-1] if key else None


# --------------------------------------------------------------------------
# source A: Open Library popularity
# --------------------------------------------------------------------------

OL_SORTS = [
    ("readinglog", "*:*", 10),               # most shelved overall
    ("already_read", "*:*", 6),              # most actually finished
    ("want_to_read", "*:*", 4),              # most aspirational
    ("editions", "ebook_access:public", 6),  # canon proxy: endlessly reprinted
    ("rating", "*:*", 4),                    # highest rated
]


def harvest_openlibrary():
    pool = {}
    for sort, query, pages in OL_SORTS:
        got = 0
        for page in range(1, pages + 1):
            data = fetch(OL, {
                "q": query, "sort": sort, "limit": 100,
                "page": page, "fields": FIELDS,
            }, f"ol_{sort}_{page}")
            if not data or not data.get("docs"):
                break
            for d in data["docs"]:
                wid = work_id(d.get("key"))
                if not wid or not d.get("title"):
                    continue
                rec = pool.setdefault(wid, {
                    "id": wid,
                    "title": d["title"].strip(),
                    "author": (d.get("author_name") or [None])[0],
                    "year": d.get("first_publish_year"),
                    "readinglog": d.get("readinglog_count") or 0,
                    "ratings": d.get("ratings_count") or 0,
                    "editions": d.get("edition_count") or 0,
                    "lang": d.get("language") or [],
                    "sources": [],
                })
                if f"ol:{sort}" not in rec["sources"]:
                    rec["sources"].append(f"ol:{sort}")
                got += 1
            time.sleep(0.25)
        print(f"  ol sort={sort:<14} +{got}")
    return pool


# --------------------------------------------------------------------------
# source B: Wikipedia canon lists
# --------------------------------------------------------------------------

CANON_PAGES = [
    # critical / popular canon
    ("Bokklubben World Library", "bokklubben"),
    ("Modern Library's 100 Best Novels", "modern-library"),
    ("Modern Library 100 Best Nonfiction", "modern-library-nf"),
    ("The Guardian's 100 Best Novels Written in English", "guardian-100"),
    ("The Big Read", "bbc-big-read"),
    ("BBC's 100 Most Inspiring Novels", "bbc-inspiring"),
    ("Le Monde's 100 Books of the Century", "le-monde"),
    ("List of English-language books considered the best", "eng-best"),
    ("20th Century's Greatest Hits: 100 English-Language Books of Fiction", "greatest-hits"),
    ("List of best-selling books", "best-selling"),
    # genre canon
    ("The Top 100 Crime Novels of All Time", "crime-100"),
    ("Science Fiction: The 100 Best Novels", "scifi-100"),
    ("Modern Fantasy: The 100 Best Novels", "fantasy-100"),
    # major prizes -- strong, well-structured canon signal
    ("Pulitzer Prize for Fiction", "pulitzer"),
    ("Booker Prize", "booker"),
    ("National Book Award for Fiction", "nba-fiction"),
    ("Hugo Award for Best Novel", "hugo"),
    ("Nebula Award for Best Novel", "nebula"),
    ("Women's Prize for Fiction", "womens-prize"),
    ("Pulitzer Prize for General Nonfiction", "pulitzer-nf"),
]

# Wikilinks that are never book titles.
BAD = re.compile(
    r"^(list of|category:|file:|image:|wikipedia:|\d{3,4}s?$|"
    r"united states|united kingdom|english|french|russian|german|novel|"
    r"fiction|literature|nonfiction|non-fiction|paperback|hardcover)",
    re.I,
)


def extract_titles(wikitext):
    """Pull ''[[Title]]'' patterns -- italicised wikilinks are book titles in
    every one of these list formats, whether table row or bullet."""
    out = []
    # ''[[Target|Display]]'' or ''[[Target]]''
    for m in re.finditer(r"''\[\[([^\]|]+)(?:\|([^\]]+))?\]\]''", wikitext):
        out.append((m.group(2) or m.group(1)).strip())
    # bare ''Title'' inside a list item, for lists that don't link every entry
    for m in re.finditer(r"^[*#]\s*''([^'\[\]]{3,90})''", wikitext, re.M):
        out.append(m.group(1).strip())
    seen, keep = set(), []
    for t in out:
        t = re.sub(r"\s*\(.*?\)\s*$", "", t).strip()
        k = norm(t)
        if not k or k in seen or BAD.match(t) or len(t) < 3:
            continue
        seen.add(k)
        keep.append(t)
    return keep


def harvest_wikipedia():
    """Returns {normalised_title: [source_tags]}"""
    wanted = {}
    for page, tag in CANON_PAGES:
        data = fetch(WP, {
            "action": "parse", "page": page, "redirects": 1,
            "prop": "wikitext", "format": "json",
        }, f"wp_{tag}")
        if not data or "parse" not in data:
            print(f"  wp {tag:<22} ! unavailable")
            continue
        titles = extract_titles(data["parse"]["wikitext"]["*"])
        for t in titles:
            wanted.setdefault(t, []).append(f"list:{tag}")
        print(f"  wp {tag:<22} +{len(titles)}")
        time.sleep(0.2)
    return wanted


def resolve_title(title):
    """Look up one Wikipedia-sourced title in Open Library."""
    data = fetch(OL, {
        "q": title, "limit": 5, "fields": FIELDS,
    }, "res_" + slugify(title, "")[:60])
    if not data:
        return None
    target = norm(title)
    best = None
    for d in data.get("docs", []):
        if not d.get("title") or not work_id(d.get("key")):
            continue
        cand = norm(d["title"])
        # exact normalised match, or the OL title is a prefix of ours
        if cand == target or cand.startswith(target) or target.startswith(cand):
            score = (d.get("edition_count") or 0) + (d.get("readinglog_count") or 0)
            if best is None or score > best[0]:
                best = (score, d)
    if best is None:
        return None
    d = best[1]
    return {
        "id": work_id(d["key"]),
        "title": d["title"].strip(),
        "author": (d.get("author_name") or [None])[0],
        "year": d.get("first_publish_year"),
        "readinglog": d.get("readinglog_count") or 0,
        "ratings": d.get("ratings_count") or 0,
        "editions": d.get("edition_count") or 0,
        "lang": d.get("language") or [],
    }


# --------------------------------------------------------------------------

def main():
    print("[1/3] Open Library popularity...")
    pool = harvest_openlibrary()
    print(f"  -> {len(pool)} unique works\n")

    print("[2/3] Wikipedia canon lists...")
    wanted = harvest_wikipedia()
    print(f"  -> {len(wanted)} unique canon titles\n")

    print("[3/3] Resolving canon titles to Open Library works...")
    titles = list(wanted.keys())
    resolved = 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        for title, rec in zip(titles, ex.map(resolve_title, titles)):
            if not rec:
                continue
            resolved += 1
            existing = pool.get(rec["id"])
            if existing:
                for tag in wanted[title]:
                    if tag not in existing["sources"]:
                        existing["sources"].append(tag)
            else:
                rec["sources"] = list(wanted[title])
                pool[rec["id"]] = rec
    print(f"  -> resolved {resolved}/{len(titles)}; pool now {len(pool)}\n")

    for rec in pool.values():
        rec["slug"] = slugify(rec["title"], rec["author"] or "")

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "candidates.json")
    with open(out, "w") as f:
        json.dump(list(pool.values()), f, indent=2, ensure_ascii=False)
    print(f"wrote {out} ({len(pool)} candidates)")


if __name__ == "__main__":
    main()
