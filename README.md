# IF-bot-3 – DLH-Innovationsfonds-Check

Web-Anwendung zur Selbstüberprüfung von Projektanträgen für den DLH-Innovationsfonds (Sek II, Kanton Zürich). Nachfolger des bisherigen GPT.

Antragstellende laden ihr ausgefülltes Formular hoch (.docx oder .pdf) und erhalten ein unverbindliches Feedback: auf der Seite und als PDF.

## Unterstützte Formulare

| Kürzel | Formular | Prüfliste |
|---|---|---|
| D | Digital Explorer (7.1) | `app/prompts/detail_D.md` (Entwurf) |
| L | Learning Incubator (7.1) | `app/prompts/detail_L.md` (Entwurf) |
| H | Hub Scaler (7.1) | `app/prompts/detail_H.md` (Entwurf) |
| 61 | Bisheriges Formular 6.1 | `app/prompts/detail_61.md` (unverändert aus dem GPT) |

## Ablauf einer Prüfung

1. Datei einlesen (nur im Arbeitsspeicher, nichts wird gespeichert).
2. Formulartyp erkennen.
3. Strukturprüfung. Fehlen Titel oder ist die Reihenfolge verändert: Abbruch mit Soll/Ist-Tabelle, kein KI-Aufruf.
4. Lokale, regelbasierte Prüfungen ohne KI: Textlängen, Stunden-Total, Sachmittel, Projektteam, Schulberechtigung, Platzhalter, Kommentare.
5. Schwärzung: Das Kapitel Projektteam geht nicht an die KI. Im übrigen Text werden Namen der Teammitglieder, E-Mail-Adressen und Telefonnummern ersetzt.
6. Inhaltliche Prüfung über die OpenAI-Schnittstelle (Systemprompt + Detailinstruktion + Förderkriterien + Projektliste).
7. Ergebnis als HTML und PDF.

## Einrichtung auf Render

Dienst: Web Service, Region Frankfurt.

- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health Check Path: `/healthz`

Umgebungsvariablen:

| Variable | Pflicht | Bedeutung |
|---|---|---|
| `OPENAI_API_KEY` | ja | API-Schlüssel (als Secret) |
| `OPENAI_MODEL` | ja | Modellname gemäss aktueller OpenAI-Dokumentation |
| `PYTHON_VERSION` | empfohlen | z. B. `3.12.7` |
| `OPENAI_TIMEOUT` | nein | Sekunden, Standard 240 |
| `LIMIT_PRO_IP_UND_TAG` | nein | Standard 6 |
| `LIMIT_TOTAL_PRO_TAG` | nein | Standard 150 |
| `MAX_UPLOAD_MB` | nein | Standard 15 |

## Lokal testen

```
pip install -r requirements.txt python-docx openpyxl pytest
python tests/make_samples.py        # erzeugt erfundene Test-Anträge in tests/out/
python -m pytest tests -q           # lokale Prüfungen, ohne KI
MOCK_LLM=1 uvicorn app.main:app --reload    # Seite auf http://127.0.0.1:8000, ohne KI-Kosten
```

## Daten aktualisieren

- Projektliste: `python tools/build_projects.py` (liest die DLH-Projektübersicht, schreibt `app/data/projekte.json`).
- Schulenliste und Formularvorlagen: neue Dateien in `referenz/` legen, dann `python tools/build_data.py`.
- Neue Formularversion: Titel in `app/forms.py` anpassen, Vorlage in `referenz/` ersetzen, `build_data.py` ausführen.

## Was wo geändert wird

| Anliegen | Datei |
|---|---|
| Ton, gesperrte Wörter, Ausgabeformat der KI | `app/prompts/system.md` |
| Prüfkriterien pro Formular | `app/prompts/detail_*.md` |
| Stundenrahmen, Seitenvorgaben, Kapiteltitel | `app/forms.py` |
| Texte der Webseite, Einwilligung | `app/static/index.html` |
| Disclaimer, Links, PDF-Layout | `app/report.py` |

## Schrift und Logos

Hausschrift des DLH ist Helvetica Neue LT Std (kostenpflichtig). Ersatz:

- Webseite: Helvetica Neue, wo installiert; sonst TeX Gyre Heros (freier Helvetica-Nachbau, GUST Font License), abgelegt in `app/static/fonts/`.
- PDF: Liberation Sans (SIL Open Font License), abgelegt in `app/fonts/`.

Die Logos in `app/static/img/` stammen aus den DLH-Web-Branding-Vorgaben vom 25.09.2024 (als PNG aus dem PDF gerendert).
