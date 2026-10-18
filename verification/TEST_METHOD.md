# Validation method and boundaries — v13.0

This is the 18 October 2026 source and published-book update to the Knowledge Atlas. It adds four practitioner-article records and a published NDSE2 chapter layer to the supplied v12.1 website. The current graph changes are intentional and audited; the frozen v12 graph remains available as historical data.

## Baseline and inputs

The comparison baseline is **Knowledge_Atlas_v12_1_Complete_GitHub_Pages_20261014.zip**, SHA-256 **128abde74f4b092372e1f6aa0de6e5b71f1cdcb6d0f84a935fe5bd527d99e2cd**. Its complete file inventory is in [update_baseline_20261018.json](../source/update_baseline_20261018.json). The author's supplied package is the stated current-site baseline; no production repository deployment is claimed.

The graph builder reads the preserved v12 HTML, audited article records, the final bilingual chapter metadata and the supplied v13 template. The static builder consumes the resulting current graph. Normal regeneration uses these frozen inputs and does not require a network connection or the complete book manuscripts.

The original source graph's node IDs and keyed edges are preserved. Current source metadata, bibliography membership and chapter citation displays can change; historical values and original edge identities remain available for comparison. The current graph contains 1,931 nodes, 13,615 keyed edges and 309 relation types.

## Article review

[Source review](../data/updates/source_review_20261018.json) records the official publication/archive coverage, deduplication decisions, accessible passages and limits of the October review. The added records are O051, F034, F035 and P124. The two Fowler-site additions explicitly expand the original series-only scope to adjacent articles.

Publication and revision dates are separate. F034 was published on 19 August and significantly revised on 13 October; it is not described as a newly published October article. Fowler-site contributors retain their actual bylines. P124 distinguishes Gergely Orosz's introduction from Sam Newman's credited excerpts. F033 was already present and is not duplicated; F026 retains its historical memo identity and records the later expanded source version.

The new online companion articles have no literal citation in the supplied published NDSE2 manuscript. Editorial chapter/topic links do not imply manuscript citations, causal support, peer review or independent replication.

## Published-book reconciliation

The author confirmed on 18 October 2026 that the second edition had already been published. That date is a confirmation of availability, not an inferred first-publication date. An unavailable ISBN is left unset.

The final EN/ITA source edition 13.7.1 yields 13 chapter records and 149 section headings per language: 147 numbered and two unnumbered. Worked examples and exercises are included according to their actual headings. The stable C:C01–C:C13 chapter hubs are retained, while NDSE2:C01–NDSE2:C13 are the new N catalogue records.

The extraction follows active source includes and literal citation macros. It preserves source-file SHA-256, line, language, chapter, section and citation-container provenance. Each language has 302 literal chapter citation occurrences and 158 distinct cited chapter sources. The distinct-source count includes the resolved auxiliary record BIB:W162Corrigendum2026. There are 223 distinct chapter–source pairs.

Introduction and appendix body citations are a separate scope: 139 occurrences per language. The combined occurrence export therefore contains 882 entries: 302 chapter plus 139 nonchapter occurrences in each language. Identifier-index links, plain identifier mentions and blanket bibliography inclusion are excluded from chapter citation counts. General bibliography membership is distinguished from literal chapter use.

[ndse2_book.json](../source/ndse2_book.json) contains the frozen extraction, bilingual alignment audit and source manifests. [The occurrence export](../data/updates/ndse2_citation_occurrences.json) supplies the graph's literal citation trace. Regenerating the website from this metadata is distinct from rerunning extraction against the original author-supplied manuscript archives.

## Structural and graph checks

[structure_checks.json](structure_checks.json) identifies the release date, site version and current interactive-HTML hash. The checker resolves local HTML links, asset references and decoded fragments; confirms permanent catalogue IDs and complete exported node data; and checks the current embedded payload and graph exports. Source collections are W193, O51, P124, F35, B111 and N13. Practice descriptors and historical occurrences remain separately represented.

The current GraphML and JSON exports preserve semantic keyed-edge identity and normalized display metadata. Graph integrity checks compare the current graph with the frozen baseline and reconcile the published-book metadata, citations and bibliography flags.

The structural pass does not fetch every external URL. Live primary-source inspection is documented separately in the article review.

## Current browser execution

The v13 browser harness is [test_update_browser.js](../source/test_update_browser.js). It uses Playwright with a Chromium-family browser and a real local HTTP server. It exercises real DOM controls and local navigation rather than replacing navigation with inlined HTML.

Checks include the exact W193 / 0 context / 64-edge initial view; collection and NDSE2 presets; source-control totals; all source catalogue counts, search, clear and empty states; deep links; static-to-graph and graph-to-static navigation; chapter actual-citation views; saved-view/export behavior; and catalogue completeness with JavaScript disabled.

All **309 relation switches** are exercised through their actual change handlers. The visible keyed-edge IDs are compared to expected IDs when a relation is enabled, and the disabled state is checked. The reset state is verified again afterward. Details are in [relationship_switch_checks.json](relationship_switch_checks.json), attested by the matching current [browser_checks.json](browser_checks.json).

Current responsive checks use **1440px and 390px CSS viewports** and include horizontal overflow and mobile control access. These are desktop and mobile-sized Chromium checks, not native Safari or iPad tests. Browser errors, failed local resource loads and unexpected external runtime requests are recorded. Local HTTP success is distinct from deployment to GitHub Pages.

Browser records are accepted by the release report only when they identify the real local-HTTP method and match the current graph counts and interactive-HTML SHA-256.

## Historical visual records

The packaged PNG screenshots and [visual_checks.json](visual_checks.json) are retained from **v12.1, 14 October 2026**. That earlier harness used inlined packaged assets and Chromium set_content after local navigation was blocked in that earlier run.

Those original screenshots and seven visual pass results are historical provenance. They are not new v13 screenshots, and their pass counts are not added to the current browser results. Current browser screenshots are produced in the separate QA output directory by the current harness.

## Byte reproducibility

[check_reproducibility.py](../source/check_reproducibility.py) creates an isolated temporary copy of the site. It runs the graph builder followed by the static builder twice and compares both resulting SHA-256 sets with the delivered generated files. It also confirms that frozen inputs remain unchanged in the live tree and temporary copy. The live website is not rebuilt by this check; only its reproducibility result is written there.

Python socket operations are prohibited by an audit hook in the rebuild processes. The test performs no source refresh. It covers current graph JSON/GraphML, the current embedded payload, generated chapter/citation exports, graph reconciliation output, static HTML, catalogue JSON/CSV, the deterministic catalogue ZIP and generated documentation.

The comparison excludes runtime browser/structural reports, release reports, the reproducibility report itself and final package checksum manifests. Those outputs depend on verification or packaging and could otherwise form circular hashes. The graph builder's deterministic graph-update audit is included.

See [reproducibility.json](reproducibility.json) for each delivered, first-rebuild and second-rebuild hash. A pass establishes faithful regeneration from the frozen inputs; it does not independently validate an article's empirical claims.

## Reports and final packages

[write_release_report.py](../source/write_release_report.py) reads the current build, graph, structural, browser and reproducibility records. Missing, historical or mismatched records are shown as pending, and failed/incomplete records are not reported as passed. The generator writes the update page, current report and release summary; it does not execute tests.

The full release package and delta are produced after current verification. The delta contains only added or changed files relative to the exact baseline, with their original relative paths. The final packaging step verifies archive contents and the reconstructed baseline-plus-delta tree separately from graph/site reproducibility. Its manifests accompany the package rather than becoming links to files outside the website.
