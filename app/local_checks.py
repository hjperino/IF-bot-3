"""Lokale, regelbasierte Prüfungen – ohne KI und ohne Datenabfluss.

- Bereinigung (Formular-Hilfstexte entfernen), Platzhalter erkennen
- Längenmessung
- Stunden-Total und Sachmittel
- Projektteam inkl. Schulberechtigung (Personendaten verlassen den Server nicht)
"""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from . import forms

DATEN = Path(__file__).parent / "data"

OK, TEIL, NEIN, UNKLAR = "erfuellt", "teilweise", "nicht_erfuellt", "nicht_beurteilbar"


def _lade(name: str):
    with open(DATEN / name, encoding="utf-8") as f:
        return json.load(f)


_VORLAGEN: Optional[dict] = None
_SCHULEN: Optional[list] = None


def vorlagen() -> dict:
    global _VORLAGEN
    if _VORLAGEN is None:
        roh = _lade("vorlagen.json")
        _VORLAGEN = {k: set(v) for k, v in roh.items()}
    return _VORLAGEN


def schulen() -> list:
    global _SCHULEN
    if _SCHULEN is None:
        _SCHULEN = _lade("schulen.json")["schulen"]
    return _SCHULEN


def zeilen_norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace(" ", " ")).strip().lower()


PLATZHALTER = re.compile(
    r"\[\s*schreiben sie hier|klicken sie hier|klicken oder tippen sie hier|geben sie hier ihren projekttitel",
    re.I,
)


# ---------------------------------------------------------------- Bereinigung

def bereinige(zeilen: List[dict], fid: str) -> dict:
    """Trennt Antragstext von unverändert stehen gebliebenen Formular-Hilfstexten."""
    vorl = vorlagen().get(fid, set())
    anfaenge = {v[:40] for v in vorl if v.startswith("[")}
    inhalt, hilfstexte, platzhalter = [], 0, 0
    im_block = False
    for z in zeilen:
        t = z["text"]
        if not t:
            continue
        # mehrzeilige Hilfstexte in eckigen Klammern (im PDF anders umbrochen als in der Vorlage)
        if im_block:
            if t.rstrip().endswith("]"):
                im_block = False
            continue
        n = zeilen_norm(t)
        if z["cells"] is None and n.startswith("[") and any(a.startswith(n[:40]) or n.startswith(a) for a in anfaenge) \
                and not PLATZHALTER.search(t):
            hilfstexte += 1
            if not t.rstrip().endswith("]"):
                im_block = True
            continue
        if PLATZHALTER.search(t):
            platzhalter += 1
            rest = PLATZHALTER.sub("", t)
            if len(re.sub(r"[\W_]+", "", rest)) < 25:
                continue
        if n in vorl:
            # Unveränderter Formulartext. Im Formular 6.1 gehören feste Sätze (z. B. in 6.2) zum Antrag.
            if fid == "61" and z["cells"] is None and len(t) > 30:
                inhalt.append(t)
            continue
        inhalt.append(t)
    return {"inhalt": inhalt, "hilfstexte": hilfstexte, "platzhalter": platzhalter}


# ---------------------------------------------------------------- Messung

_ABK = r"(?:z\.\s?B|d\.\s?h|u\.\s?a|u\.\s?ä|o\.\s?ä|o\.\s?a|bzw|ca|etc|inkl|exkl|evtl|usw|vgl|Nr|Abb|Kap|S|Std|max|min|ggf|sog|resp|Dr|Prof|St)\."


def zaehle_saetze(text: str) -> int:
    t = re.sub(_ABK, lambda m: m.group(0).replace(".", "§"), text, flags=re.I)
    t = re.sub(r"(\d)\.(\d)", r"\1§\2", t)      # 2.5, 1.1
    t = re.sub(r"(\d)\.(\s+[a-zäöü])", r"\1§\2", t)  # «im 2. semester»
    t = re.sub(r"(\d)\.(\s+(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember|"
               r"Semester|Quartal|Klasse|Lehrjahr|Schuljahr|Jahr|Lektion|Phase|Durchführung|Durchgang))", r"\1§\2", t)
    t = re.sub(r"\.{2,}|…", "§", t)
    teile = re.split(r"[.!?]+(?=\s|$|[»\"”)])", t)
    return sum(1 for s in teile if len(re.sub(r"[\W_]+", "", s)) >= 3)


