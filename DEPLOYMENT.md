# Publish or update this static site

## Apply the package

Copy the extracted files to the folder already configured as the GitHub Pages publishing source. Preserve all relative paths and `.nojekyll`. The extracted `index.html` must be directly inside that folder.

For a **full package**, use the complete site tree. For a **delta package**, add or overwrite only the included files at their existing relative paths. Follow the accompanying delta instructions for the baseline and file list.

The homepage is `index.html`; the interactive atlas is `swe_knowledge_graph.html`. If an unrelated homepage must be retained, use `knowledge-atlas.html` as the project entrypoint. Local links work at a user-site root or within a project subdirectory.

## Preview locally

Static catalogue contents remain readable with JavaScript disabled. To preview normal browser navigation, run from the site folder:

```sh
python -m http.server 8000
```

Open `http://localhost:8000/`. External source links still follow the publisher’s access conditions.

## Repeat an Atlas update

Start from the **exact complete ZIP currently published**. The updater freezes its ZIP hash and file inventory, then works on an isolated copy. A previous delta or a live repository snapshot is not a substitute for that confirmed baseline.

Run these commands from a complete package that contains `source/automation/`. Choose a fresh run directory outside the site and replace the path, date and release placeholders with this update’s values:

```sh
python source/automation/atlas_cli.py prepare --baseline /path/to/published-complete.zip --run /path/to/atlas-update --date YYYY-MM-DD --release NEXT_VERSION
python source/automation/atlas_cli.py discover --run /path/to/atlas-update
```

Discovery collects public publisher metadata and flags candidate additions or revisions. Review `/path/to/atlas-update/review.json`: resolve each candidate, retain actual bylines and original versus revision dates, identify access restrictions, and record source evidence before marking editorial review complete. Orosz blog and Deepdives remain in scope; The Pulse title-prefix and podcast exclusions remain in force. Canonical duplicates are revised under the existing ID; accepted additions receive new IDs. The discovery step does not create verified summaries or book citations.

After that source review is complete:

```sh
python source/automation/atlas_cli.py build --run /path/to/atlas-update
python source/automation/atlas_cli.py check --run /path/to/atlas-update --browser /path/to/chromium --playwright /path/to/node_modules/playwright
python source/automation/atlas_cli.py package --run /path/to/atlas-update --output /path/to/packages
```

Python 3.10+ uses only its standard library for graph updates, site rendering, structural checks and packaging. Real browser verification additionally requires Node.js, the Playwright package and a Chromium-family executable. The `--browser` and `--playwright` overrides can be omitted if those dependencies are discoverable in the environment. A missing browser is reported as an incomplete check and prevents packaging; it is not a successful browser result.

The `check` command validates current pages, anchors, exact graph exports, stable IDs and historical keyed edges, literal book citations, and the preserved original starting view. It exercises every relation switch and the catalogues in a real local browser, then compares two rebuilds from the same frozen inputs. Verification records are bound to the current artifact’s file hashes. If reviewed inputs or candidate files change, build and check again before packaging.

The `package` command calculates the delta by SHA-256 comparison of actual file contents against the frozen published ZIP. The delta includes only added or changed paths. Applying that delta to a fresh extraction of the original ZIP must reconstruct the complete package exactly. No file deletion is permitted by this copy-only procedure. An update with no approved changes is recorded as such instead of manufacturing a new release.

## Update the book only when its sources change

Leave `book_policy` as `unchanged` for article-only updates. Current chapter citations and bibliography flags remain derived from the retained manuscript metadata. New article mappings are editorial reading suggestions unless the supplied book actually cites them.

For a new final bilingual manuscript, `extract-book` can prepare a metadata draft for review. Use `source/automation/atlas_cli.py extract-book --help` for its required source paths. Review the extracted titles, summaries, goals and citation evidence, set `book_policy` to `reconcile`, and pass `--book /path/to/reviewed-book.json` to `build`. Chapter or section identity changes require an explicit migration and are blocked by the routine update workflow.

## Render the frozen website without refreshing sources

```sh
python source/build_site.py
```

This command rebuilds the static catalogues from the current configured template `source/atlas_v13_current.html`, `source/site_config.json` and `source/ndse2_book.json`. It does not discover articles, alter the graph, run verification or create a new approved package. The reusable `build` command above also performs this rendering step after applying the reviewed graph update.

Current graph downloads are `data/graph/knowledge_graph_v13.json` and `data/graph/knowledge_graph_v13.graphml`. Earlier exports remain historical artifacts. Release notes are `UPDATE_v13_1_20261018.html` and the source audit is `data/updates/source_review_20261018.json`. Use the existing GitHub Pages publishing workflow after reviewing the resulting full or delta package.

