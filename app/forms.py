"""Definition der vier unterstützten Formulare und Strukturprüfung.

61 = Projekteingabeformular Version 6.1 (altes Einheitsformular)
D  = Digital Explorer, L = Learning Incubator, H = Hub Scaler (Formularversion 7.1)

Abklärungen der Geschäftsstelle (Stand 14.11.2026), hier umgesetzt für D, L, H:
- Umfang: Die Seitenangaben sind Empfehlungen. Rückmeldung nur, wenn die SUMME
  aller Längenempfehlungen eines Formulars um mehr als 20 % überschritten ist.
- Stunden: mindestens 160 (L, H); Digital Explorer fix 160, ohne Planung.
- Schulleitung: keine separate schriftliche Bewilligung mehr (auch nicht BB).
  Nachweis ist die Unterschrift des SL-Kontakts im Kapitel Projektteam.
Formular 6.1 läuft unverändert mit den alten Werten.
"""
from __future__ import annotations

import difflib
import re
from typing import Dict, List, Optional, Tuple

# Annahme aus dem früheren Prompt V6: 1 Seite ≈ 3'200 Zeichen inkl. Leerzeichen.
# Die Geschäftsstelle hat dazu keinen Wert genannt; bei Bedarf hier ändern.
ZEICHEN_PRO_SEITE = 3200
TOLERANZ = 1.2  # Formulare 7.1: Hinweis erst, wenn die Summe der Empfehlungen um mehr als 20 % überschritten ist

_TEAM_7 = [("Projektleitung und Kontaktperson", 2), ("Weitere Teammitglieder", 2)]

