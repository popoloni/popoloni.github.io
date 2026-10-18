# Knowledge Atlas for AI and Software Engineering

An independent, source-traceable map of research and practitioner writing about AI-assisted software development, by **Enrico Papalini**. The graph and static catalogues connect publications, topics, engineering practices and book chapters while retaining their evidence limits.

**[Open the published atlas](https://popoloni.github.io/swe_knowledge_graph.html)** · **[Local atlas](swe_knowledge_graph.html)** · **[Catalogues](catalogues/index.html)** · **[NDSE2 · published second edition](catalogues/ndse2.html)** · **[Downloads](downloads.html)** · **[Update notes](UPDATE_20261018.html)**

## The starting collection

The foundation is **[The SE & AI Annotated Bibliography](https://www.sepolimi.com/p/se-ai-annotated-bibliography)**, curated by **Alfonso Fuggetta, Damian Andrew Tamburri and Alessandro Margara**, **Software Engineering @ PoliMi**. Its original 8 October 2026 snapshot contains 193 works. The original classification and annotations are the curators’ contribution. This independent atlas and its editorial extensions do not imply institutional endorsement.

The atlas opens with the original PoliMi collection. Additional collections, context and relationship controls are available through the interface. Source IDs and established links remain stable.

## Current catalogues

| ID | Collection | Records |
|---|---|---:|
| W | [SE@PoliMi bibliography](catalogues/polimi.html) | 193 |
| O | [Addy Osmani](catalogues/osmani.html) | 51 |
| P | [The Pragmatic Engineer](catalogues/pragmatic-engineer.html) | 124 |
| F | [Martin Fowler’s website](catalogues/fowler.html) | 35 |
| B | [Earlier Non-Deterministic books](catalogues/books.html) | 111 |
| N | [NDSE2 · Published second edition](catalogues/ndse2.html) | 13 |

Also browse **[9 streams](catalogues/streams.html)**, **[30 topics](catalogues/topics.html)**, **[6 published books](catalogues/volumes.html)**, **[13 NDSE2 chapter guides](catalogues/chapters.html)**, **[84 practice descriptors](catalogues/practices.html)** and **[87 historical occurrences](catalogues/occurrences.html)**. Static entries work without JavaScript; optional filters improve navigation.

## Published NDSE2 second edition

On **18 October 2026**, the author confirmed that the book was already published. That confirmation records availability, not an inferred first-publication date. ISBN and first-publication date are displayed only if supplied in the edition metadata.

The **13 chapter records** contain concise English summaries, Italian titles, learning goals, outlines and source links. Literal citations from the English and Italian chapter files are distinguished from bibliography membership, the identifier index and broader editorial reading mappings. The full manuscripts are not included in the website.

[Read the chapter guides](catalogues/ndse2.html) · [Edition and extraction provenance](source/ndse2_book.json) · [Source-review audit](data/updates/source_review_20261018.json)

## Authorship and evidence

The Fowler collection credits each article’s actual author and acknowledges **Birgitta Böckeler** as contributor and editor of [Exploring Generative AI](https://martinfowler.com/articles/exploring-gen-ai.html). Its adjacent website additions are labelled separately. The Pragmatic Engineer catalogue preserves guest and interview roles. Collection membership does not establish peer review, causal support or independent replication.

## About Enrico Papalini

<img src="assets/enrico-papalini.jpg" alt="Enrico Papalini — author photograph" width="140">

Enrico Papalini is a software engineering leader and author based in Milan, Italy. With more than 25 years in software engineering and 15 in people management, his work focuses on AI-assisted development, intelligent automation and dependable financial-market systems. His career includes leadership roles at Euronext Securities, London Stock Exchange Group and Borsa Italiana. He writes the Non-Deterministic series and created this independent knowledge atlas.

Photo and biography are adapted from the author’s own *Non-Deterministic Loop Engineering* author page. [Photo provenance](source/author_provenance.json) · [About the project](about.html) · [GitHub](https://github.com/popoloni). This project expresses the author’s views, not those of his employers or cited institutions.

## Publish or update the static site

Copy the package contents to the configured Pages publishing folder, preserving relative paths and `.nojekyll`. The homepage is `index.html`; the interactive atlas remains `swe_knowledge_graph.html`. A `knowledge-atlas.html` entrypoint is also supplied. A delta package contains only files to add or overwrite and is applied to the existing site using the same relative paths.

No server application, API key, framework or CDN is required. See [DEPLOYMENT.md](DEPLOYMENT.md) for local preview and rebuild instructions.

**Graph v13 · 2026-10-18**. **Website v13.0 · 2026-10-18**. The current graph contains **1,931 nodes**, **13,615 keyed relationships** and **309 relation types**. Historical v12 exports remain labelled as historical.

[Credits and boundaries](attribution.html) · [Validation report](verification/report.html)
