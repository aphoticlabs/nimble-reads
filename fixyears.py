#!/usr/bin/env python3
"""Correct publication years in books.json against Wikidata.

Open Library's first_publish_year comes from the earliest *edition record*,
which is frequently wrong (Lolita 1777, Ulysses 1914). Wikidata's P577 is
curated. We only overwrite when the author surname also matches, and we take
the earliest P577 per work so reissues don't win.
"""

import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".cache")
os.makedirs(CACHE, exist_ok=True)
UA = "nimble-reads/0.1 (seanmyeh@gmail.com)"
BATCH = 40


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"^(the|a|an)\s+", "", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def surname(a):
    t = re.findall(r"[A-Za-z]+", norm(a))
    return t[-1] if t else ""


def sparql(query, cache_key, retries=3):
    path = os.path.join(CACHE, cache_key + ".json")
    if os.path.exists(path):
        return json.load(open(path))
    url = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode(
        {"query": query, "format": "json"})
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.load(r)
            json.dump(d, open(path, "w"))
            return d
        except Exception as e:
            if attempt == retries - 1:
                print(f"  ! batch {cache_key} failed: {e}", file=sys.stderr)
                return None
            time.sleep(5 * (attempt + 1))
    return None


def main():
    books = json.load(open(os.path.join(HERE, "books.json")))

    # title -> {surname: earliest_year}
    found = {}
    batches = [books[i:i + BATCH] for i in range(0, len(books), BATCH)]
    for n, batch in enumerate(batches):
        # Escape quotes/backslashes for the SPARQL literal.
        vals = " ".join(
            '"%s"@en' % b["title"].replace("\\", "").replace('"', '\\"')
            for b in batch)
        query = """
SELECT ?title ?authorLabel (MIN(YEAR(?pub)) AS ?y) WHERE {
  VALUES ?title { %s }
  ?work rdfs:label ?title ;
        wdt:P50 ?author ;
        wdt:P577 ?pub .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} GROUP BY ?title ?authorLabel
""" % vals
        d = sparql(query, f"wd_{n:03d}")
        if d:
            for r in d["results"]["bindings"]:
                if "y" not in r or "authorLabel" not in r:
                    continue  # MIN() can come back unbound for odd date values
                t = norm(r["title"]["value"])
                s = surname(r["authorLabel"]["value"])
                try:
                    y = int(r["y"]["value"])
                except ValueError:
                    continue
                cur = found.setdefault(t, {})
                if s not in cur or y < cur[s]:
                    cur[s] = y
        print(f"  batch {n + 1}/{len(batches)}  matched titles so far: {len(found)}")
        time.sleep(1.0)

    fixed = unchanged = nomatch = 0
    for b in books:
        cands = found.get(norm(b["title"]))
        if not cands:
            nomatch += 1
            continue
        y = cands.get(surname(b["author"]))
        if y is None:
            nomatch += 1
            continue
        if not (-3000 <= y <= 2026):
            nomatch += 1
            continue
        if y != b["year"]:
            b["year"] = y
            fixed += 1
        else:
            unchanged += 1

    json.dump(books, open(os.path.join(HERE, "books.json"), "w"),
              indent=2, ensure_ascii=False)
    print(f"\ncorrected {fixed}, confirmed {unchanged}, no wikidata match {nomatch}")


if __name__ == "__main__":
    main()
