#!/usr/bin/env python3
"""Build full and pure delta archives by comparing actual website file bytes.

The original author-supplied ZIP is mandatory and its SHA-256 must match the
frozen baseline manifest. Applying the delta must reconstruct the full tree
exactly. No network, deployment, deletion or source refresh is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
STAMP = (2026, 10, 18, 0, 0, 0)
FULL = "Knowledge_Atlas_v13_0_Complete_20261018.zip"
DELTA = "Knowledge_Atlas_v13_0_Delta_from_v12_1_20261018.zip"
MANIFEST = "Knowledge_Atlas_v13_0_Delta_Manifest_20261018.json"
INSTRUCTIONS = "Knowledge_Atlas_v13_0_Istruzioni_20261018.txt"
EXCLUDED_PARTS = {"__pycache__", ".git", ".pytest_cache", "node_modules"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def tree(root):
    output = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if EXCLUDED_PARTS.intersection(relative.parts) or path.suffix in (".pyc", ".pyo") or path.name == ".DS_Store":
            continue
        if path.is_symlink():
            raise ValueError("Unexpected symbolic link: " + relative.as_posix())
        if path.is_file():
            data = path.read_bytes()
            output[relative.as_posix()] = {"sha256": digest(data), "size": len(data)}
    return output


def safe_members(archive):
    members, seen = [], set()
    for item in archive.infolist():
        if item.is_dir():
            continue
        path = PurePosixPath(item.filename)
        if path.is_absolute() or ".." in path.parts or "\\" in item.filename or item.filename in seen:
            raise ValueError("Unsafe or duplicate ZIP path: " + item.filename)
        if stat.S_ISLNK(item.external_attr >> 16):
            raise ValueError("Unexpected ZIP symbolic link: " + item.filename)
        seen.add(item.filename)
        members.append(item)
    return members


def write_zip(destination, paths):
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(paths):
            info = zipfile.ZipInfo(name, STAMP)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (ROOT / name).read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True, help="Unmodified v12.1 complete website ZIP")
    parser.add_argument("--output", type=Path, required=True, help="Destination outside the website tree")
    args = parser.parse_args()
    out = args.output.resolve()
    if out.is_relative_to(ROOT):
        parser.error("Output must be outside the website tree")
    out.mkdir(parents=True, exist_ok=True)
    baseline = json.loads((ROOT / "source/update_baseline_20261018.json").read_text(encoding="utf-8"))
    if digest(args.baseline.read_bytes()) != baseline["baseline_sha256"]:
        parser.error("Baseline ZIP SHA-256 does not match the author-supplied published package")
    with zipfile.ZipFile(args.baseline) as archive:
        members = safe_members(archive)
        original = {i.filename: {"sha256": digest(archive.read(i)), "size": i.file_size} for i in members}
    if original != baseline["files"]:
        raise AssertionError("Baseline file inventory differs from the frozen provenance manifest")

    browser = json.loads((ROOT / "verification/browser_checks.json").read_text(encoding="utf-8"))
    structure = json.loads((ROOT / "verification/structure_checks.json").read_text(encoding="utf-8"))
    reproducibility = json.loads((ROOT / "verification/reproducibility.json").read_text(encoding="utf-8"))
    release = json.loads((ROOT / "verification/release_summary.json").read_text(encoding="utf-8"))
    graph_hash = digest((ROOT / "swe_knowledge_graph.html").read_bytes())
    if not (browser.get("complete") and browser.get("failed") == 0 and
            browser.get("graphHTMLSHA256") == graph_hash and structure.get("failed") == 0 and
            structure.get("graph_html_sha256") == graph_hash and reproducibility.get("failed") == 0 and
            release.get("verification_status") == "passed"):
        raise AssertionError("The current site must have complete, matching successful verification records before packaging")

    # The manifest intentionally excludes itself; all other delivered paths are covered.
    current = tree(ROOT)
    current.pop("SHA256SUMS.txt", None)
    text = "".join(meta["sha256"] + "  " + name + "\n" for name, meta in sorted(current.items()))
    (ROOT / "SHA256SUMS.txt").write_text(text, encoding="utf-8")
    current = tree(ROOT)
    removed = sorted(set(original) - set(current))
    if removed:
        raise AssertionError("A copy-only delta cannot remove files: " + ", ".join(removed))
    changed = sorted(p for p in original if current[p]["sha256"] != original[p]["sha256"])
    added = sorted(set(current) - set(original))
    unchanged = sorted(p for p in original if current[p]["sha256"] == original[p]["sha256"])
    delta_paths = sorted(changed + added)
    write_zip(out / FULL, current)
    write_zip(out / DELTA, delta_paths)

    # Reconstruct a fresh copy using only the two actual ZIPs, not in-memory substitutions.
    with tempfile.TemporaryDirectory(prefix="atlas-delta-check-") as temp:
        restored = Path(temp) / "restored"
        complete = Path(temp) / "complete"
        restored.mkdir()
        complete.mkdir()
        with zipfile.ZipFile(args.baseline) as archive:
            archive.extractall(restored)
        with zipfile.ZipFile(out / DELTA) as archive:
            actual_delta = [i.filename for i in safe_members(archive)]
            if actual_delta != delta_paths:
                raise AssertionError("Delta includes an unchanged or unexpected file")
            archive.extractall(restored)
        with zipfile.ZipFile(out / FULL) as archive:
            safe_members(archive)
            archive.extractall(complete)
        if tree(restored) != current or tree(complete) != current:
            raise AssertionError("Original + delta does not reconstruct the full package exactly")

    manifest = {
        "release": "13.0", "as_of": "2026-10-18",
        "comparison_method": "SHA-256 of actual uncompressed file contents; no timestamp or live-repository comparison",
        "baseline": {"filename": baseline["baseline_name"], "sha256": baseline["baseline_sha256"],
                     "size": baseline["baseline_size"], "files": len(original)},
        "complete": {"filename": FULL, "sha256": digest((out / FULL).read_bytes()),
                     "size": (out / FULL).stat().st_size, "files": len(current)},
        "delta": {"filename": DELTA, "sha256": digest((out / DELTA).read_bytes()),
                  "size": (out / DELTA).stat().st_size, "files": len(delta_paths)},
        "counts": {"overwritten": len(changed), "added": len(added), "unchanged": len(unchanged), "removed": 0},
        "verification": {"baseline_sha256_verified": True, "baseline_inventory_verified": True,
                         "delta_contains_only_changed_or_added_paths": True,
                         "baseline_plus_delta_equals_complete_file_tree_and_sha256": True},
        "files": [{"path": p, "action": "overwrite" if p in original else "add",
                   "baseline_sha256": original.get(p, {}).get("sha256"), **current[p]} for p in delta_paths],
        "unchanged_files": unchanged,
    }
    (out / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    instructions = f"""KNOWLEDGE ATLAS v13.0 — AGGIORNAMENTO DEL 18 OTTOBRE 2026

