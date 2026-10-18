#!/usr/bin/env python3
"""Package a checked publication-assets release against its exact published ZIP."""
from __future__ import annotations
import argparse
import hashlib
import html
import json
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "source/automation"))
from atlas_cli import archive_site, files, safe_extract
from atlas_validate import artifact_sha256, validate_site

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def report_page(meta, reports):
    rows = "".join(
        "<tr><th scope=\"row\">" + html.escape(name.title()) + "</th><td>"
        + str(r["passed"]) + " passed / " + str(r["failed"]) + " failed</td></tr>"
        for name, r in reports.items()
    )
    links = "".join('<li><a href="publications_' + key + '.json">' + html.escape(key.title()) + " report</a></li>" for key in reports)
    text = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Atlas ' + html.escape(meta["release"]) + ' verification</title><link rel="stylesheet" href="../assets/site.css"></head><body><main class="wrap" id="main">'
    text += "<h1>Release verification</h1><p>Atlas v" + html.escape(meta["release"]) + " · " + html.escape(meta["date"]) + "</p><table>" + rows + "</table>"
    text += "<p>This publication update adds the supplied cover images and Amazon.com destinations. Checks cover graph/export consistency, preservation of source and citation data, publication pages and catalogue navigation at desktop and mobile widths, and two independent rebuilds from the published " + html.escape(meta["baseline_release"]) + " archive.</p>"
    text += "<p>Local browser checks use Chromium and a real local HTTP server. They inspect link destinations without starting an Amazon shopping session. They do not assert native Safari coverage or deployment.</p>"
    text += "<p>Older reports and verification images retained elsewhere belong to their original releases.</p><ul>" + links + "</ul>"
    text += '<p><a href="../source/book_publications.json">Publication registry and source verification</a> · <a href="../source/PUBLICATION_UPDATES.md">Rebuild procedure</a> · <a href="../index.html">Atlas home</a></p></main></body></html>'
    (ROOT / "verification/report.html").write_text(text, encoding="utf-8")

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    meta = load(ROOT / "source/book_publications.json")
    output = args.output.resolve()
    if output.is_relative_to(ROOT):
        p.error("Package output must be outside the website tree.")
    if sha(args.baseline) != meta["baseline_package_sha256"]:
        p.error("Published baseline ZIP does not match the reviewed SHA-256.")
    config = load(ROOT / "source/site_config.json")
    if config["site_version"] != meta["release"]:
        p.error("Candidate release does not match the reviewed input.")
    payload = load(ROOT / config["payload_json"])
    cover_files = meta["cover_provenance"]["files"]
    for item in cover_files:
        if sha(ROOT / item["site_path"]) != item["sha256"]:
            p.error("Supplied cover bytes differ from the reviewed fingerprint: " + item["site_path"])
    reports = {key: load(ROOT / "verification" / ("publications_" + key + ".json")) for key in ("structure", "browser", "reproducibility")}
    identity = artifact_sha256(ROOT)
    for key, result in reports.items():
        if not result.get("complete") or result.get("failed") != 0 or result.get("artifact_sha256") != identity:
            p.error("Failed, incomplete or stale " + key + " verification.")
    report_page(meta, reports)
    with tempfile.TemporaryDirectory(prefix="atlas132-package-") as temp:
        base = Path(temp) / "baseline"
        safe_extract(args.baseline, base)
        original = files(base)
        fresh = validate_site(ROOT, baseline_payload=base / "swe_knowledge_graph.html",
                              book=ROOT / "source/ndse2_book.json")
        if fresh.get("failed") or fresh.get("artifact_sha256") != identity:
            save(output / "packaging_structure_failure.json", fresh)
            p.error("Current structural verification failed or the artifact changed.")
        current = files(ROOT)
        if set(original) - set(current):
            p.error("A delta made only of additions and overwrites cannot remove baseline files.")
        lines = "".join(info["sha256"] + "  " + name + "\n" for name, info in sorted(current.items()) if name != "SHA256SUMS.txt")
        (ROOT / "SHA256SUMS.txt").write_text(lines, encoding="utf-8")
        current = files(ROOT)
        changed = sorted(name for name in original if original[name] != current[name])
        added = sorted(set(current) - set(original))
        unchanged = sorted(name for name in original if original[name] == current[name])
        stamp = meta["date"].replace("-", "")
        prefix = "Knowledge_Atlas_v" + meta["release"].replace(".", "_")
        full_name = prefix + "_Complete_" + stamp + ".zip"
        delta_name = prefix + "_Delta_from_v" + meta["baseline_release"].replace(".", "_") + "_" + stamp + ".zip"
        output.mkdir(parents=True, exist_ok=True)
        archive_site(output / full_name, ROOT, current, meta["date"])
        archive_site(output / delta_name, ROOT, changed + added, meta["date"])
        for name in (full_name, delta_name):
            with zipfile.ZipFile(output / name) as z:
                if z.testzip() is not None:
                    raise ValueError("ZIP integrity verification failed: " + name)
        patched, complete = Path(temp) / "patched", Path(temp) / "full"
        safe_extract(args.baseline, patched)
        safe_extract(output / delta_name, patched)
        safe_extract(output / full_name, complete)
        if files(patched) != current or files(complete) != current:
            raise ValueError("The actual baseline plus actual delta does not reproduce the full archive.")
        with zipfile.ZipFile(output / delta_name) as z:
            if sorted(i.filename for i in z.infolist() if not i.is_dir()) != sorted(changed + added):
                raise ValueError("Delta contains an unchanged or unexpected path.")
    manifest = {
        "schema": "knowledge-atlas-release/1", "release": meta["release"], "date": meta["date"],
        "baseline": {"name": args.baseline.name, "sha256": sha(args.baseline), "files": len(original)},
        "full": {"name": full_name, "sha256": sha(output / full_name), "size": (output / full_name).stat().st_size, "files": len(current)},
        "delta": {"name": delta_name, "sha256": sha(output / delta_name), "size": (output / delta_name).stat().st_size, "files": len(changed) + len(added)},
        "counts": {"overwrite": len(changed), "add": len(added), "unchanged": len(unchanged), "remove": 0},
        "verification": {"artifact_sha256": identity, "baseline_plus_delta_equals_full": True,
                         "delta_only_changed_or_added_files": True, "original_covers_preserved": True,
                         "deployed": False},
        "files": [{"path": name, "action": "overwrite" if name in original else "add",
                   "old_sha256": original.get(name, {}).get("sha256"), **current[name]} for name in sorted(changed + added)]
    }
    save(output / (prefix + "_Manifest_" + stamp + ".json"), manifest)
    checks = {key: {k: r.get(k) for k in ("complete", "passed", "failed", "artifact_sha256")} for key, r in reports.items()}
    save(output / (prefix + "_Verification_" + stamp + ".json"), {
        "release": meta["release"], "date": meta["date"], "checks": checks,
        "baseline_sha256_verified": True, "baseline_plus_delta_equals_full": True,
        "delta_only_changed_or_added_files": True, "node_count": len(payload["nodes"]), "edge_count": len(payload["edges"]),
        "publication_input": "source/book_publications.json", "deployed": False
    })
    notes = (
        "KNOWLEDGE ATLAS v" + meta["release"] + " — " + meta["date"] + "\n\n"
        + "FULL: " + full_name + "\nDELTA: " + delta_name + "\n\n"
        + "BASE PUBBLICATA: " + args.baseline.name + "\nSHA-256: " + sha(args.baseline) + "\n\n"
        + str(len(changed)) + " file da sovrascrivere; " + str(len(added)) + " file da aggiungere; nessuna eliminazione.\n"
        + "Il delta contiene esclusivamente file nuovi o modificati rispetto al pacchetto completo v" + meta["baseline_release"] + ".\n\n"
        + "INSTALLAZIONE DEL DELTA\n"
        + "1. Estrai lo ZIP in una cartella temporanea.\n"
        + "2. Copia il suo contenuto nella cartella del sito che contiene index.html, mantenendo tutti i percorsi.\n"
        + "3. Accetta la sovrascrittura dei file esistenti. Non aggiungere un ulteriore livello di cartelle.\n"
        + "4. Usa il consueto flusso di pubblicazione GitHub Pages.\n"
        + "5. Controlla catalogues/books.html, catalogues/volumes.html e catalogues/ndse2.html dopo la pubblicazione.\n\n"
        + "Il pacchetto completo contiene l'intero sito e può essere estratto in una nuova cartella.\n"
        + "Non è necessario applicare sia full sia delta. Nessun file deve essere eliminato.\n"
        + "Verifica effettuata sui file reali: baseline " + meta["baseline_release"] + " + delta " + meta["release"] + " = full " + meta["release"] + ", con identici percorsi e SHA-256.\n\n"
        + "NOVITÀ\n"
        + "- Copertina NDSE2 e immagine della serie fornite dall'autore, conservate integralmente.\n"
        + "- Collegamenti Amazon.com separati per la serie e per tutti i sei volumi del catalogo.\n"
        + "- Pagine ND/Books, indice volumi, sei schede dei volumi e pagina NDSE2 aggiornate.\n"
        + "- Metadati riutilizzabili e procedura automatica in source/PUBLICATION_UPDATES.md.\n"
        + "- Contenuti delle practice, capitoli, citazioni, ID e relazioni conservati.\n\n"
        + "I pulsanti rimandano ai libri in inglese. I testi italiani dei capitoli restano disponibili nel companion.\n"
        + "La provenienza di ogni link è registrata in source/book_publications.json. Il nuovo link NDSE2 è quello fornito dall'autore.\n"
        + "Questa consegna crea i pacchetti; il sito online viene aggiornato tramite la tua pubblicazione GitHub Pages.\n"
        + "Dopo la pubblicazione, conserva il full " + meta["release"] + " come base per il prossimo delta.\n"
    )
    (output / (prefix + "_Istruzioni_" + stamp + ".txt")).write_text(notes, encoding="utf-8")
    print(json.dumps({"status": "packaged", "full": manifest["full"], "delta": manifest["delta"],
                      "counts": manifest["counts"], "baseline_plus_delta_equals_full": True}, indent=2))

if __name__ == "__main__":
    main()