FORMULARE: Dict[str, dict] = {
    "61": {
        "name": "Projekteingabeformular Version 6.1",
        "kurz": "Formular 6.1",
        "erkennung": [r"Version\s*6\.1"],
        "titel": [
            ("1", "Kurzzusammenfassung"),
            ("1.1", "Ausgangslage, Innovationspotenzial und Lösungsansatz"),
            ("1.2", "Pädagogische Ziele, didaktische Umsetzung, Digitalität"),
            ("1.3", "Breite und langfristige Nutzung"),
            ("2", "Innovationspotenzial"),
            ("2.1", "Ausgangslage (Problem/Potenzial)"),
            ("2.2", "Innovation (das Neue) und Lösungsansatz"),
            ("3", "Pädagogisch-didaktisches Konzept/Digitalität"),
            ("3.1", "Pädagogik"),
            ("3.1.1", "Geförderte fachliche Kompetenzen"),
            ("3.1.2", "Geförderte überfachliche und digitale Kompetenzen"),
            ("3.1.3", "Weitere Ziele für SuS/Lernende, Lehrpersonen"),
            ("3.2", "Didaktik"),
            ("3.2.1", "Lernsetting, -prozess und -methoden"),
            ("3.2.2", "Zusammenarbeit Mensch - Technik"),
            ("3.2.3", "Erforderliche Infrastruktur"),
            ("3.3", "Evaluationsplanung"),
            ("3.3.1", "Zu evaluierende Ziele"),
            ("3.3.2", "Evaluationsprozess"),
            ("4", "Breite und langfristige Nutzung"),
            ("4.1", "Zielgruppen"),
            ("4.2", "Nachhaltigkeit"),
            ("5", "Projektteam"),
            ("5.1", "Projektleitung und Kontaktperson"),
            ("5.2", "Weitere Teammitglieder"),
            ("6", "Planung und Antrag"),
            ("6.1", "Grobplanung mit Aufwandsabschätzung"),
            ("6.2", "Entlastung von Lehrpersonen in Arbeitsstunden"),
            ("6.3", "Drittmittelausweis"),
            ("6.4", "Zusätzliche Mittel in Franken"),
            ("6.5", "Allfällige Bemerkungen"),
        ],
        "team": "5",
        "team_leitung": "5.1",
        "team_weitere": "5.2",
        "planung": "6.1",
        "mittel": "6.4",
        "optional": ["3.1.3", "6.3", "6.4", "6.5"],
        # Messregeln gemäss Detailinstruktion 6.1 (unverändert)
        "messung": [
            {"kapitel": "1", "label": "Kapitel 1.1–1.3", "art": "saetze", "soll": 10, "schwelle": 12},
            {"kapitel": "2", "label": "Kapitel 2.1–2.2", "art": "zeichen_ohne", "soll": 2000, "schwelle": 2400},
            {"kapitel": "3", "label": "Kapitel 3.1–3.3.2", "art": "zeichen_ohne", "soll": 5000, "schwelle": 6000},
            {"kapitel": "4", "label": "Kapitel 4.1–4.2", "art": "zeichen_ohne", "soll": 1000, "schwelle": 1200},
        ],
        "stunden": {"min": 150, "max": 800, "zeile": r"totale?\s+arbeitsstunden"},
        "sach_max": 5000,
    },
    "D": {
        "name": "Projekteingabe des Typs Digital Explorer (Formularversion 7.1)",
        "kurz": "Digital Explorer",
        "erkennung": [r"Typs\s+Digital[\s-]*Explorer"],
        "titel": [
            ("1", "Projektskizze"),
            ("1.1", "Ausgangslage, Innovationspotenzial und Lösungsansatz"),
            ("1.2", "Pädagogik, Didaktik/Unterrichtsorganisation, Digitalität"),
            ("1.3", "Evaluationsplanung"),
            ("2", "Antrag"),
            ("2.1", "Arbeitsstunden"),
            ("2.2", "Zusätzliche Mittel"),
            ("2.3", "Allfällige Bemerkungen"),
            ("3", "Projektteam"),
            ("3.1", "Projektleitung und Kontaktperson"),
            ("3.2", "Weitere Teammitglieder"),
        ],
        "team": "3",
        "team_leitung": "3.1",
        "team_weitere": "3.2",
        "planung": None,
        "mittel": "2.2",
        "optional": ["2.1", "2.2", "2.3"],
        "messung": [
            {"kapitel": "1", "label": "Kapitel 1.1–1.3", "art": "seiten", "soll_text": "2–3 Seiten", "max_seiten": 3},
        ],
        "stunden": {"fix": 160, "max_pro_lp_jahr": 80},
        "sach_max": 5000,
    },
    "L": {
        "name": "Projekteingabe des Typs Learning Incubator (Formularversion 7.1)",
        "kurz": "Learning Incubator",
        "erkennung": [r"Typs\s+Learning[\s-]*Incubator"],
        "titel": [
            ("1", "Kurzzusammenfassung"),
            ("1.1", "Innovationsumsetzungspotenzial"),
            ("1.2", "Pädagogik, Didaktik/Unterrichtsorganisation, Digitalität"),
            ("1.3", "Angedachte breite und langfristige Nutzung"),
            ("2", "Innovationsumsetzungspotenzial"),
            ("2.1", "Existierende Innovationsbasis"),
            ("2.2", "Potenzial für das Lernen/Lehren"),
            ("3", "Pädagogik, Didaktik/Organisation, Digitalität"),
            ("3.1", "Pädagogik"),
            ("3.1.1", "Geförderte fachliche Kompetenzen"),
            ("3.1.2", "Geförderte überfachliche und digitale Kompetenzen"),
            ("3.2", "Didaktik"),
            ("3.2.1", "Lern/Arbeitssetting, -prozess und -methoden"),
            ("3.2.2", "Zusammenarbeit Mensch – Technik"),
            ("3.2.3", "Erforderliche Infrastruktur"),
            ("3.3", "Evaluationsplanung"),
            ("3.3.1", "Grenzen und Risiken"),
            ("3.3.2", "Zu evaluierende Ziele"),
            ("3.3.3", "Evaluationsprozess"),
            ("4", "Angedachte breite und langfristige Nutzung"),
            ("4.1", "Zielgruppen"),
            ("4.2", "Leichte Zugänglichkeit und Nachhaltigkeit"),
            ("5", "Planung und Antrag"),
            ("5.1", "Grobplanung mit Aufwandsabschätzung"),
            ("5.2", "Drittmittelausweis (Ergänzung zur grünen Kolonne)"),
            ("5.3", "Zusätzliche Mittel (Ergänzung zur gelben Kolonne)"),
            ("5.4", "Allfällige Bemerkungen"),
            ("6", "Projektteam"),
            ("6.1", "Projektleitung und Kontaktperson"),
            ("6.2", "Weitere Teammitglieder"),
        ],
        "team": "6",
        "team_leitung": "6.1",
        "team_weitere": "6.2",
        "planung": "5.1",
        "mittel": "5.3",
        "optional": ["5.2", "5.3", "5.4"],
        "messung": [
            {"kapitel": "1", "label": "Kapitel 1.1–1.3", "art": "seiten", "soll_text": "maximal 1 Seite", "max_seiten": 1},
            {"kapitel": "2", "label": "Kapitel 2.1–2.2", "art": "seiten", "soll_text": "½–1 Seite", "max_seiten": 1},
            {"kapitel": "3", "label": "Kapitel 3.1–3.3.3", "art": "seiten", "soll_text": "2–3 Seiten", "max_seiten": 3},
            {"kapitel": "4", "label": "Kapitel 4.1–4.2", "art": "seiten", "soll_text": "½ Seite", "max_seiten": 0.5},
        ],
        "stunden": {"min": 160, "max": 800, "zeile": r"total\s+arbeitsstunden\s*\(offen\)"},
        "sach_max": 5000,
    },
    "H": {
        "name": "Projekteingabe des Typs Hub Scaler (Formularversion 7.1)",
        "kurz": "Hub Scaler",
        "erkennung": [r"Typs\s+Hub[\s-]*Scaler"],
        "titel": [
            ("1", "Kurzzusammenfassung"),
            ("1.1", "Zu skalierender innovativer Ansatz"),
            ("1.2", "Pädagogik, Didaktik/Unterrichtsorganisation, Digitalität"),
            ("1.3", "Zugänglichkeit und langfristige Verfügbarkeit"),
            ("2", "Zu skalierender innovativer Ansatz"),
            ("2.1", "Etablierte Innovationsbasis"),
            ("2.2", "Potenzial für das Lernen/Lehren"),
            ("3", "Pädagogik, Didaktik/Organisation, Digitalität"),
            ("3.1", "Pädagogik"),
            ("3.1.1", "Geförderte fachliche Kompetenzen"),
            ("3.1.2", "Geförderte überfachliche und digitale Kompetenzen"),
            ("3.2", "Didaktik"),
            ("3.2.1", "Lern-/Arbeitssetting, -prozess und -methoden"),
            ("3.2.2", "Zusammenarbeit Mensch – Technik"),
            ("3.2.3", "Erforderliche Infrastruktur"),
            ("4", "Zugänglichkeit und langfristige Verfügbarkeit"),
            ("4.1", "Leichte Zugänglichkeit"),
            ("4.2", "Nachhaltigkeit"),
            ("4.3", "Evaluationsplanung"),
            ("4.3.1", "Grenzen und Risiken"),
            ("4.3.2", "Zu evaluierende Ziele"),
            ("4.3.3", "Evaluationsprozess"),
            ("5", "Planung und Antrag"),
            ("5.1", "Grobplanung mit Aufwandsabschätzung"),
            ("5.2", "Drittmittelausweis (Ergänzung zur grünen Kolonne)"),
            ("5.3", "Zusätzliche Mittel (Ergänzung zur gelben Kolonne)"),
            ("5.4", "Allfällige Bemerkungen"),
            ("6", "Projektteam"),
            ("6.1", "Projektleitung und Kontaktperson"),
            ("6.2", "Weitere Teammitglieder"),
        ],
        "team": "6",
        "team_leitung": "6.1",
        "team_weitere": "6.2",
        "planung": "5.1",
        "mittel": "5.3",
        "optional": ["5.2", "5.3", "5.4"],
        "messung": [
            {"kapitel": "1", "label": "Kapitel 1.1–1.3", "art": "seiten", "soll_text": "maximal 1 Seite", "max_seiten": 1},
            {"kapitel": "2", "label": "Kapitel 2.1–2.2", "art": "seiten", "soll_text": "½–1 Seite", "max_seiten": 1},
            {"kapitel": "3", "label": "Kapitel 3.1–3.2.3", "art": "seiten", "soll_text": "1–3 Seiten", "max_seiten": 3},
            {"kapitel": "4", "label": "Kapitel 4.1–4.3.3", "art": "seiten", "soll_text": "ca. 1–2 Seiten", "max_seiten": 2},
        ],
        "stunden": {"min": 160, "max": 400, "zeile": r"total\s+arbeitsstunden\s*\(offen\)"},
        "sach_max": 5000,
        "kooperation": True,  # überschulisch oder interdisziplinär
    },
}


