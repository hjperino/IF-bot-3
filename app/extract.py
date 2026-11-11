"""Liest DOCX- und PDF-Anträge in eine einheitliche Zeilenstruktur ein.

Jede Zeile ist ein dict:
  text    – sichtbarer Text (Tabellenzeilen: Zellen mit " | " verbunden)
  cells   – Liste der Zelltexte (nur Tabellenzeilen, sonst None)
  images  – Liste bool pro Zelle: enthält die Zelle ein Bild (z. B. Unterschrift)?
  level   – Überschriftenebene 1–5 (nur DOCX, sonst None)

Nichts wird auf die Festplatte geschrieben; alles läuft im Arbeitsspeicher.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from typing import List, Optional

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
NS = {"w": W, "mc": MC}


def _q(tag: str) -> str:
    return "{%s}%s" % (W, tag)


@dataclass
class Dokument:
    quelle: str  # "docx" oder "pdf"
    zeilen: List[dict] = field(default_factory=list)
    hat_kommentare: bool = False
    hat_aenderungen: bool = False
    hat_fussnoten: bool = False
    seiten: Optional[int] = None

    @property
    def volltext(self) -> str:
        return "\n".join(z["text"] for z in self.zeilen)


class ExtraktionsFehler(Exception):
    pass


# ---------------------------------------------------------------- DOCX

def _text_von(el) -> str:
    """Sichtbarer Text eines Elements, inkl. Inhaltssteuerelemente und Hyperlinks.
    Gelöschter Text (Änderungsverfolgung) und mc:Fallback-Duplikate werden ignoriert."""
    teile = []
    for node in el.iter():
        tag = node.tag
        if not isinstance(tag, str):
            continue
        if tag == _q("t"):
            # nicht innerhalb von mc:Fallback (Duplikat von Textfeldern)
            if any(a.tag == "{%s}Fallback" % MC for a in node.iterancestors()):
                continue
            teile.append(node.text or "")
        elif tag == _q("tab"):
            teile.append(" ")
        elif tag in (_q("br"), _q("cr")):
            teile.append(" ")
        elif tag == _q("noBreakHyphen"):
            teile.append("-")
    return re.sub(r"[ \t ]+", " ", "".join(teile)).strip()


def _hat_bild(el) -> bool:
    for node in el.iter():
        tag = node.tag
        if isinstance(tag, str) and (tag.endswith("}drawing") or tag.endswith("}pict") or tag.endswith("}object")):
            return True
    return False


def _stil_ebenen(z: zipfile.ZipFile) -> dict:
    """styleId -> Überschriftenebene (über outlineLvl oder Stilnamen)."""
    ebenen = {}
    try:
        root = etree.fromstring(z.read("word/styles.xml"))
    except KeyError:
        return ebenen
    for st in root.findall("w:style", NS):
        sid = st.get(_q("styleId"))
        name_el = st.find("w:name", NS)
        name = (name_el.get(_q("val")) if name_el is not None else "") or ""
        m = re.match(r"(?i)^(heading|überschrift|berschrift)\s*(\d)$", name.strip())
        if m:
            ebenen[sid] = int(m.group(2))
            continue
        lvl = st.find("w:pPr/w:outlineLvl", NS)
        if lvl is not None and name.lower().startswith(("heading", "überschrift")):
            ebenen[sid] = int(lvl.get(_q("val"))) + 1
    return ebenen


def _absatz_zeilen(p, ebenen) -> List[dict]:
    text = _text_von(p)
    stil = p.find("w:pPr/w:pStyle", NS)
    level = ebenen.get(stil.get(_q("val"))) if stil is not None else None
    if not text and not _hat_bild(p):
        return []
    return [{"text": text, "cells": None, "images": None, "level": level}]


def _tabellen_zeilen(tbl) -> List[dict]:
    out = []
    for tr in tbl.iter(_q("tr")):
        # nur direkte Zeilen dieser Tabelle (verschachtelte Tabellen werden als Zelltext gelesen)
        eltern_tbl = next((a for a in tr.iterancestors() if a.tag == _q("tbl")), None)
        if eltern_tbl is not tbl:
            continue
        cells, images = [], []
        for tc in tr.iter(_q("tc")):
            eltern_tr = next((a for a in tc.iterancestors() if a.tag == _q("tr")), None)
            if eltern_tr is not tr:
                continue
            cells.append(_text_von(tc))
            images.append(_hat_bild(tc))
        if any(cells) or any(images):
            out.append({"text": " | ".join(cells), "cells": cells, "images": images, "level": None})
    return out


def _koerper(el, ebenen, out):
    for kind in el:
        tag = kind.tag
        if not isinstance(tag, str):
            continue
        if tag == _q("p"):
            out.extend(_absatz_zeilen(kind, ebenen))
        elif tag == _q("tbl"):
            out.extend(_tabellen_zeilen(kind))
        elif tag == _q("sdt"):
            inhalt = kind.find("w:sdtContent", NS)
            if inhalt is not None:
                _koerper(inhalt, ebenen, out)
        elif tag in (_q("ins"), _q("moveTo"), _q("customXml"), _q("smartTag")):
            _koerper(kind, ebenen, out)


def lies_docx(daten: bytes) -> Dokument:
    try:
        z = zipfile.ZipFile(io.BytesIO(daten))
        doc_xml = z.read("word/document.xml")
    except Exception as e:  # noqa: BLE001
        raise ExtraktionsFehler("Die Datei ist kein lesbares Word-Dokument (.docx).") from e
    root = etree.fromstring(doc_xml)
    body = root.find("w:body", NS)
    ebenen = _stil_ebenen(z)
    d = Dokument(quelle="docx")
    _koerper(body, ebenen, d.zeilen)
    namen = set(z.namelist())
    if "word/comments.xml" in namen:
        try:
            c = etree.fromstring(z.read("word/comments.xml"))
            d.hat_kommentare = len(c.findall("w:comment", NS)) > 0
        except Exception:  # noqa: BLE001
            d.hat_kommentare = False
    d.hat_aenderungen = (
        root.find(".//w:ins", NS) is not None or root.find(".//w:del", NS) is not None
    )
    if "word/footnotes.xml" in namen:
        try:
            f = etree.fromstring(z.read("word/footnotes.xml"))
            # Word legt immer zwei technische Fussnoten (Trennlinien) an
            echte = [
                n for n in f.findall("w:footnote", NS)
                if n.get(_q("type")) not in ("separator", "continuationSeparator")
            ]
            d.hat_fussnoten = len(echte) > 0
        except Exception:  # noqa: BLE001
            pass
    return d


# ---------------------------------------------------------------- PDF

_FUSSZEILE = re.compile(r"^\s*(Projekteingabe .*vom:.*|\d+\s*[I|/]\s*\d+|Seite \d+( von \d+)?)\s*$")


def _sauber(t) -> str:
    return re.sub(r"[ \t\u00a0\n]+", " ", t or "").strip()


def _pdf_seite(seite) -> List[dict]:
    """Zeilen einer PDF-Seite in Lesereihenfolge; Tabellen werden als Zellen gelesen."""
    elemente = []  # (oben, reihenfolge, zeile)
    boxen = []
    try:
        tabellen = seite.find_tables()
    except Exception:  # noqa: BLE001
        tabellen = []
    for t in tabellen:
        try:
            daten = t.extract()
        except Exception:  # noqa: BLE001
            continue
        if not daten:
            continue
        boxen.append(t.bbox)
        for k, reihe in enumerate(daten):
            cells = [_sauber(c) for c in reihe]
            if any(cells):
                elemente.append((t.bbox[1], k, {"text": " | ".join(cells), "cells": cells,
                                                "images": [False] * len(cells), "level": None}))
    try:
        textzeilen = seite.extract_text_lines()
    except Exception:  # noqa: BLE001
        textzeilen = [{"text": x, "top": i, "bottom": i, "x0": 0, "x1": 0}
                      for i, x in enumerate((seite.extract_text() or "").split("\n"))]
        boxen = []
    for z in textzeilen:
        mitte_y = (z["top"] + z["bottom"]) / 2
        mitte_x = (z["x0"] + z["x1"]) / 2
        if any(b[0] <= mitte_x <= b[2] and b[1] <= mitte_y <= b[3] for b in boxen):
            continue  # gehört zu einer Tabelle
        t = _sauber(z["text"])
        if not t or _FUSSZEILE.match(t):
            continue
        elemente.append((z["top"], 0, {"text": t, "cells": None, "images": None, "level": None}))
    elemente.sort(key=lambda e: (e[0], e[1]))
    return [e[2] for e in elemente]



def lies_pdf(daten: bytes) -> Dokument:
    try:
        import pdfplumber
    except ImportError as e:  # pragma: no cover
        raise ExtraktionsFehler("PDF-Unterstützung ist auf dem Server nicht installiert.") from e
    d = Dokument(quelle="pdf")
    try:
        with pdfplumber.open(io.BytesIO(daten)) as pdf:
            d.seiten = len(pdf.pages)
            for seite in pdf.pages:
                d.zeilen.extend(_pdf_seite(seite))
    except ExtraktionsFehler:
        raise
    except Exception as e:  # noqa: BLE001
        raise ExtraktionsFehler("Das PDF konnte nicht gelesen werden.") from e
    if len(d.volltext) < 200:
        raise ExtraktionsFehler(
            "Das PDF enthält keinen auslesbaren Text (vermutlich ein Scan). "
            "Bitte laden Sie das Word-Dokument oder ein aus Word exportiertes PDF hoch."
        )
    return d


def lies_datei(dateiname: str, daten: bytes) -> Dokument:
    name = (dateiname or "").lower()
    if daten[:4] == b"%PDF" or name.endswith(".pdf"):
        return lies_pdf(daten)
    if daten[:2] == b"PK" or name.endswith(".docx"):
        return lies_docx(daten)
    raise ExtraktionsFehler("Bitte laden Sie eine .docx- oder .pdf-Datei hoch.")