def messe(abschnitte_inhalt: Dict[str, List[str]], fid: str, quelle: str, hat_fussnoten: bool) -> List[dict]:
    out = []
    for m in forms.FORMULARE[fid]["messung"]:
        kap = m["kapitel"]
        texte = []
        for nr, inhalt in abschnitte_inhalt.items():
            if nr == kap or nr.startswith(kap + "."):
                texte.extend(inhalt)
        text = " ".join(texte)
        mit = len(text)
        ohne = len(re.sub(r"\s+", "", text))
        e = {"label": m["label"], "art": m["art"], "zeichen_mit": mit, "zeichen_ohne": ohne}
        if m["art"] == "saetze":
            n = zaehle_saetze(text)
            e.update(wert=n, messtext=f"Gemessen: {n} Sätze.", soll=f"max. {m['soll']} Sätze",
                     ueber=n > m["schwelle"])
        elif m["art"] == "zeichen_ohne":
            e.update(wert=ohne, messtext=f"Gemessen: {ohne} Zeichen ohne Leerzeichen.",
                     soll=f"max. {m['soll']} Zeichen ohne Leerzeichen", ueber=ohne > m["schwelle"])
        else:  # seiten (Formulare 7.1) – Umrechnung ist eine Annahme, siehe forms.ZEICHEN_PRO_SEITE
            seiten = mit / forms.ZEICHEN_PRO_SEITE
            grenze = m["max_seiten"] * forms.ZEICHEN_PRO_SEITE * forms.TOLERANZ
            e.update(
                wert=round(seiten, 1),
                messtext=(f"Gemessen: {mit} Zeichen inkl. Leerzeichen, das entspricht rund "
                          f"{seiten:.1f} Seiten Fliesstext (Umrechnung: {forms.ZEICHEN_PRO_SEITE} Zeichen pro Seite)."),
                soll=f"Längenempfehlung: {m['soll_text']}",
                ueber=mit > grenze,
            )
        e["hinweis"] = ""
        if quelle == "pdf":
            e["hinweis"] = ("Im PDF lassen sich Fussnoten und Formular-Hilfstexte nicht sicher vom Haupttext "
                            "trennen; der Messwert ist deshalb eine Näherung.")
        elif hat_fussnoten:
            e["hinweis"] = "Fussnoten sind nicht mitgezählt."
        out.append(e)
    return out


# ---------------------------------------------------------------- Zahlen

_ZAHL = re.compile(r"(?<![\w.])\d{1,3}(?:['’`´   ]\d{3})+(?:[.,]\d+)?|(?<![\w.])\d+(?:[.,]\d+)?")


def zahlen(text: str) -> List[float]:
    out = []
    for m in _ZAHL.finditer(text):
        s = re.sub(r"['’`´   ]", "", m.group(0)).replace(",", ".")
        if s.count(".") > 1:
            continue
        try:
            out.append(float(s))
        except ValueError:
            pass
    return out