# ---------------------------------------------------------------- Normalisierung

def norm(s: str) -> str:
    """Vergleichsform eines Titels/einer Zeile: ohne Nummer, Gross-/Kleinschreibung,
    Strich- und Leerzeichenvarianten."""
    s = s.replace("­", "").replace(" ", " ")
    s = re.sub(r"^\s*\d+(\.\d+)*\.?\s+", "", s)  # führende Nummerierung
    s = s.lower()
    s = re.sub(r"[‐‑‒–—−-]", "-", s)
    s = re.sub(r"\s*([/\-,:()])\s*", r"\1", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip(" .:")


def erkenne_formular(volltext: str, zeilen: List[dict]) -> Optional[str]:
    kopf = volltext[:6000]
    for fid in ("D", "L", "H", "61"):
        for muster in FORMULARE[fid]["erkennung"]:
            if re.search(muster, kopf, flags=re.I):
                return fid
    # Rückfall: Formular mit den meisten gefundenen Titeln (mind. 60 %)
    vorhanden = {norm(z["text"]) for z in zeilen}
    beste, quote = None, 0.0
    for fid, f in FORMULARE.items():
        treffer = sum(1 for _, t in f["titel"] if norm(t) in vorhanden)
        q = treffer / len(f["titel"])
        if q > quote:
            beste, quote = fid, q
    return beste if quote >= 0.6 else None


# ---------------------------------------------------------------- Strukturprüfung

def _passt(zeile: dict, titel: str, quelle: str) -> bool:
    n, t = norm(zeile["text"]), norm(titel)
    if n == t:
        return True
    if quelle == "pdf" and len(t) > 12:
        # PDF: Zeilenumbrüche/Trennungen tolerieren
        return difflib.SequenceMatcher(None, n, t).ratio() >= 0.93
    return False


def pruefe_struktur(zeilen: List[dict], fid: str, quelle: str) -> Tuple[Dict[str, int], List[dict]]:
    """Sucht alle erwarteten Titel in der richtigen Reihenfolge.

    Rückgabe: (positionen, probleme). positionen: Nummer -> Zeilenindex.
    probleme: Liste {erwartet, gefunden, problem}; leer = Struktur in Ordnung.
    """
    titel = FORMULARE[fid]["titel"]
    kandidaten: Dict[str, List[int]] = {}
    for nr, t in titel:
        kandidaten[nr] = [
            i for i, z in enumerate(zeilen)
            if z["cells"] is None and _passt(z, t, quelle)
        ]
        # DOCX: echte Überschriften haben Vorrang vor gleichlautendem Fliesstext
        echte = [i for i in kandidaten[nr] if zeilen[i].get("level")]
        if echte:
            kandidaten[nr] = echte
    # rückwärts-gierig: letzter Titel = letztes Vorkommen; jeder davor = letztes Vorkommen davor.
    # So wird ein allfälliges Inhaltsverzeichnis am Dokumentanfang übergangen.
    pos: Dict[str, int] = {}
    grenze = len(zeilen)
    for nr, _ in reversed(titel):
        davor = [i for i in kandidaten[nr] if i < grenze]
        if davor:
            pos[nr] = davor[-1]
            grenze = davor[-1]
    probleme = []
    for nr, t in titel:
        if nr in pos:
            continue
        if kandidaten[nr]:
            probleme.append({
                "erwartet": f"{nr} {t}",
                "gefunden": f"«{zeilen[kandidaten[nr][0]]['text'][:90]}» an anderer Stelle",
                "problem": "Titel steht nicht an der erwarteten Position (Reihenfolge verändert).",
            })
            continue
        # ähnlichste Zeile suchen, um veränderte Titel zu zeigen
        beste, quote = "", 0.0
        nt = norm(t)
        for z in zeilen:
            if z["cells"] is not None or len(z["text"]) > 140:
                continue
            q = difflib.SequenceMatcher(None, norm(z["text"]), nt).ratio()
            if q > quote:
                beste, quote = z["text"], q
        if quote >= 0.7:
            probleme.append({
                "erwartet": f"{nr} {t}",
                "gefunden": f"«{beste[:90]}»",
                "problem": "Titel wurde vermutlich verändert.",
            })
        else:
            probleme.append({
                "erwartet": f"{nr} {t}",
                "gefunden": "–",
                "problem": "Titel fehlt.",
            })
    return pos, probleme


def schneide_abschnitte(zeilen: List[dict], fid: str, pos: Dict[str, int]) -> Dict[str, List[dict]]:
    """Nummer -> Zeilen zwischen diesem und dem nächsten Titel (ohne Titelzeile)."""
    titel = FORMULARE[fid]["titel"]
    reihen = [(pos[nr], nr) for nr, _ in titel if nr in pos]
    reihen.sort()
    out: Dict[str, List[dict]] = {}
    for k, (start, nr) in enumerate(reihen):
        ende = reihen[k + 1][0] if k + 1 < len(reihen) else len(zeilen)
        out[nr] = zeilen[start + 1:ende]
    return out


def deckblatt(zeilen: List[dict], pos: Dict[str, int]) -> List[dict]:
    erste = min(pos.values()) if pos else len(zeilen)
    return zeilen[:erste]


def titel_von(fid: str, nr: str) -> str:
    return dict(FORMULARE[fid]["titel"])[nr]
