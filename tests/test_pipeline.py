"""Tests der lokalen Prüfungen. Die KI wird nicht aufgerufen (MOCK_LLM=1).

Aufruf:  python tests/make_samples.py && python -m pytest tests -q
(oder ohne pytest:  python tests/test_pipeline.py)
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["MOCK_LLM"] = "1"

from app import forms, llm, pipeline, report  # noqa: E402
from app import local_checks as lc  # noqa: E402
from app.redact import Schwaerzer  # noqa: E402

OUT = ROOT / "tests" / "out"
REF = ROOT / "referenz"


def lauf(name, ordner=OUT, wahl="auto"):
    return pipeline.pruefe(name, (ordner / name).read_bytes(), wahl)


def zeile(r, start):
    return next(z for z in r["zeilen"] if z["abschnitt"].startswith(start))


def test_erkennung_und_struktur_leere_formulare():
    for datei, fid in [("Projekteingabefomular Digital Explorer.docx", "D"),
                       ("Projekteingabefomular Learning Incubator.docx", "L"),
                       ("Projekteingabefomular Hub Scaler.docx", "H"),
                       ("Projekteingabefomular (Version 6.1, Original).pdf", "61")]:
        r = lauf(datei, REF)
        assert r["formular_id"] == fid, datei
        assert r["abbruch"] is None, (datei, r["abbruch"])
        # leeres Formular: keine Personen, kein Titel
        assert zeile(r, "Formular und Formales")["status"] == lc.TEIL


def test_ok_antraege():
    for datei, fid in [("D_ok.docx", "D"), ("L_ok.docx", "L"), ("H_ok.docx", "H")]:
        r = lauf(datei)
        assert r["formular_id"] == fid and r["abbruch"] is None
        assert r["projekttitel"] == "Sprechen mit KI"
        team = [z for z in r["zeilen"] if "Teamgrösse" in z["abschnitt"]][0]
        assert team["status"] == lc.OK
    r = lauf("L_ok.docx")
    assert zeile(r, "5.1 Grobplanung mit Aufwandsabschätzung – Total")["status"] == lc.OK
    assert zeile(r, "5.3 Zusätzliche Mittel (Ergänzung zur gelben Kolonne) – Betrag")["status"] == lc.OK
    r = lauf("H_ok.docx")
    assert [z for z in r["zeilen"] if "Kooperation" in z["abschnitt"]][0]["status"] == lc.OK


def test_hilfstexte_und_fester_text():
    r = lauf("L_ok.docx")  # Testantrag enthält noch alle orangen Hinweise
    z = zeile(r, "Formular und Formales")
    assert z["status"] == lc.TEIL and "orange Ausfüllhinweise" in z["befund"] and "Platzhalter" not in z["todo"]
    # Formular 6.1: der feste Satz in 6.2 bleibt Teil des Antragstexts
    gesehen = {}
    original = llm.frage_ki
    llm.frage_ki = lambda fid, k: (gesehen.update(k=k), original(fid, k))[1]
    try:
        lauf("Projekteingabefomular (Version 6.1, Original).pdf", REF)
    finally:
        llm.frage_ki = original
    assert "Wir beantragen beim Innovationsfonds so viele Arbeitsstunden" in gesehen["k"]["antragstext"]


def test_grenzen():
    r = lauf("L_stunden_zu_hoch.docx")
    assert zeile(r, "5.1 Grobplanung mit Aufwandsabschätzung – Total")["status"] == lc.NEIN
    assert zeile(r, "5.3 Zusätzliche Mittel (Ergänzung zur gelben Kolonne) – Betrag")["status"] == lc.NEIN
    r = lauf("H_stunden_zu_hoch.docx")  # 450 > 400
    assert zeile(r, "5.1 Grobplanung mit Aufwandsabschätzung – Total")["status"] == lc.NEIN


def test_umfang_summe_20_prozent():
    """Formulare 7.1: Hinweis erst, wenn die Summe der Längenempfehlungen um mehr als 20 % überschritten ist."""
    def mw(zeichen, seiten):
        return {"art": "seiten", "zeichen_mit": zeichen, "max_seiten": seiten, "hinweis": ""}
    # L: 1 + 1 + 3 + 0.5 = 5.5 Seiten = 17'600 Zeichen; Grenze +20 % = 21'120
    assert lc.messe_gesamt([mw(9000, 1), mw(3000, 1), mw(9000, 3), mw(120, 0.5)])["ueber"] is False   # 21'120: genau auf der Grenze
    g = lc.messe_gesamt([mw(9000, 1), mw(3000, 1), mw(9000, 3), mw(121, 0.5)])                        # ein Kapitel stark, Summe knapp darüber
    assert g["ueber"] is True and g["soll_seiten"] == 5.5
    assert lc.messe_gesamt([{"art": "saetze", "zeichen_mit": 99999}]) is None                         # Formular 6.1
    # im Ablauf: normaler Testantrag -> keine Zeile, keine Längenliste
    r = lauf("L_ok.docx")
    assert not [z for z in r["zeilen"] if z["abschnitt"] == "Dokument – Umfang"] and r["messwerte"] == []
    alt = forms.ZEICHEN_PRO_SEITE
    forms.ZEICHEN_PRO_SEITE = 100  # macht denselben Antrag künstlich «zu lang»
    try:
        r = lauf("L_ok.docx")
    finally:
        forms.ZEICHEN_PRO_SEITE = alt
    z = [z for z in r["zeilen"] if z["abschnitt"] == "Dokument – Umfang"]
    assert len(z) == 1 and z[0]["status"] == lc.TEIL and "5.5 Seiten" in z[0]["befund"] and r["messwerte"]
    # Formular 6.1 unverändert: Messwerte pro Kapitel bleiben
    assert lauf("Projekteingabefomular (Version 6.1, Original).pdf", REF)["messwerte"]


def test_stunden_und_schulleitung():
    assert forms.FORMULARE["L"]["stunden"]["min"] == 160 and forms.FORMULARE["H"]["stunden"]["min"] == 160
    assert forms.FORMULARE["D"]["stunden"]["fix"] == 160
    r = lauf("D_ok.docx")
    assert "160 Arbeitsstunden" in zeile(r, "2.1 Arbeitsstunden")["befund"]
    for fid in "DLH":
        txt = llm.baue_nachrichten(fid, {"formular_name": "x", "abschnitte_liste": [], "lokal": {},
                                          "antragstext": "t", "projektliste": "p"})[0]["content"]
        assert "OFFEN" not in txt and "Unterschrift des Schulleitungskontakts" in txt
    r = lauf("H_ok.docx")  # Teammitglied 1 ohne SL-Unterschrift
    assert "belegt, dass die Schulleitung" in zeile(r, "6.2 Teammitglied 1")["todo"]


def test_eine_person_ohne_kreuz():
    r = lauf("D_eine_person.docx")
    assert [z for z in r["zeilen"] if "Teamgrösse" in z["abschnitt"]][0]["status"] == lc.NEIN
    leitung = zeile(r, "3.1 Projektleitung")
    assert "Checkbox" in leitung["befund"]


def test_struktur_abbruch():
    r = lauf("L_titel_geloescht.docx")
    assert r["abbruch"] is not None
    assert any("3.2 Didaktik" in p["erwartet"] for p in r["abbruch"]["tabelle"])
    assert r["zeilen"] == []
    assert b"%PDF" == report.als_pdf(r)[:4]


def test_schwaerzung_und_kein_team_im_ki_text():
    gesehen = {}
    original = llm.frage_ki

    def spion(fid, kontext):
        gesehen["k"] = kontext
        return original(fid, kontext)

    llm.frage_ki = spion
    try:
        lauf("L_ok.docx")
    finally:
        llm.frage_ki = original
    alles = json.dumps(gesehen["k"], ensure_ascii=False)
    for geheim in ("Petra", "Muster", "Lukas", "petra.muster@kzo.ch", "044 123 45 67", "lukas.lang@gmail.com",
                   "rektor.beispiel", "leitung@bbw.ch", "Wetzikon, 1.11.2026"):
        assert geheim not in alles, geheim
    assert "[Person 1]" in alles and "[E-Mail]" in alles and "[Telefon]" in alles
    assert "Projektleitung und Kontaktperson" not in "\n".join(gesehen["k"]["abschnitte_liste"])
    # «lang» als Adjektiv bleibt stehen, obwohl eine Person «Lang» heisst
    s = Schwaerzer([{"felder": {"name": "Lukas Lang"}}])
    assert s.text("Das dauert lang. Lukas Lang und Lang, Lukas.") == "Das dauert lang. [Person 1] und [Person 1], [Person 1]."


def test_schulen():
    assert lc.finde_schule("Kantonsschule Zürcher Oberland")["berechtigt"] is True
    assert lc.finde_schule("KZO Wetzikon")["kuerzel"] == "KZO"
    assert lc.finde_schule("Freies Gymnasium Zürich")["berechtigt"] is False
    assert lc.finde_schule("Gymnasium Musterstadt") is None


def test_saetze_und_zahlen():
    assert lc.zaehle_saetze("Das ist z. B. ein Satz. Am 3. März kostet es 2.5 Franken! Wirklich?") == 3
    assert lc.zahlen("CHF 1'200.50 und 4 800") == [1200.5, 4800.0]


def test_ki_ausgabe_wird_bereinigt():
    assert "Jury" not in pipeline.pflege("Die Jury könnte fragen, ob der Jury das genügt. 🟢")
    assert pipeline.pflege("Maßnahme") == "Massnahme"


def test_html_und_pdf():
    r = lauf("H_ok.docx")
    h = report.als_html(r)
    assert "TEIL A" in h and "TEIL B" in h and "Disclaimer" in h and "Jury" not in h
    pdf = report.als_pdf(r)
    assert pdf[:4] == b"%PDF" and len(pdf) > 5000
    (OUT / "H_ok_feedback.pdf").write_bytes(pdf)
    (OUT / "H_ok_feedback.html").write_text(h, encoding="utf-8")


def test_prompt_enthaelt_alles():
    for fid in forms.FORMULARE:
        n = llm.baue_nachrichten(fid, {"formular_name": "x", "abschnitte_liste": ["1.1 a"], "lokal": {},
                                        "antragstext": "t", "projektliste": "p"})
        assert "DETAILINSTRUKTION" in n[0]["content"] and "FÖRDERKRITERIEN" in n[0]["content"]


if __name__ == "__main__":
    fehler = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fehler += 1
                import traceback
                print("FEHLER", name)
                traceback.print_exc()
    sys.exit(1 if fehler else 0)
