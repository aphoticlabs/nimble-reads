# Nimble Reads

The top 1000 books, each summarised in exactly ten words.

`books.json` is the data, as an array of:

```json
{
  "id": "OL627084W",
  "slug": "lolita-vladimir-nabokov",
  "title": "Lolita",
  "author": "Vladimir Nabokov",
  "year": 1955,
  "summary": "Obsessive professor narrates his predatory infatuation with a young girl."
}
```

`id` is the Open Library **work** key — the deduplicated work-level identifier, so
all ~4000 editions of *Pride and Prejudice* collapse to one stable id. `slug` is a
human-readable fallback derived from title + author.

## How "top 1000" is defined

There is no canonical global list, so this blends two independent signals:

- **canon** — appearances across 20 curated best-of and major-prize lists
  (Bokklubben World Library, BBC Big Read, Le Monde, Modern Library, Pulitzer,
  Booker, Hugo, Nebula, National Book Award, Women's Prize, …)
- **reach** — Open Library shelving counts, ratings, and edition counts
  (edition count is a good proxy for standing: canonical works get reprinted endlessly)

Score is `4·√(canon lists) + 1.2·log₁₀(shelvings) + 1.5·log₁₀(editions) + 0.8·log₁₀(ratings)`.
Per-book provenance is kept in `books.meta.json` so any ranking is explainable.

## Pipeline

```
python3 harvest.py    # Open Library + Wikipedia  -> candidates.json (~3.3k)
python3 select.py     # score, filter, dedupe     -> books.json (1000) + books.meta.json
python3 fixyears.py   # correct years vs Wikidata -> books.json
python3 merge.py      # attach summaries          -> books.json
```

`harvest.py` and `fixyears.py` cache every HTTP response under `.cache/`, so
re-runs are free. Delete the relevant cache files to force a refresh.

## Publication years

Open Library's `first_publish_year` comes from the earliest *edition record* and is
often wrong (it had *Lolita* at 1777, *Ulysses* at 1914). `fixyears.py` checks each
title against Wikidata's P577, matching on author surname and taking the earliest
date: 192 corrected, 555 independently confirmed, 253 with no confident match.
A further 40 are pinned by hand in `merge.py`'s `YEAR_FIXES` — mostly translated
titles and pre-modern works where Wikidata matching by English label fails.

## Site

An Astro static site renders `books.json`: a searchable list plus one page per book.

```
npm install
npm run dev      # http://localhost:4321/nimble-reads
npm run build    # -> dist/  (1001 pages, ~1.4s)
```

Search matches title and author, with diacritics folded — `bronte` finds Brontë,
`safak` finds Şafak. Read state lives in `localStorage` under
`nimble-reads:read` and is per-browser; there is no account or sync.

Pushing to `main` triggers `.github/workflows/pages.yml`, which builds and
deploys to Pages. The workflow sets `BASE_PATH` from the repository name so URLs
resolve under `/<repo>/`; override it to `/` for a user site or custom domain.

Regenerating the data is enough to update the site — the pages are built from
`books.json` at deploy time, so no site files need editing.

## Summaries

986 of 1000 have a 10-word summary (every one exactly 10 words). The remaining 14
are deliberately blank: category romance, later series instalments, and similar
titles whose content wasn't known well enough to summarise without guessing.
Summaries are stored per-batch in `summaries/` keyed by work id, so re-running
`select.py` and `merge.py` reattaches them to whichever books survive.
