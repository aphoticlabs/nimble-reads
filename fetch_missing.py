#!/usr/bin/env python3
"""Pull source descriptions for books whose summary is still empty.

Tries, per book:
  1. Open Library work record  -> `description` field
  2. Wikipedia                 -> intro extract of the best-matching article
  3. Wikipedia                 -> the article's Plot / Synopsis section

Writes missing_sources.json for manual condensing. Nothing here writes summaries;
the point is to ground them in a real source rather than recall.
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".cache")
os.makedirs(CACHE, exist_ok=True)
UA = "nimble-reads/0.1 (seanmyeh@gmail.com)"
WP = "https://en.wikipedia.org/w/api.php"


def get(url, cache_key, retries=3):
    path = os.path.join(CACHE, cache_key + ".json")
    if os.path.exists(path):
        return json.load(open(path))
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=45) as r:
                d = json.loads(r.read().decode())
            json.dump(d, open(path, "w"))
            return d
        except Exception as e:
            if attempt == retries - 1:
                print(f"  ! {cache_key}: {e}", file=sys.stderr)
                return None
            time.sleep(2 * (attempt + 1))
    return None


def openlibrary_description(work_id):
    d = get(f"https://openlibrary.org/works/{work_id}.json", f"work_{work_id}")
    if not d:
        return None
    desc = d.get("description")
    if isinstance(desc, dict):
        desc = desc.get("value")
    if not desc:
        return None
    # Strip the "----- source" footers Open Library editors often append.
    desc = re.split(r"\n-{3,}|\(\[source\]", desc)[0]
    return " ".join(desc.split())[:1200]


def wikipedia_article(title, author):
    """Find the best article for this book, return (page_title, intro extract)."""
    surname = re.findall(r"[A-Za-z]+", author)[-1] if author else ""
    for query in (f"{title} {author} novel", f"{title} {surname}", title):
        d = get(WP + "?" + urllib.parse.urlencode({
            "action": "query", "list": "search", "srsearch": query,
            "srlimit": 5, "format": "json",
        }), "s_" + re.sub(r"\W+", "_", query)[:60])
        if not d:
            continue
        for hit in d.get("query", {}).get("search", []):
            page = hit["title"]
            ex = get(WP + "?" + urllib.parse.urlencode({
                "action": "query", "prop": "extracts", "titles": page,
                "exintro": 1, "explaintext": 1, "redirects": 1, "format": "json",
            }), "e_" + re.sub(r"\W+", "_", page)[:60])
            if not ex:
                continue
            for p in ex.get("query", {}).get("pages", {}).values():
                text = " ".join((p.get("extract") or "").split())
                # Confirm the article is about this book, not a namesake.
                if len(text) > 120 and (not surname or surname.lower() in text.lower()):
                    return page, text[:1500]
        time.sleep(0.3)
    return None, None


def wikipedia_plot(page):
    """Return the Plot/Synopsis section text, if the article has one."""
    d = get(WP + "?" + urllib.parse.urlencode({
        "action": "parse", "page": page, "prop": "wikitext",
        "redirects": 1, "format": "json",
    }), "p_" + re.sub(r"\W+", "_", page)[:60])
    if not d or "parse" not in d:
        return None
    w = d["parse"]["wikitext"]["*"]
    m = re.search(r"==\s*(Plot|Synopsis|Plot summary|Story|Premise)[^=]*==(.+?)(?=\n==[^=])",
                  w, re.S | re.I)
    if not m:
        return None
    text = m.group(2)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)              # templates
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)  # piped links
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)          # plain links
    text = re.sub(r"<ref.*?(/>|</ref>)", "", text, flags=re.S)
    text = re.sub(r"'{2,}", "", text)
    return " ".join(text.split())[:2000]


def main():
    books = json.load(open(os.path.join(HERE, "books.json")))
    missing = [b for b in books if not b["summary"].strip()]
    print(f"{len(missing)} books need sources\n")

    out = []
    for b in missing:
        print(f"== {b['title']} — {b['author']}")
        rec = {"id": b["id"], "title": b["title"], "author": b["author"],
               "year": b["year"]}

        rec["openlibrary"] = openlibrary_description(b["id"])
        print(f"   openlibrary: {'yes' if rec['openlibrary'] else 'none'}")

        page, intro = wikipedia_article(b["title"], b["author"])
        rec["wikipedia_page"] = page
        rec["wikipedia_intro"] = intro
        rec["wikipedia_plot"] = wikipedia_plot(page) if page else None
        print(f"   wikipedia:   {page or 'none'}"
              f"{' (+plot)' if rec['wikipedia_plot'] else ''}")

        out.append(rec)
        time.sleep(0.4)

    path = os.path.join(HERE, "missing_sources.json")
    json.dump(out, open(path, "w"), indent=2, ensure_ascii=False)
    got = sum(1 for r in out if r["openlibrary"] or r["wikipedia_intro"])
    print(f"\nwrote {path} — {got}/{len(out)} have at least one source")


if __name__ == "__main__":
    main()
