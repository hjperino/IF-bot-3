"""Erzeugt ausgefüllte Test-Anträge aus den leeren Formularen (erfundene Inhalte und Personen).

Aufruf:  python tests/make_samples.py     (braucht python-docx)
Ausgabe: tests/out/*.docx
"""
import copy
import sys
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "referenz"
OUT = ROOT / "tests" / "out"

TEXT = ("Im Französischunterricht der Berufsmaturität fehlt den Lernenden oft die Gelegenheit, frei zu sprechen. "
        "Wir erproben einen KI-gestützten Gesprächspartner, mit dem die Lernenden zu zweit Alltagssituationen üben. "
        "Die Lehrperson Petra Muster begleitet die Übungsphasen, gibt Feedback und leitet die Reflexion an. "
        "Bei Fragen: petra.muster@kzo.ch oder 044 123 45 67.")

PERSONEN = [
    {"Vorname, Name": "Petra Muster", "Fach/Beruf": "Französisch", "Schule": "Kantonsschule Zürcher Oberland",
     "E-Mail": "petra.muster@kzo.ch", "Telefon": "044 123 45 67", "Fürs Projekt relevante Kompetenzen": "Didaktik, Moodle",
     "Ort, Datum, Unterschrift Lehrperson": "Wetzikon, 1.11.2026",
     "Zuständiger Schulleitungskontakt (E-Mail)": "rektor.beispiel@kzo.ch",
     "Ort, Datum, Unterschrift SL-Kontakt": "Wetzikon, 2.11.2026", "Schuladresse": "Bühlstrasse 36, 8620 Wetzikon"},
    {"Vorname, Name": "Lukas Lang", "Fach/Beruf": "Informatik", "Schule": "BBW",
     "E-Mail": "lukas.lang@gmail.com", "Fürs Projekt relevante Kompetenzen": "Programmierung, KI-Tools",
     "Ort, Datum, Unterschrift Lehrperson": "Winterthur, 1.11.2026",
     "Zuständiger Schulleitungskontakt (E-Mail)": "leitung@bbw.ch",
     "Ort, Datum, Unterschrift SL-Kontakt": "", "Schuladresse": "Wülflingerstrasse 17, 8400 Winterthur"},
]


def setze(zelle, text):
    zelle.text = text


def fuelle(datei: str, ziel: str, titel="Sprechen mit KI", total="240", personen=PERSONEN, kreuz=True,
           betrag="1'200", kapitel_loeschen=None):
    d = Document(REF / datei)
    for p in d.paragraphs:
        if "Schreiben Sie hier" in p.text:
            p.text = TEXT
        elif "Geben Sie hier Ihren Projekttitel ein" in p.text:
            p.text = f"«{titel}»"
        if kapitel_loeschen and p.text.strip() == kapitel_loeschen:
            p._element.getparent().remove(p._element)
    # Der Projekttitel steht in einem Inhaltssteuerelement, das python-docx nicht als Absatztext zeigt
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    for sdt in d.element.iter(W + "sdt"):
        alias = sdt.find(W + "sdtPr/" + W + "alias")
        if alias is not None and "Projekttitel" in (alias.get(W + "val") or ""):
            ts = list(sdt.iter(W + "t"))
            for k, t_el in enumerate(ts):
                t_el.text = titel if k == 0 else ""
    idx = 0
    for t in d.tables:
        zeilen = t.rows
        erste = zeilen[0].cells[0].text.strip() if zeilen else ""
        if erste.startswith("Vorname, Name"):
            if idx < len(personen):
                pers = personen[idx]
                for r in zeilen:
                    label = r.cells[0].text.strip()
                    if label in pers and len(r.cells) > 1:
                        setze(r.cells[-1], pers[label])
                    if label == "Anstellung" and kreuz:
                        setze(r.cells[-1], "☐ unbefristete Anstellung obA; ☒ unbefristete Anstellung mbA")
            idx += 1
        for r in zeilen:
            txt = " ".join(c.text for c in r.cells)
            if "Total Arbeitsstunden (offen)" in txt and total is not None:
                setze(r.cells[-1], total)
            if r.cells[0].text.strip() == "" and len(r.cells) >= 3 and r.cells[1].text.strip() == "Total:" and betrag:
                setze(r.cells[-1], betrag)
    OUT.mkdir(parents=True, exist_ok=True)
    d.save(OUT / ziel)
    return OUT / ziel


def alle():
    fuelle("Projekteingabefomular Digital Explorer.docx", "D_ok.docx")
    fuelle("Projekteingabefomular Learning Incubator.docx", "L_ok.docx")
    fuelle("Projekteingabefomular Hub Scaler.docx", "H_ok.docx", total="380")
    fuelle("Projekteingabefomular Learning Incubator.docx", "L_stunden_zu_hoch.docx", total="950", betrag="6'500")
    fuelle("Projekteingabefomular Hub Scaler.docx", "H_stunden_zu_hoch.docx", total="450")
    fuelle("Projekteingabefomular Digital Explorer.docx", "D_eine_person.docx", personen=PERSONEN[:1], kreuz=False)
    fuelle("Projekteingabefomular Learning Incubator.docx", "L_titel_geloescht.docx", kapitel_loeschen="Didaktik")


if __name__ == "__main__":
    alle()
    print("Testdateien in", OUT)
