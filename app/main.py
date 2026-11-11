"""Web-Anwendung (FastAPI) für Render.

Start lokal:   uvicorn app.main:app --reload
Start Render:  uvicorn app.main:app --host 0.0.0.0 --port $PORT

Datenschutz: Hochgeladene Dateien und Ergebnisse werden nur im Arbeitsspeicher
verarbeitet und nicht gespeichert. Ins Log gelangen keine Inhalte.
"""
from __future__ import annotations

import base64
import datetime
import logging
import os
import threading
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from . import pipeline, report
from .extract import ExtraktionsFehler
from .llm import KIFehler

log = logging.getLogger("ifbot")
logging.basicConfig(level=logging.INFO)

STATIC = Path(__file__).parent / "static"
MAX_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "15")) * 1024 * 1024
LIMIT_IP = int(os.environ.get("LIMIT_PRO_IP_UND_TAG", "6"))
LIMIT_TOTAL = int(os.environ.get("LIMIT_TOTAL_PRO_TAG", "150"))

app = FastAPI(title="DLH-Innovationsfonds-Check", docs_url=None, redoc_url=None, openapi_url=None)

_zaehler_lock = threading.Lock()
_zaehler = {"tag": None, "ip": {}, "total": 0}


def _kontingent(ip: str) -> bool:
    """Einfaches Tageslimit im Arbeitsspeicher (wird bei Neustart zurückgesetzt)."""
    heute = datetime.date.today().isoformat()
    with _zaehler_lock:
        if _zaehler["tag"] != heute:
            _zaehler.update(tag=heute, ip={}, total=0)
        if _zaehler["total"] >= LIMIT_TOTAL or _zaehler["ip"].get(ip, 0) >= LIMIT_IP:
            return False
        _zaehler["total"] += 1
        _zaehler["ip"][ip] = _zaehler["ip"].get(ip, 0) + 1
        return True


def _ip(request: Request) -> str:
    weiter = request.headers.get("x-forwarded-for", "")
    if weiter:
        return weiter.split(",")[0].strip()
    return request.client.host if request.client else "unbekannt"


def _fehler(status: int, text: str) -> JSONResponse:
    return JSONResponse({"ok": False, "fehler": text}, status_code=status)


@app.get("/")
def startseite():
    return FileResponse(STATIC / "index.html", media_type="text/html; charset=utf-8",
                        headers={"Cache-Control": "no-cache"})


@app.get("/healthz")
def gesund():
    return {"ok": True}


@app.post("/api/pruefen")
def pruefen(
    request: Request,
    datei: UploadFile = File(...),
    einwilligung: str = Form(""),
    formular: str = Form("auto"),
):
    if einwilligung != "ja":
        return _fehler(400, "Bitte bestätigen Sie zuerst den Hinweis zur Datenverarbeitung.")
    daten = datei.file.read(MAX_BYTES + 1)
    if len(daten) > MAX_BYTES:
        return _fehler(413, f"Die Datei ist zu gross (maximal {MAX_BYTES // (1024 * 1024)} MB).")
    if not daten:
        return _fehler(400, "Die Datei ist leer.")
    if not _kontingent(_ip(request)):
        return _fehler(429, "Das Tageslimit für Prüfungen ist erreicht. Bitte versuchen Sie es morgen wieder.")
    try:
        ergebnis = pipeline.pruefe(datei.filename or "", daten, formular)
        pdf = report.als_pdf(ergebnis)
        seite = report.als_html(ergebnis)
    except ExtraktionsFehler as e:
        return _fehler(422, str(e))
    except pipeline.NichtUnterstuetzt as e:
        return _fehler(422, str(e))
    except KIFehler as e:
        log.warning("KI-Fehler: %s", type(e.__cause__).__name__ if e.__cause__ else "ohne Ursache")
        return _fehler(502, str(e))
    except Exception as e:  # noqa: BLE001 – bewusst ohne Inhalte loggen
        log.error("Unerwarteter Fehler: %s", type(e).__name__)
        return _fehler(500, "Bei der Prüfung ist ein unerwarteter Fehler aufgetreten. Bitte versuchen Sie es erneut.")
    finally:
        del daten
    log.info("Prüfung abgeschlossen: Formular %s, Abbruch %s", ergebnis["formular_id"], bool(ergebnis["abbruch"]))
    return {
        "ok": True,
        "html": seite,
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "dateiname": "Innovationsfonds-Check_Feedback_" + datetime.date.today().isoformat() + ".pdf",
        "abbruch": bool(ergebnis["abbruch"]),
    }
