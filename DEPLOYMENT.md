# Publish this static site

## Existing GitHub Pages site

Back up your current publishing folder first. Copy the extracted package contents into that folder, preserving all subfolders and the empty `.nojekyll` file. Do not upload only `index.html` or rename HTML files to `.txt`. No build command is required on GitHub.

The new `index.html` is a project landing page, not the atlas itself. `swe_knowledge_graph.html` remains the interactive atlas. If your current homepage is unrelated, keep it: publish this package in a subdirectory, or link to the supplied `knowledge-atlas.html` and do not replace your existing `index.html`. The latter file uses the same relative resource paths as the new landing page.

For the user-site root, `swe_knowledge_graph.html` serves at `https://popoloni.github.io/swe_knowledge_graph.html`. For a project site such as `articles`, the same file normally serves at `https://popoloni.github.io/articles/swe_knowledge_graph.html`. Local catalogue and image paths are relative, so no repository-name edit is required.

## Branch publishing

In repository **Settings → Pages → Build and deployment**, keep or select **Deploy from a branch**, choose the publishing branch, and select its **/(root)** or **/docs** folder. Save and wait for the Pages deployment to succeed. The package’s `index.html` must be directly inside that selected folder, not hidden one level deeper under the ZIP’s name.

GitHub documentation: https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site

Static sites and `.nojekyll`: https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site

## Local check

Open `index.html` locally. The static catalogues work without JavaScript; optional filters and atlas interactions use only bundled JavaScript. For a web-like preview, from this folder run:

```sh
python -m http.server 8000
```

Then visit `http://localhost:8000/`. An external article still requires internet access and may require a subscription. This package does not bypass that access.

## Updating the site

Edit `source/site_config.json` for the brief introduction/bio and replace `assets/enrico-papalini.jpg` only with an approved portrait. Run `python source/build_site.py`, then `python source/check_site.py`. The builder reads the frozen v12 atlas snapshot, not a live source feed. Do not substitute the old v6 attachment. Research refreshes require a separate, explicitly audited graph update.

Deployments are not executed by this deliverable. Browser tests in the verification report are local tests, not evidence of a successful deployment to your account.
