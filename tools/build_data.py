"""Erzeugt app/data/schulen.json und app/data/vorlagen.json aus den Referenzdateien.

Aufruf (im Repo-Hauptordner):
    python tools/build_data.py

Erwartet in referenz/:
    Schulen der Sek II 1.xlsx
    Projekteingabefomular Digital Explorer.docx / Learning Incubator.docx / Hub Scaler.docx
    Projekteingabefomular (Version 6.1, Original).pdf
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.extract import lies_datei  # noqa: E402
from app.local_checks import zeilen_norm  # noqa: E402

REF = ROOT / "referenz"
OUT = ROOT / "app" / "data"


def schulen():
    import openpyxl

    wb = openpyxl.load_workbook(REF / "Schulen der Sek II 1.xlsx")
    ws = wb.active
    stand, liste = "", []
    for row in ws.iter_rows(values_only=True):
        _, name, kuerzel, typ, gymi, traeger, berechtigt = (list(row) + [None] * 7)[:7]
        if isinstance(name, str) and name.startswith("Letzte Änderung"):
            stand = name.replace("Letzte Änderung:", "").strip()
            continue
        if not name or not berechtigt or name == "Schule":
            continue
        b = str(berechtigt).strip().lower()
        if not (b.startswith("ja") or b.startswith("nein")):
            continue
        liste.append({
            "name": " ".join(str(name).split()),
            "kuerzel": (str(kuerzel).strip() if kuerzel else ""),
            "typ": (str(typ).strip() if typ else ("BB" if traeger and "Leist" in str(traeger) else "")),
            "traeger": (str(traeger).strip() if traeger else ""),
            "berechtigt": b.startswith("ja"),
            "berechtigt_text": str(berechtigt).strip(),
        })
    (OUT / "schulen.json").write_text(
        json.dumps({"stand": stand, "schulen": liste}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("schulen.json:", len(liste), "Schulen, Stand", stand)


def vorlagen():
    quellen = {
        "D": "Projekteingabefomular Digital Explorer.docx",
        "L": "Projekteingabefomular Learning Incubator.docx",
        "H": "Projekteingabefomular Hub Scaler.docx",
        "61": "Projekteingabefomular (Version 6.1, Original).pdf",
    }
    out = {}
    for fid, datei in quellen.items():
        d = lies_datei(datei, (REF / datei).read_bytes())
        out[fid] = sorted({zeilen_norm(z["text"]) for z in d.zeilen if z["text"].strip()})
        print("vorlagen", fid, len(out[fid]), "Zeilen")
    (OUT / "vorlagen.json").write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    schulen()
    vorlagen()
