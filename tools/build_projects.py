"""Baut app/data/projekte.json aus der DLH-Projektübersicht neu auf.

Aufruf (im Repo-Hauptordner, braucht Internetzugang):
    pip install requests beautifulsoup4
    python tools/build_projects.py

Die Übersichtsseite lädt jeweils 12 Projekte nach («Mehr laden»). Dieses Script
ruft dieselbe Nachlade-Adresse auf, bis nichts mehr kommt.
Stand der Seitenstruktur: 11.11.2026. Ändert der DLH die Seite, muss das Script
angepasst werden.
"""
import datetime
import json
import re
import unicodedata
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASIS = "https://www.dlh.zh.ch"
UEBERSICHT = BASIS + "/home/innovationsfonds/projektvorstellungen/uebersicht"
NACHLADEN = BASIS + "/templates/yootheme_child/builder/article-grid-loadmore/ajax.php?catid={cat}&offset={off}"
OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "projekte.json"


def sauber(s: str) -> str:
    return unicodedata.normalize("NFC", re.sub(r"\s+", " ", s or "").strip())


def karten(html: str):
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.select('.el-item a[href*="/projektvorstellungen/uebersicht/"]'):
        titel = a.select_one(".el-title")
        text = a.select_one(".el-content")
        if not titel:
            continue
        href = a["href"].split("?")[0]
        yield {
            "title": sauber(titel.get_text()),
            "url": href if href.startswith("http") else BASIS + href,
            "short_description": sauber(text.get_text() if text else ""),
        }


def main():
    s = requests.Session()
    s.headers["User-Agent"] = "IF-bot-3 Projektlisten-Aktualisierung"
    seite = s.get(UEBERSICHT, timeout=30)
    seite.raise_for_status()
    projekte = list(karten(seite.text))
    m = re.search(r'data-category="(\d+)"', seite.text)
    cat = m.group(1) if m else "143"
    off = len(projekte)
    while True:
        r = s.get(NACHLADEN.format(cat=cat, off=off), timeout=30)
        r.raise_for_status()
        neu = list(karten(r.text))
        if not neu:
            break
        projekte.extend(neu)
        off += 12
    eindeutig = list({p["url"]: p for p in projekte}.values())
    OUT.write_text(json.dumps({
        "stand": datetime.date.today().isoformat(),
        "quelle": UEBERSICHT,
        "innovationsfonds_projects": eindeutig,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(eindeutig), "Projekte geschrieben nach", OUT)


if __name__ == "__main__":
    main()