def _fmt(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{x:.1f}"


def pruefe_stunden(abschnitte: Dict[str, List[dict]], fid: str, quelle: str) -> Optional[dict]:
    f = forms.FORMULARE[fid]
    st = f["stunden"]
    if "fix" in st:
        return {
            "abschnitt": "2.1 Arbeitsstunden", "status": OK, "wert": st["fix"],
            "befund": (f"Digital-Explorer-Projekte werden pauschal mit {st['fix']} Arbeitsstunden unterstützt "
                       f"(max. {st['max_pro_lp_jahr']} Arbeitsstunden pro Lehrperson und Jahr). "
                       "Eine eigene Stundenplanung ist in diesem Formular nicht vorgesehen."),
            "todo": "",
        }
    nr = f["planung"]
    titel = f"{nr} {forms.titel_von(fid, nr)} – Total (offen)"
    zeile = None
    for z in abschnitte.get(nr, []):
        if re.search(st["zeile"], z["text"], flags=re.I):
            zeile = z
    if zeile is None:
        return {"abschnitt": titel, "status": UNKLAR, "wert": None,
                "befund": "Die Total-Zeile der Grobplanung wurde nicht gefunden.",
                "todo": "Bitte prüfen, ob die Tabelle der Grobplanung vollständig vorhanden ist."}
    wert, unsicher = None, False
    if zeile["cells"]:
        letzte = zeile["cells"][-1]
        zz = zahlen(letzte)
        if zz:
            wert = zz[-1]
        else:
            andere = [x for c in zeile["cells"][1:-1] for x in zahlen(c)]
            if andere:
                wert, unsicher = andere[-1], True
    else:
        rest = re.split(st["zeile"], zeile["text"], flags=re.I)[-1]
        rest = re.sub(r"finanziert bzw\. offen|beantragt zur finanzierung.*?:", "", rest, flags=re.I)
        zz = zahlen(rest)
        if zz:
            wert = zz[-1]
            unsicher = fid == "61" and len(zz) < 2  # im PDF nicht erkennbar, welche Spalte gemeint ist
    if wert is None:
        return {"abschnitt": titel, "status": NEIN, "wert": None,
                "befund": "Im Feld für das Total der offenen Arbeitsstunden ist keine Zahl eingetragen.",
                "todo": f"Bitte das Total eintragen (Rahmen: {st['min']}–{st['max']} Arbeitsstunden)."}
    if unsicher:
        return {"abschnitt": titel, "status": UNKLAR, "wert": wert,
                "befund": (f"Gelesen: {_fmt(wert)} Arbeitsstunden. Es ist nicht zuverlässig erkennbar, "
                           "ob diese Zahl im Feld «offen» steht."),
                "todo": f"Bitte prüfen: Das Total «offen» soll zwischen {st['min']} und {st['max']} Arbeitsstunden liegen."}
    if st["min"] <= wert <= st["max"]:
        return {"abschnitt": titel, "status": OK, "wert": wert,
                "befund": f"Total offen: {_fmt(wert)} Arbeitsstunden (Rahmen {st['min']}–{st['max']}).", "todo": ""}
    return {"abschnitt": titel, "status": NEIN, "wert": wert,
            "befund": (f"Total offen: {_fmt(wert)} Arbeitsstunden. Der Rahmen für dieses Formular beträgt "
                       f"{st['min']}–{st['max']} Arbeitsstunden."),
            "todo": "Bitte die Planung so anpassen, dass das Total im vorgegebenen Rahmen liegt."}


def pruefe_sachmittel(abschnitte: Dict[str, List[dict]], fid: str) -> Optional[dict]:
    f = forms.FORMULARE[fid]
    nr = f["mittel"]
    titel = f"{nr} {forms.titel_von(fid, nr)} – Betrag"
    grenze = f["sach_max"]
    betrag = None
    zeilen = abschnitte.get(nr, [])
    for z in zeilen:
        if z["cells"] and any(re.match(r"\s*total", c, flags=re.I) for c in z["cells"]):
            zz = zahlen(z["cells"][-1])
            if zz:
                betrag = zz[-1]
        elif not z["cells"]:
            m = re.search(r"im Umfang von\s+(.{0,40}?)\s*Franken", z["text"], flags=re.I)
            if m and zahlen(m.group(1)):
                betrag = zahlen(m.group(1))[-1]
            m = re.match(r"\s*total:?\s*(.*)$", z["text"], flags=re.I)
            if m and zahlen(m.group(1)):
                betrag = zahlen(m.group(1))[-1]
    if betrag is None:
        einzel = [x for z in zeilen if z["cells"] and len(z["cells"]) >= 3
                  and not re.match(r"\s*(begründung|total)", z["text"], flags=re.I)
                  for x in zahlen(z["cells"][-1])]
        if einzel:
            summe = sum(einzel)
            st = NEIN if summe > grenze else TEIL
            return {"abschnitt": titel, "status": st, "wert": summe,
                    "befund": (f"Es sind Beträge eingetragen (Summe gelesen: CHF {_fmt(summe)}), aber kein Total. "
                               f"Die maximale Sachzuwendung beträgt CHF {grenze}."),
                    "todo": "Bitte das Total in der Tabelle eintragen."}
        return None  # keine zusätzlichen Mittel erkennbar -> keine lokale Zeile
    if betrag > grenze:
        return {"abschnitt": titel, "status": NEIN, "wert": betrag,
                "befund": f"Beantragt: CHF {_fmt(betrag)}. Die maximale Sachzuwendung pro Projekt beträgt CHF {grenze}.",
                "todo": "Bitte den Betrag auf den zulässigen Rahmen reduzieren oder anderweitig finanzieren."}
    return {"abschnitt": titel, "status": OK, "wert": betrag,
            "befund": f"Beantragt: CHF {_fmt(betrag)} (maximal CHF {grenze}).", "todo": ""}


# ---------------------------------------------------------------- Schulen

def _sn(s: str) -> str:
    s = s.lower().replace("ß", "ss")
    s = re.sub(r"[^\wäöü ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def finde_schule(angabe: str) -> Optional[dict]:
    a = _sn(angabe)
    if not a:
        return None
    tokens_roh = set(re.findall(r"[A-Za-zÄÖÜäöü+]{2,}", angabe))
    beste, quote = None, 0.0
    for s in schulen():
        n = _sn(s["name"])
        if n and (n in a or (len(a) >= 8 and a in n)):
            return s
        k = s.get("kuerzel") or ""
        if k and len(k) >= 3 and k in tokens_roh:  # Kürzel exakt (Gross-/Kleinschreibung)
            return s
        q = difflib.SequenceMatcher(None, a, n).ratio()
        if q > quote:
            beste, quote = s, q
    return beste if quote >= 0.86 else None


# ---------------------------------------------------------------- Projektteam

FELDER = [
    ("name", r"^vorname,?\s*name"),
    ("fach", r"^fach\s*/\s*beruf"),
    ("anstellung", r"^anstellung"),
    ("schuladresse", r"^schuladresse"),
    ("schule", r"^schule"),
    ("email", r"^e-?mail"),
    ("telefon", r"^telefon"),
    ("kompetenzen", r"^fürs projekt relevante kompetenzen"),
    ("beteiligung", r"^allfällige beteiligung"),
    ("unterschrift_lp", r"^ort, datum, unter-?\s?schrift lehrperson"),
    ("sl_kontakt", r"^zuständiger schullei-?\s?tungskontakt"),
    ("unterschrift_sl", r"^ort, datum, unter-?\s?schrift sl-kontakt"),
]
_LABEL_REST = {
    "beteiligung": r"^allfällige beteiligung\s*(in laufenden if-pro-?\s?jekten)?\s*(\(projekttitel,\s*zugeteilte stunden\))?",
    "sl_kontakt": r"^zuständiger schullei-?\s?tungskontakt\s*(\(e-?mail\))?",
    "kompetenzen": r"^fürs projekt relevante kompetenzen",
    "name": r"^vorname,?\s*name",
    "fach": r"^fach\s*/\s*beruf",
    "anstellung": r"^anstellung",
    "schuladresse": r"^schuladresse",
    "schule": r"^schule",
    "email": r"^e-?mail",
    "telefon": r"^telefon",
    "unterschrift_lp": r"^ort, datum, unter-?\s?schrift lehrperson",
    "unterschrift_sl": r"^ort, datum, unter-?\s?schrift sl-kontakt",
}

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PRIVAT_MAIL = re.compile(r"@(gmail|gmx|outlook|hotmail|bluewin|yahoo|icloud|me|live|msn|sunrise|hispeed|proton|protonmail)\.", re.I)
ANGEKREUZT = re.compile(r"[☒☑✓✔✗✘⊠]|\[\s*[xX]\s*\]|\(\s*[xX]\s*\)|(?<![\w])[xX]\s+unbefristete")


def lies_personen(zeilen: List[dict]) -> List[dict]:
    """Zerlegt die Zeilen eines Team-Kapitels in Personenblöcke."""
    personen, akt = [], None
    for z in zeilen:
        if z["cells"]:
            label = z["cells"][0]
            wert = " ".join(c for c in z["cells"][1:] if c).strip()
            bild = any(z["images"][1:]) if z["images"] else False
        else:
            label, wert, bild = z["text"], None, False
        ln = zeilen_norm(label)
        feld = next((f for f, rx in FELDER if re.match(rx, ln)), None)
        if feld is None:
            continue
        if wert is None:  # PDF/Fliesstext: Wert steht hinter dem Label in derselben Zeile
            wert = re.sub(_LABEL_REST[feld], "", z["text"].strip(), flags=re.I).strip(" :")
        if feld == "name":
            akt = {"felder": {}, "bilder": {}}
            personen.append(akt)
        if akt is None:
            continue
        akt["felder"][feld] = wert
        akt["bilder"][feld] = bild
    return [p for p in personen if any(v for k, v in p["felder"].items() if k != "anstellung")
            or ANGEKREUZT.search(p["felder"].get("anstellung", ""))]


def pruefe_team(abschnitte: Dict[str, List[dict]], fid: str, quelle: str) -> dict:
    f = forms.FORMULARE[fid]
    leit = lies_personen(abschnitte.get(f["team_leitung"], []))
    weitere = lies_personen(abschnitte.get(f["team_weitere"], []))
    # Zeilen direkt unter dem Hauptkapitel (falls Tabellen dorthin verschoben wurden)
    personen = [dict(p, rolle="Projektleitung") for p in leit[:1]]
    personen += [dict(p, rolle="Teammitglied") for p in leit[1:] + weitere]
    zeilen_out: List[dict] = []
    hinweise_pdf = quelle == "pdf"
    nr_l, nr_w = f["team_leitung"], f["team_weitere"]

    # ---- Teamgrösse
    n = len(personen)
    if n == 0:
        zeilen_out.append({"abschnitt": f"{f['team']} Projektteam", "status": NEIN,
                           "befund": "Im Kapitel Projektteam sind keine Personen eingetragen.",
                           "todo": "Bitte Projektleitung und mindestens ein weiteres Teammitglied eintragen."})
        return {"zeilen": zeilen_out, "personen": [], "zusammenfassung": []}
    if n == 1:
        zeilen_out.append({"abschnitt": f"{f['team']} Projektteam – Teamgrösse", "status": NEIN,
                           "befund": "Es ist nur eine Lehrperson aufgeführt. Unterstützt werden Teams von mindestens zwei Lehrpersonen.",
                           "todo": ("Mögliche Ergänzung: eine zweite Lehrperson mindestens für eine Anwendung, "
                                    "Erprobung oder Mitentwicklung einbeziehen.")})
    else:
        zeilen_out.append({"abschnitt": f"{f['team']} Projektteam – Teamgrösse", "status": OK,
                           "befund": f"{n} Lehrpersonen aufgeführt (Mindestgrösse: 2).", "todo": ""})

    # ---- pro Person
    zusammenfassung = []
    schul_ids, faecher = set(), set()
    for i, p in enumerate(personen, 1):
        fe = p["felder"]
        bez = "Projektleitung" if p["rolle"] == "Projektleitung" else f"Teammitglied {i - (1 if leit else 0)}"
        nr = nr_l if p["rolle"] == "Projektleitung" else nr_w
        fehlend, hinweise, status = [], [], OK
        pflicht = [("name", "Vorname, Name"), ("fach", "Fach/Beruf"), ("schule", "Schule"), ("email", "E-Mail")]
        if fid == "61":
            pflicht.insert(3, ("schuladresse", "Schuladresse"))
        else:
            pflicht.append(("kompetenzen", "Fürs Projekt relevante Kompetenzen"))
        if p["rolle"] == "Projektleitung":
            pflicht.append(("telefon", "Telefon"))
        for key, label in pflicht:
            if not fe.get(key):
                fehlend.append(label)
        mail = fe.get("email", "")
        if mail and not EMAIL.search(mail):
            hinweise.append("Die E-Mail-Angabe sieht nicht wie eine gültige Adresse aus.")
        elif mail and PRIVAT_MAIL.search(mail):
            hinweise.append("Es ist eine private E-Mail-Adresse angegeben; eine Schuladresse wäre vorzuziehen.")
        # Anstellung (nur Projektleitung)
        if p["rolle"] == "Projektleitung":
            a = fe.get("anstellung", "")
            if hinweise_pdf and not ANGEKREUZT.search(a):
                hinweise.append("Ob bei «Anstellung» eine Checkbox angewählt ist, lässt sich im PDF nicht zuverlässig erkennen.")
                status = UNKLAR
            elif not ANGEKREUZT.search(a):
                fehlend.append("Checkbox «unbefristete Anstellung» (obA oder mbA)")
        # Schulleitung
        sl = fe.get("sl_kontakt", "")
        if not sl:
            fehlend.append("Zuständiger Schulleitungskontakt (E-Mail)")
        elif not EMAIL.search(sl):
            hinweise.append("Beim Schulleitungskontakt fehlt eine E-Mail-Adresse.")
        # Unterschriften
        for key, label in (("unterschrift_lp", "Ort, Datum, Unterschrift Lehrperson"),
                           ("unterschrift_sl", "Ort, Datum, Unterschrift SL-Kontakt")):
            text, bild = fe.get(key, ""), p["bilder"].get(key, False)
            if bild:
                if not text:
                    hinweise.append(f"«{label}»: Unterschriftsbild vorhanden, Ort und Datum fehlen.")
            elif text:
                if hinweise_pdf:
                    hinweise.append(f"«{label}»: Text vorhanden; ob eine Unterschrift vorliegt, ist im PDF nicht zuverlässig erkennbar.")
                else:
                    hinweise.append(f"«{label}»: Ort/Datum eingetragen, aber kein Unterschriftsbild im Dokument "
                                    "(falls von Hand unterschrieben wird, ist das in Ordnung).")
            else:
                if hinweise_pdf:
                    hinweise.append(f"«{label}»: im PDF nicht zuverlässig erkennbar.")
                    if status == OK:
                        status = UNKLAR
                else:
                    fehlend.append(label)
        # Schulberechtigung
        schule = finde_schule(fe.get("schule", "")) if fe.get("schule") else None
        berechtigt_txt = "unbekannt"
        if fe.get("schule"):
            if schule is None:
                hinweise.append("Die angegebene Schule konnte der Liste der Sek-II-Schulen nicht eindeutig zugeordnet werden.")
                if status == OK:
                    status = UNKLAR
            elif schule["berechtigt"]:
                berechtigt_txt = "ja"
                schul_ids.add(schule["name"])
            else:
                berechtigt_txt = "nein"
                schul_ids.add(schule["name"])
        if fe.get("fach"):
            faecher.add(_sn(fe["fach"]))
        teile = []
        if fehlend:
            teile.append("Es fehlt: " + "; ".join(fehlend) + ".")
            status = NEIN if len(fehlend) >= 3 or "Vorname, Name" in fehlend else TEIL
        if berechtigt_txt == "nein":
            teile.append("Die angegebene Schule ist gemäss Schulenliste nicht berechtigt, Entlastungen aus dem Innovationsfonds zu beziehen.")
            status = NEIN
        elif berechtigt_txt == "ja":
            teile.append("Schule gemäss Schulenliste berechtigt.")
        teile.extend(hinweise)
        if not teile:
            teile.append("Angaben vollständig.")
        todo = ""
        if fehlend:
            todo = "Bitte die fehlenden Angaben ergänzen."
        elif berechtigt_txt == "nein":
            todo = "Bitte die Berechtigung mit der Geschäftsstelle klären."
        elif status == UNKLAR:
            todo = "Bitte diese Punkte selbst im Dokument kontrollieren."
        zeilen_out.append({"abschnitt": f"{nr} {bez}", "status": status,
                           "befund": " ".join(teile), "todo": todo})
        zusammenfassung.append({
            "rolle": bez,
            "fach": fe.get("fach", ""),
            "schultyp": (schule or {}).get("typ") or "unbekannt",
            "schule_berechtigt": berechtigt_txt,
            "kompetenzen": fe.get("kompetenzen", ""),
            "beteiligung_laufende_if_projekte": fe.get("beteiligung", ""),
        })

    # ---- Hub Scaler: Kooperation
    if f.get("kooperation") and n >= 2:
        if len(schul_ids) >= 2 or len(faecher) >= 2:
            zeilen_out.append({"abschnitt": f"{f['team']} Projektteam – Kooperation", "status": OK,
                               "befund": "Das Team ist überschulisch oder interdisziplinär zusammengesetzt.", "todo": ""})
        else:
            zeilen_out.append({"abschnitt": f"{f['team']} Projektteam – Kooperation", "status": TEIL,
                               "befund": ("Hub-Scaler-Projekte erfordern eine überschulische oder interdisziplinäre "
                                          "Zusammenarbeit. Aus den Angaben sind weder verschiedene Schulen noch verschiedene Fächer erkennbar."),
                               "todo": "Bitte die Teamzusammensetzung prüfen oder die Angaben zu Fach und Schule präzisieren."})
    return {"zeilen": zeilen_out, "personen": personen, "zusammenfassung": zusammenfassung}