PACCHETTO COMPLETO
{FULL}
Contiene l'intero sito aggiornato: {len(current)} file, con index.html alla radice.

PACCHETTO DELTA
{DELTA}
Contiene soltanto {len(changed)} file da sovrascrivere e {len(added)} file nuovi.
Nessun file da eliminare. I {len(unchanged)} file invariati sono esclusi dal delta.

BASE ESATTA DEL CONFRONTO
{baseline['baseline_name']}
SHA-256: {baseline['baseline_sha256']}
È il pacchetto originale indicato dall'autore come quello pubblicato.
Il confronto usa i contenuti effettivi dei file, non le date di modifica.

COME APPLICARE IL DELTA
1. Estrai il delta in una cartella temporanea.
2. Copia tutto il contenuto estratto nella stessa cartella del sito attuale
   che contiene index.html, mantenendo tutti i percorsi e le sottocartelle.
3. Accetta la sovrascrittura dei file esistenti. Aggiungi i file nuovi.
4. Usa il consueto aggiornamento GitHub Pages per pubblicare quei file.
Non caricare lo ZIP come unico file del sito: vanno copiati i file al suo interno.

VERIFICA ESEGUITA
Il delta è stato applicato a un'estrazione nuova dello ZIP originale.
L'albero risultante coincide esattamente con il pacchetto completo, per percorsi,
dimensioni e SHA-256. Non è necessario eliminare o rinominare alcun file.

NOVITÀ
- O051: Agentic Verification (Addy Osmani, 14 ottobre 2026).
- F034: Practitioner Voice (Jim Highsmith; revisione 13 ottobre 2026).
- F035: When Software Meets Hardware (Kuldeep Singh, 15 ottobre 2026).
- P124: Building resilient AI-powered software, and planning for when things go
  wrong (Gergely Orosz, con estratti attribuiti a Sam Newman, 13 ottobre 2026).
- NDSE2: 13 capitoli dell'edizione pubblicata, 149 intestazioni di sezione,
  titoli e metadati EN/ITA, citazioni effettive riconciliate ai sorgenti finali.
- Grafo attuale: 1.931 nodi, 13.615 relazioni, 309 tipi di relazione.

I dettagli del confronto sono in {MANIFEST}.
Le note di aggiornamento sono in UPDATE_20261018.html, il rapporto di verifica
in verification/report.html. I sorgenti e i dati sono nel pacchetto completo.
"""
    (out / INSTRUCTIONS).write_text(instructions, encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("baseline", "complete", "delta", "counts", "verification")}, indent=2))


if __name__ == "__main__":
    main()
