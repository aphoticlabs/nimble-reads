#!/usr/bin/env python3
"""Score, filter and dedupe candidates.json down to the top ~1000 books.

Scoring blends two independent signals so neither dominates:
  canon   -- how many curated best-of / prize lists the book appears on
  reach   -- how many people shelve it, how often it gets reprinted

Emits books.json: [{id, slug, title, author, year, summary}]
"""

import json
import math
import os
import re
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = 1000

# Catalog artifacts that leak out of Open Library's bulk records.
JUNK = re.compile(
    r"^\[|"                                  # "[Nii language publications]."
    r"^laws,|"                               # "Laws, etc" (statute compilations)
    r"\b(annual report|proceedings|hearings?|bulletin|catalog(ue)?|"
    r"census|statistics|directory|handbook of the|index to|"
    r"technical report|working paper|plan summary|study of|"
    r"study guide|summary of|workbook|teacher'?s edition)\b",
    re.I,
)

# Publishers and corporate bodies that appear in the author field on textbooks,
# reference sets, and study guides -- never a book we want to summarise.
JUNK_AUTHOR = re.compile(
    r"(company staff|publishing|publishers|supersummary|editors of|"
    r"houghton mifflin|mcgraw|pearson|scholastic inc|^great britain)",
    re.I,
)

# One-off bad records that no general rule should try to catch:
# abridgements/adaptations credited to the adapter, and a critical companion
# catalogued under the novel's own title.
BLOCKLIST = {
    "OL15844388W",  # "One hundred years of solitude" credited to Regina Janes
                    # (critic, not author); the real novel is OL274505W
    "OL17451527W",  # "The Little Prince" adaptation; original is OL10263W
    "OL16059606W",  # "J.R.R. Tolkien's The hobbit" retelling; original OL27482W
}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"^(the|a|an)\s+", "", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def surname(author):
    """Last alphabetic token -- stable across 'J.R.R. Tolkien' / 'John Tolkien'."""
    toks = re.findall(r"[A-Za-z]+", norm(author))
    return toks[-1] if toks else ""


def keep(b):
    """Hard filters. Anything failing these is not a book we can summarise."""
    if not b.get("title") or not b.get("author") or not b.get("year"):
        return False
    if b.get("id") in BLOCKLIST:
        return False
    if JUNK.search(b["title"]) or JUNK_AUTHOR.search(b["author"]):
        return False
    if not (-3000 <= b["year"] <= 2026):
        return False
    if len(b["title"]) > 120 or len(norm(b["title"])) < 2:
        return False
    # Titles that are mostly digits/punctuation are catalog noise.
    if len(re.sub(r"[^a-zA-Z]", "", b["title"])) < 3:
        return False
    return True


def canon_hits(b):
    return sum(1 for s in b["sources"] if s.startswith("list:"))


def score(b):
    canon = canon_hits(b)
    reach = (
        1.2 * math.log10(b.get("readinglog", 0) + 1)
        + 1.5 * math.log10(b.get("editions", 0) + 1)
        + 0.8 * math.log10(b.get("ratings", 0) + 1)
    )
    # Appearing on any curated list is a strong statement of standing;
    # additional lists have diminishing returns.
    return 4.0 * math.sqrt(canon) + reach


def is_english(b):
    langs = b.get("lang") or []
    return (not langs) or ("eng" in langs)


def main():
    cands = json.load(open(os.path.join(HERE, "candidates.json")))
    print(f"loaded {len(cands)}")

    pool = [b for b in cands if keep(b)]
    print(f"after hard filters: {len(pool)}")

    # A non-English work earns its place only through demonstrated literary
    # standing (a curated list, or a long reprint history) -- this keeps
    # Don Quixote and Crime and Punishment while dropping recent foreign
    # -language pop titles that happen to spike in Open Library's shelves.
    pool = [b for b in pool
            if is_english(b) or canon_hits(b) > 0 or b.get("editions", 0) >= 25]
    print(f"after language standing filter: {len(pool)}")

    for b in pool:
        b["score"] = score(b)
    pool.sort(key=lambda b: -b["score"])

    # Dedupe: Open Library work keys are good but not perfect -- the same book
    # sometimes exists as two works. Collapse on (title, author surname).
    seen, chosen = {}, []
    for b in pool:
        k = (norm(b["title"]), surname(b["author"]))
        if k in seen:
            continue
        seen[k] = True
        chosen.append(b)
    print(f"after title/author dedupe: {len(chosen)}")

    top = chosen[:TARGET]

    books = [{
        "id": b["id"],
        "slug": b["slug"],
        "title": b["title"],
        "author": b["author"],
        "year": b["year"],
        "summary": "",
    } for b in top]

    out = os.path.join(HERE, "books.json")
    with open(out, "w") as f:
        json.dump(books, f, indent=2, ensure_ascii=False)
    print(f"\nwrote {out} ({len(books)} books)")

    # provenance sidecar -- keeps books.json clean but the ranking explainable
    with open(os.path.join(HERE, "books.meta.json"), "w") as f:
        json.dump([{
            "id": b["id"], "title": b["title"], "score": round(b["score"], 3),
            "canon_lists": canon_hits(b), "sources": b["sources"],
            "readinglog": b.get("readinglog", 0), "editions": b.get("editions", 0),
        } for b in top], f, indent=2, ensure_ascii=False)

    print("\n--- top 15 ---")
    for b in top[:15]:
        print(f"  {b['score']:5.1f} {b['year']:>5} {b['title'][:46]:<48} {b['author'][:26]}")
    print("\n--- ranks 995-1000 ---")
    for b in top[-6:]:
        print(f"  {b['score']:5.1f} {b['year']:>5} {b['title'][:46]:<48} {b['author'][:26]}")


if __name__ == "__main__":
    main()
