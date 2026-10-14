# Validation method and boundaries

This release is a new website and catalogue presentation of the frozen v12 graph, not a source-research update.

- The complete embedded graph payload, record IDs, attributes, and default-state declaration are compared with the original v12 HTML. Original GraphML/JSON bytes are retained.
- Static validation resolves HTML file links, record fragments, stylesheet/script references and image paths inside the site. External URLs are inventoried, not fetched afresh.
- The 510 W/O/P/F/B source records, 84 practice descriptors and 87 historical occurrences are present in static HTML. Current JSON exports retain each complete node object.
- Browser execution uses system Chromium through Playwright. Administrator policy blocks local HTTP navigation in this environment. Therefore packaged CSS, JavaScript and images are inlined into Playwright `set_content`. The production catalogue URL handler is called with explicit query parameters. This exercises code and rendering but does not establish successful hosted navigation. Static link resolution is a separate check.
- All 297 relationship checkboxes are exercised through their actual change handlers and compared against the expected edge IDs. The reset state is checked against the exact original 193-source / 0-context / 64-edge set.
- Responsive viewports are explicitly asserted at 1440/1024/390 CSS pixels. This is not native iPad/Safari testing. Lazy-loaded author imagery is scrolled into view and checked before full-page screenshots.
- Initial test-harness assumptions about the inherited viewport and portrait width were corrected against actual runtime values (390px viewport; portrait 631 × 640 pixels); the final checks reran with those assertions. These were harness corrections, not changes to the graph or source record content.
- The standard-library site builder and catalogue ZIP are tested for byte-reproducibility. The final release ZIP is separately reopened and its payloads checked against SHA256SUMS.txt.

No source claim acquires new evidentiary status through these checks. No original research data have been independently replicated here, and no production pilot, restricted-content access or repository deployment is claimed. The source and photo provenance files record the input basis.
