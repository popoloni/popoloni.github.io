# Book covers and Amazon links

Atlas 13.2 adds the author-supplied ND series artwork and NDSE2 cover, a separate Amazon.com series destination, and individual Amazon.com destinations for the six existing volume records.

## Source of truth

Edit `source/book_publications.json` for a reviewed publication update. It records the release, baseline package and canonical graph-payload hashes, the series artwork, and the existing node/volume identifiers. Product links must use a canonical `https://www.amazon.com/dp/ASIN` URL. The registry records whether each destination was supplied by the author or confirmed through Amazon product pages. Prices, retailer format ISBNs and a current Amazon series count are not inferred.

The supplied originals are `assets/books/NDseries.png` and `assets/books/NDSE2_cover.jpg`. Their bytes, dimensions and SHA-256 fingerprints are recorded in the registry. The renderer displays the whole image. Earlier-volume pages identify the composite image as series artwork; the current NDSE2 edition uses its own cover.

## Build a reviewed publication update

Start with the complete package confirmed as published, then work on a separate copy. Set the new release, baseline release and exact baseline hashes in the reviewed publication registry. Keep the existing node and volume IDs. Install the updated builder and publication-adapter scripts and the reviewed local artwork in that copy, then run:

```sh
python -B source/update_publications.py
```

The adapter validates all destinations and local assets before updating navigation metadata. It preserves graph node order, all edges, source records, practices and literal chapter citations. It writes a deterministic audit under `data/updates/`, exports matching JSON and GraphML files, updates release labels and runs the static renderer. Repeating the exact reviewed update is idempotent; a different input or unexpected baseline requires a new reviewed update.

For an ordinary render of the already updated site:

```sh
python -B source/build_site.py
```

The publication registry is also used as a presentation overlay by the static builder. This preserves the cover and retail destinations during later article updates or a separately reviewed manuscript extraction. It does not rewrite bibliographic titles, ISBNs or citation evidence. Keep the corresponding builder copies under `source/automation/` synchronized: the article updater installs those copies.

## Verify and package

Run these commands from the candidate website root. Python 3.10 or later is required. The browser check also requires Node.js, the `playwright` package and an installed Chromium executable. Extract the published full ZIP into a separate baseline directory before the first check.

1. Validate the candidate against the published graph and current NDSE2 metadata:

```sh
python -B source/automation/atlas_validate.py --site . --baseline /path/to/extracted-baseline/swe_knowledge_graph.html --book source/ndse2_book.json --output verification/publications_structure.json
```

2. Check publication pages, covers, destinations, mobile layout, catalogue search and navigation through a local HTTP server:

```sh
node source/test_publications_browser.js --site . --browser /path/to/chromium --output verification/publications_browser.json
```

The browser check does not open a shopping session.
3. Run the two independent publication rebuilds:

```sh
python -B source/reproduce_publications.py --baseline /path/to/published-complete.zip --output verification/publications_reproducibility.json
```

4. Generate the current verification page and create the packages:

```sh
python -B source/package_publications.py --baseline /path/to/published-complete.zip --output /path/to/packages
```

The package command binds the three reports to the candidate's artifact digest. It compares actual file bytes with the exact published ZIP, creates a full archive and a delta containing only added or changed files, and extracts the actual archives to prove that baseline plus delta equals full. It refuses missing baseline files or failed/stale verification. Installation notes and a path-by-path SHA-256 manifest accompany the archives. Packaging does not deploy the site.

For this release the baseline is `Knowledge_Atlas_v13_1_Complete_20261018.zip`, SHA-256 `d7d9b7629ed3daf2897ca9a9e498a2912a6126bd2ee0b61d2ddf9b57fc58b251`. After 13.2 is published, use its full package as the baseline for the next update.
