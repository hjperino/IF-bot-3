"""Ablauf einer Prüfung: einlesen → Formular erkennen → Struktur → lokale Prüfungen
→ Schwärzung → KI → Ergebnis zusammenführen."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from . import forms, llm
from . import local_checks as lc
from .extract import Dokument, lies_datei
from .redact import Schwaerzer

DATEN = Path(__file__).parent / "data"
MAX_ANTRAGSTEXT = 120_000  # Zeichen, Schutz vor übergrossen Dokumenten

LINK_FORMULARE = "https://www.dlh.zh.ch/home/innovationsfonds/projektfoerderung"


class NichtUnterstuetzt(Exception):
    pass


_PROJEKTE: Optional[list] = None


def projekte() -> list:
    global _PROJEKTE
    if _PROJEKTE is None:
        with open(DATEN / "projekte.json", encoding="utf-8") as f:
            _PROJEKTE = json.load(f)["innovationsfonds_projects"]
    return _PROJEKTE


# ---------------------------------------------------------------- Textpflege der KI-Ausgabe

_ERSATZ = [
    (r"\bJury-?[Ee]ntscheid(ung|s|es)?\b", "offizieller Entscheid"),
    (r"\bJurymitglieder(n)?\b", "zuständige Stellen"),
    (r"\b([Dd]ie|[Ee]ine) Jury\b", r"\1 offizielle Prüfung"),
    (r"\b([Dd]er|[Ee]iner) Jury\b", r"\1 offiziellen Prüfung"),
    (r"\bJury\b", "offizielle Prüfung"),
]
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿️‍]")


def pflege(text) -> str:
    if not isinstance(text, str):
        return ""
    t = text.replace("ß", "ss")
    for rx, neu in _ERSATZ:
        t = re.sub(rx, neu, t)
    t = _EMOJI.sub("", t)
    return re.sub(r"[ \t]+", " ", t).strip()


def _sortierschluessel(abschnitt: str):
    m = re.match(r"\s*(\d+(?:\.\d+)*)", abschnitt)
    if not m:
        return (0,)
    return tuple(int(x) for x in m.group(1).split("."))


def projekttitel(deck: List[dict]) -> str:
    for i, z in enumerate(deck):
        if re.search(r"Projekteingabe", z["text"]):
            for kandidat in (z["text"], deck[i + 1]["text"] if i + 1 < len(deck) else ""):
                m = re.search(r"«\s*(.*?)\s*»", kandidat)
                if m:
                    t = m.group(1).strip()
                    return "" if (not t or lc.PLATZHALTER.search(t)) else t
    return ""


# ---------------------------------------------------------------- Hauptablauf

def pruefe(dateiname: str, daten: bytes, formular_wahl: str = "auto") -> dict:
    dok: Dokument = lies_datei(dateiname, daten)
    fid = formular_wahl if formular_wahl in forms.FORMULARE else forms.erkenne_formular(dok.volltext, dok.zeilen)
    if fid is None:
        raise NichtUnterstuetzt(
            "Das hochgeladene Dokument konnte keinem unterstützten Projekteingabeformular zugeordnet werden. "
            "Unterstützt werden die Formulare Digital Explorer, Learning Incubator und Hub Scaler (Version 7.1) "
            "sowie das bisherige Formular Version 6.1."
        )
    f = forms.FORMULARE[fid]
    ergebnis = {
        "formular_id": fid, "formular": f["name"], "formular_kurz": f["kurz"], "quelle": dok.quelle,
        "projekttitel": "", "abbruch": None, "zeilen": [], "messwerte": [], "staerken": [],
        "rueckfragen": [], "fazit": "", "aehnliche_projekte": [], "hinweise": [],
    }

    # 1) Struktur (zwingend, vor allem anderen)
    pos, probleme = forms.pruefe_struktur(dok.zeilen, fid, dok.quelle)
    if probleme:
        ergebnis["abbruch"] = {
            "text": ("Entweder wurde nicht das erwartete Formular verwendet, oder vorhandene Titel im Formular "
                     "wurden gelöscht, verändert oder verschoben. Deshalb führe ich keine weitere inhaltliche Prüfung durch."),
            "tabelle": probleme,
        }
        if dok.quelle == "pdf":
            ergebnis["hinweise"].append(
                "Bei PDF-Dateien kann die Titelerkennung an Zeilenumbrüchen scheitern. "
                "Falls Sie das Formular unverändert verwendet haben, laden Sie bitte die Word-Datei (.docx) hoch.")
        return ergebnis

    abschnitte = forms.schneide_abschnitte(dok.zeilen, fid, pos)
    deck = forms.deckblatt(dok.zeilen, pos)
    ergebnis["projekttitel"] = projekttitel(deck)

    # 2) Bereinigung und Messung
    rein: Dict[str, dict] = {nr: lc.bereinige(z, fid) for nr, z in abschnitte.items()}
    inhalt = {nr: r["inhalt"] for nr, r in rein.items()}
    hilfstexte = sum(r["hilfstexte"] for r in rein.values())
    platzhalter = sum(r["platzhalter"] for r in rein.values())
    messwerte = lc.messe(inhalt, fid, dok.quelle, dok.hat_fussnoten)
    ergebnis["messwerte"] = messwerte

    # 3) lokale Zeilen
    lokal_zeilen: List[dict] = []
    formales, st = [f"Erkannt: {f['name']}. Alle erwarteten Kapitel sind in der richtigen Reihenfolge vorhanden."], lc.OK
    if not ergebnis["projekttitel"]:
        formales.append("Auf der Titelseite ist kein Projekttitel eingetragen (oder der Platzhalter steht noch).")
        st = lc.TEIL
    if platzhalter:
        formales.append(f"Es stehen noch {platzhalter} Platzhalter («Schreiben Sie hier...» o. ä.) im Dokument.")
        st = lc.TEIL
    todos = []
    if not ergebnis["projekttitel"]:
        todos.append("Bitte den Projekttitel auf der Titelseite eintragen.")
    if platzhalter:
        todos.append("Bitte die Platzhalter durch Ihren Text ersetzen oder löschen.")
    if hilfstexte:
        wort = "oranger Ausfüllhinweis" if hilfstexte == 1 else "orange Ausfüllhinweise"
        formales.append(f"Es {'steht' if hilfstexte == 1 else 'stehen'} noch {hilfstexte} {wort} im Dokument.")
        todos.append("Bitte die orangen Ausfüllhinweise vor der Einreichung löschen (siehe Hinweis auf der Titelseite).")
        st = lc.TEIL
    if dok.hat_kommentare or dok.hat_aenderungen:
        formales.append("Aus meiner Sicht als KI sind noch Kommentare oder Bearbeitungsspuren (Änderungsverfolgung) vorhanden.")
        todos.append("Vorschlag: Kommentare und Bearbeitungsspuren für ein sauberes Erscheinungsbild entfernen.")
        st = lc.TEIL
    todo = " ".join(todos)
    lokal_zeilen.append({"abschnitt": "Formular und Formales", "status": st, "befund": " ".join(formales), "todo": todo})

    stunden = lc.pruefe_stunden(abschnitte, fid, dok.quelle)
    sach = lc.pruefe_sachmittel(abschnitte, fid)
    team = lc.pruefe_team(abschnitte, fid, dok.quelle)
    for z in (stunden, sach):
        if z:
            lokal_zeilen.append({k: z[k] for k in ("abschnitt", "status", "befund", "todo")})
    lokal_zeilen.extend(team["zeilen"])
    for z in lokal_zeilen:
        z["quelle"] = "lokal"

    # 4) Text für die KI: ohne Projektteam, geschwärzt
    sw = Schwaerzer(team["personen"])
    team_nrs = {f["team"], f["team_leitung"], f["team_weitere"]}
    kinder = {nr for nr, _ in f["titel"] if any(n2.startswith(nr + ".") for n2, _ in f["titel"])}
    ki_abschnitte, bloecke, leer = [], [], []
    for nr, titel in f["titel"]:
        if nr in team_nrs:
            continue
        zeilen = sw.zeilen(inhalt.get(nr, []))
        kopf = f"{nr} {titel}"
        if nr not in kinder:
            if not (fid == "D" and nr == "2.1"):
                ki_abschnitte.append(kopf)
            if not zeilen:
                leer.append(kopf)
        bloecke.append(f"### {kopf}\n" + ("\n".join(zeilen) if zeilen else ("(leer)" if nr not in kinder else "")))
    antragstext = f"PROJEKTTITEL: {sw.text(ergebnis['projekttitel']) or '(nicht eingetragen)'}\n\n" + "\n\n".join(bloecke)
    if len(antragstext) > MAX_ANTRAGSTEXT:
        antragstext = antragstext[:MAX_ANTRAGSTEXT] + "\n[… Text wegen Überlänge gekürzt …]"
        ergebnis["hinweise"].append("Der Antrag ist sehr lang; die inhaltliche Prüfung berücksichtigt nur den ersten Teil.")

    lokal = {
        "struktur": "bestanden",
        "dateiformat": dok.quelle,
        "leere_abschnitte": leer,
        "platzhalter_im_dokument": platzhalter,
        "stehen_gebliebene_hilfstexte": hilfstexte,
        "kommentare_oder_bearbeitungsspuren": bool(dok.hat_kommentare or dok.hat_aenderungen),
        "fussnoten_vorhanden": dok.hat_fussnoten,
        "laengenmessung": [
            {"kapitel": m["label"], "vorgabe": m["soll"], "messtext": m["messtext"], "ueber": m["ueber"],
             "hinweis": m["hinweis"]} for m in messwerte
        ],
        "arbeitsstunden": ({"status": stunden["status"], "befund": stunden["befund"]} if stunden else None),
        "zusaetzliche_mittel": ({"status": sach["status"], "befund": sach["befund"]} if sach else "kein Total erkennbar"),
        "projektteam": {
            "anzahl_personen": len(team["personen"]),
            "personen": [{k: sw.text(v) for k, v in p.items()} for p in team["zusammenfassung"]],
            "lokale_befunde": [{"abschnitt": z["abschnitt"], "status": z["status"]} for z in team["zeilen"]],
        },
    }
    kontext = {
        "formular_name": f["name"],
        "abschnitte_liste": ki_abschnitte,
        "lokal": lokal,
        "antragstext": antragstext,
        "projektliste": "\n".join(f"{p['title']} | {p['url']} | {p['short_description']}" for p in projekte()),
    }

    # 5) KI
    roh = llm.frage_ki(fid, kontext)

    # 6) Zusammenführen
    ki_zeilen = []
    for z in roh.get("zeilen", []):
        if not isinstance(z, dict):
            continue
        status = z.get("status") if z.get("status") in llm.STATUS else lc.UNKLAR
        ab = pflege(z.get("abschnitt")) or "–"
        if ab.lower().startswith("dokument"):
            ab = "Dokument – Titel und Gesamtbild"
        nr = re.match(r"\s*(\d+(?:\.\d+)*)", ab)
        if nr and nr.group(1) in team_nrs:
            continue  # Team wird nur lokal geprüft
        todo = pflege(z.get("todo"))
        if status == "erfuellt":
            todo = ""  # «erfüllt» und To-do schliessen sich aus
        ki_zeilen.append({"abschnitt": ab, "status": status, "befund": pflege(z.get("befund")),
                          "todo": todo, "quelle": "ki"})
    alle = lokal_zeilen + ki_zeilen
    reihenfolge = {id(z): i for i, z in enumerate(alle)}

    def _key(z):
        k = _sortierschluessel(z["abschnitt"])
        if k == (0,):  # dokumentweite Zeilen: lokal zuerst
            return (k, 0 if z["quelle"] == "lokal" else 1, reihenfolge[id(z)])
        return (k, 0 if z["quelle"] == "ki" else 1, reihenfolge[id(z)])

    alle.sort(key=_key)
    ergebnis["zeilen"] = alle
    ergebnis["staerken"] = [pflege(s) for s in roh.get("staerken", []) if pflege(s)][:3]
    ergebnis["rueckfragen"] = [pflege(s) for s in roh.get("rueckfragen", []) if pflege(s)][:5]
    ergebnis["fazit"] = pflege(roh.get("fazit"))
    bekannt = {p["url"].rstrip("/"): p for p in projekte()}
    for a in (roh.get("aehnliche_projekte") or [])[:3]:
        if not isinstance(a, dict):
            continue
        p = bekannt.get(str(a.get("url", "")).strip().rstrip("/"))
        if p is None:  # keine erfundenen Projekte/URLs durchlassen
            continue
        ergebnis["aehnliche_projekte"].append({
            "title": p["title"], "url": p["url"], "kurzbeschreibung": p["short_description"],
            "begruendung": pflege(a.get("begruendung")), "abgrenzungsfrage": pflege(a.get("abgrenzungsfrage")),
        })
    return ergebnis
