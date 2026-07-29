#!/usr/bin/env python3
"""Merge hand-written summaries into books.json and apply year corrections.

Summaries live in summaries/batch*.json as {work_id: summary}. Only books whose
content is actually known got an entry; everything else keeps summary "".

YEAR_FIXES covers records where Open Library's first_publish_year was wrong and
Wikidata had no confident match (usually because the title in Open Library is a
variant or translation).
"""

import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

YEAR_FIXES = {
    "OL102749W": 1851,   # Moby Dick
    "OL15292640W": 8,    # Metamorphoses (Ovid)
    "OL7180368W": 1353,  # Decameron
    "OL731644W": 1957,   # Atlas Shrugged
    "OL267171W": 1869,   # War and Peace
    "OL531767W": 1387,   # The Canterbury Tales (composition, not Caxton printing)
    "OL93227W": 1320,    # Inferno
    "OL81655W": 1993,    # Green Mars
    "OL1955906W": 2011,  # A Dance With Dragons
    "OL15455841W": 2010, # Unbroken
    "OL104128W": 1967,   # The Naked Ape
    "OL14942956W": 1903, # The Call of the Wild
    "OL27257W": 1993,    # Virtual Light
    "OL498463W": 1925,   # Der Prozess (The Trial)
    "OL36287W": 1844,    # Le Comte de Monte-Cristo
    "OL362702W": 1599,   # Julius Caesar
    "OL17396611W": 1842, # Dead Souls
    "OL503666W": 1605,   # Don Quijote
    "OL24156W": 1886,    # Jekyll and Hyde
    "OL51117W": 1920,    # Main Street
    "OL59684W": 1984,    # Job: A Comedy of Justice
    "OL240210W": 1880,   # Ben-Hur
    "OL258902W": 1606,   # Macbeth
    "OL362427W": 1597,   # Romeo and Juliet
    "OL66501W": -431,    # Medea
    "OL62250W": 1841,    # Emerson, Essays
    "OL1317211W": 180,   # Meditations
    "OL244537W": -500,   # The Art of War
    "OL24220W": 1907,    # The Education of Henry Adams
    "OL1448853W": 1957,  # By Love Possessed
    "OL20234863W": 2016, # Girl in Pieces
    "OL8193387W": 1854,  # Hard Times
    "OL63985W": 1820,    # The Legend of Sleepy Hollow
    "OL27776452W": 1895, # The Importance of Being Earnest
    "OL8215661W": 1997,  # One Piece vol. 1
    "OL45499W": -400,    # Tao Te Ching
    "OL18993W": 1273,    # Masnavi
    "OL308980W": -400,   # Ramayana
    "OL462007W": 1911,   # Peter Pan (novel)
    "OL28353073W": 2012, # Me Before You
}


def main():
    books = json.load(open(os.path.join(HERE, "books.json")))

    summaries = {}
    for path in sorted(glob.glob(os.path.join(HERE, "summaries", "batch*.json"))):
        batch = json.load(open(path))
        overlap = set(batch) & set(summaries)
        if overlap:
            print(f"  ! {os.path.basename(path)} repeats {len(overlap)} ids")
        summaries.update(batch)
    print(f"loaded {len(summaries)} summaries")

    filled = years = 0
    for b in books:
        s = summaries.get(b["id"])
        if s:
            b["summary"] = s
            filled += 1
        if b["id"] in YEAR_FIXES:
            b["year"] = YEAR_FIXES[b["id"]]
            years += 1

    json.dump(books, open(os.path.join(HERE, "books.json"), "w"),
              indent=2, ensure_ascii=False)

    unused = set(summaries) - {b["id"] for b in books}
    if unused:
        print(f"  ! {len(unused)} summaries matched no book: {sorted(unused)[:5]}")

    print(f"filled {filled}/{len(books)} summaries; corrected {years} years")
    print(f"left empty: {len(books) - filled}")


if __name__ == "__main__":
    main()
