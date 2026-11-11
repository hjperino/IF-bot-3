"""Schwärzung von Personendaten, bevor Text an die KI-Schnittstelle geht.

Grenzen: Namen werden nur erkannt, wenn sie im Kapitel Projektteam stehen
(oder als Schulleitungskontakt-E-Mail ableitbar sind). Namen Dritter im
Fliesstext bleiben stehen.
"""
from __future__ import annotations

import re
from typing import Iterable, List

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Schweizer und internationale Telefonnummern (mind. 9 Ziffern, typische Trennzeichen)
TELEFON = re.compile(r"(?<![\w/])(?:\+|00)?\d{2,3}[\s./-]?\(?\d{1,3}\)?(?:[\s./-]?\d{2,4}){2,4}(?![\w/])")

_STOPP = {
    "und", "der", "die", "das", "von", "van", "de", "del", "della", "di", "du", "le", "la", "zu", "zur",
    "dr", "prof", "lic", "phil", "msc", "bsc", "ma", "ba", "herr", "frau",
}


class Schwaerzer:
    def __init__(self, personen: Iterable[dict]):
        self.namen: List[tuple] = []  # (regex, ersatz)
        for i, p in enumerate(personen, 1):
            name = (p.get("felder", {}).get("name") or "").strip()
            ersatz = f"[Person {i}]"
            if not name:
                continue
            voll = re.sub(r"\s+", " ", name)
            teile = [t for t in re.split(r"[\s,;/]+", voll) if len(t) >= 3 and t.lower().strip(".") not in _STOPP]
            muster = []
            if len(voll) >= 5:
                muster.append(re.escape(voll).replace(r"\ ", r"\s+"))
            if len(teile) >= 2:
                muster.append(r"\s+".join(re.escape(t) for t in reversed(teile)))
            muster.extend(re.escape(t) for t in sorted(teile, key=len, reverse=True))
            for m in muster:
                # bewusst mit Gross-/Kleinschreibung: «Lang» (Name) soll «lang» (Adjektiv) nicht treffen
                self.namen.append((re.compile(r"(?<![\wäöüÄÖÜ])" + m + r"(?![\wäöüÄÖÜ])"), ersatz))
            # Namensbestandteile aus E-Mail-Adressen (vorname.nachname@…)
            for feld in ("email", "sl_kontakt"):
                wert = p.get("felder", {}).get(feld) or ""
                for adr in EMAIL.findall(wert):
                    lokal = adr.split("@")[0]
                    for t in re.split(r"[._-]+", lokal):
                        if len(t) >= 4 and feld == "sl_kontakt":
                            self.namen.append((re.compile(r"(?<![\wäöüÄÖÜ])" + re.escape(t) + r"(?![\wäöüÄÖÜ])", re.I),
                                               "[Schulleitung]"))

    def text(self, s: str) -> str:
        if not s:
            return s
        s = EMAIL.sub("[E-Mail]", s)
        s = TELEFON.sub(self._tel, s)
        for rx, ersatz in self.namen:
            s = rx.sub(ersatz, s)
        return s

    @staticmethod
    def _tel(m: re.Match) -> str:
        ziffern = re.sub(r"\D", "", m.group(0))
        # Jahreszahlen-Bereiche, Beträge u. ä. nicht schwärzen
        return "[Telefon]" if 9 <= len(ziffern) <= 13 else m.group(0)

    def zeilen(self, zeilen: Iterable[str]) -> List[str]:
        return [self.text(z) for z in zeilen]
