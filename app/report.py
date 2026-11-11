"""Darstellung des Prüfergebnisses als HTML (für die Webseite) und als PDF (Download)."""
from __future__ import annotations

import datetime
import html
import io
from pathlib import Path

DISCLAIMER_START = [
    "Dieser Bot dient der Selbstüberprüfung Ihres Innovationsfonds-Antrags.",
    "Er weist auf mögliche formale, strukturelle und inhaltliche Lücken hin.",
    "Die Einschätzung ist unverbindlich und ersetzt keine offizielle Prüfung.",
]
DISCLAIMER_ENDE = [
    "Dieser Bot dient der Selbstüberprüfung Ihres Innovationsfonds-Antrags.",
    "Die Einschätzung ist unverbindlich und ersetzt keine offizielle Prüfung.",
]
LINK_TERMINE = "https://dlh.zh.ch/home/innovationsfonds/termine"
LINK_ANMELDUNG = "https://dlh.zh.ch/home/innovationsfonds/projektanmeldungen"

STATUS = {
    "erfuellt": ("✔", "erfüllt", "#2e7d4f"),
    "teilweise": ("⚠️", "teilweise erfüllt", "#c25400"),
    "nicht_erfuellt": ("❌", "nicht erfüllt", "#b3261e"),
    "nicht_beurteilbar": ("❔", "nicht beurteilbar", "#5b5b6b"),
}

e = html.escape


# ---------------------------------------------------------------- HTML

def als_html(r: dict) -> str:
    t = []
    t.append('<div class="disclaimer"><strong>Disclaimer</strong><br>' + "<br>".join(map(e, DISCLAIMER_START)) + "</div>")
    kopf = f"Erkanntes Formular: {r['formular']}"
    if r.get("projekttitel"):
        kopf += f" · Projekttitel: «{r['projekttitel']}»"
    t.append(f'<p class="meta">{e(kopf)}</p>')
    for h in r.get("hinweise", []):
        t.append(f'<p class="hinweis">{e(h)}</p>')

    if r.get("abbruch"):
        t.append(f"<p><strong>{e(r['abbruch']['text'])}</strong></p>")
        t.append('<div class="tabwrap"><table><thead><tr><th>Erwartet</th><th>Gefunden</th><th>Problem</th></tr></thead><tbody>')
        for z in r["abbruch"]["tabelle"]:
            t.append(f"<tr><td>{e(z['erwartet'])}</td><td>{e(z['gefunden'])}</td><td>{e(z['problem'])}</td></tr>")
        t.append("</tbody></table></div>")
    else:
        t.append("<h2>TEIL A – Prüftabelle</h2>")
        t.append('<div class="tabwrap"><table class="pruef"><thead><tr><th>Abschnitt</th><th>Status</th><th>Befund</th><th>To-do</th></tr></thead><tbody>')
        for z in r["zeilen"]:
            sym, label, _ = STATUS.get(z["status"], STATUS["nicht_beurteilbar"])
            lokal = ' <span class="lokal" title="regelbasiert geprüft, ohne KI">regelbasiert</span>' if z.get("quelle") == "lokal" else ""
            t.append(
                f'<tr class="st-{e(z["status"])}"><td>{e(z["abschnitt"])}{lokal}</td>'
                f'<td class="status"><span aria-hidden="true">{sym}</span> {e(label)}</td>'
                f'<td>{e(z["befund"])}</td><td>{e(z["todo"])}</td></tr>'
            )
        t.append("</tbody></table></div>")
        if r.get("messwerte"):
            t.append("<h3>Längenmessung</h3><ul>")
            for m in r["messwerte"]:
                zusatz = f" {m['hinweis']}" if m.get("hinweis") else ""
                marke = " – über der Vorgabe" if m["ueber"] else ""
                t.append(f"<li><strong>{e(m['label'])}</strong> ({e(m['soll'])}): {e(m['messtext'])}{e(marke)}{e(zusatz)}</li>")
            t.append("</ul>")
        t.append("<h2>TEIL B – Kurzbewertung</h2>")
        t.append("<h3>🟢 Stärken</h3><ul>" + "".join(f"<li>{e(s)}</li>" for s in r["staerken"]) + "</ul>")
        t.append("<h3>🔴 Mögliche kritische Rückfragen</h3><ul>" + "".join(f"<li>{e(s)}</li>" for s in r["rueckfragen"]) + "</ul>")
        t.append(f"<h3>🟣 Fazit</h3><p>{e(r['fazit'])}</p>")
        if r.get("aehnliche_projekte"):
            t.append("<h2>Ähnliche bestehende Projekte</h2><p>Ähnlichkeit ist nicht negativ; die Hinweise dienen der Abgrenzung.</p><ul>")
            for a in r["aehnliche_projekte"]:
                t.append(
                    f'<li><a href="{e(a["url"])}" target="_blank" rel="noopener">{e(a["title"])}</a><br>'
                    f'{e(a["kurzbeschreibung"])}<br><em>Ähnlichkeit:</em> {e(a["begruendung"])}<br>'
                    f'<em>Mögliche Abgrenzungsfrage:</em> {e(a["abgrenzungsfrage"])}</li>'
                )
            t.append("</ul>")

    t.append("<h2>Beratung &amp; offizielle Anmeldung</h2>"
             "<p>Falls Sie Rückfragen haben oder Ihren Antrag gezielt weiterentwickeln möchten:</p><ul>"
             f'<li>Beratungstermine: <a href="{LINK_TERMINE}" target="_blank" rel="noopener">{LINK_TERMINE}</a></li>'
             f'<li>Offizielle Anmeldung und Prüfung über die DLH-Seite: <a href="{LINK_ANMELDUNG}" target="_blank" rel="noopener">{LINK_ANMELDUNG}</a></li></ul>')
    t.append('<div class="disclaimer"><strong>Disclaimer</strong><br>' + "<br>".join(map(e, DISCLAIMER_ENDE)) + "<br>🟣 Ende</div>")
    return "\n".join(t)


# ---------------------------------------------------------------- PDF

_FONTS_OK = False


def _fonts():
    global _FONTS_OK
    if _FONTS_OK:
        return
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    ordner = Path(__file__).parent / "fonts"
    pdfmetrics.registerFont(TTFont("DLH", str(ordner / "LiberationSans-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("DLH-Bold", str(ordner / "LiberationSans-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("DLH-Italic", str(ordner / "LiberationSans-Italic.ttf")))
    pdfmetrics.registerFontFamily("DLH", normal="DLH", bold="DLH-Bold", italic="DLH-Italic", boldItalic="DLH-Bold")
    _FONTS_OK = True


def _p(text: str) -> str:
    """Text für reportlab-Paragraph: escapen, nicht darstellbare Zeichen ersetzen."""
    from reportlab.pdfbase import pdfmetrics

    try:
        vorhanden = pdfmetrics.getFont("DLH").face.charToGlyph
    except Exception:  # noqa: BLE001
        vorhanden = None
    out = []
    for ch in text or "":
        if ch in "\n\t":
            out.append(" ")
        elif vorhanden is not None and ord(ch) not in vorhanden:
            out.append("")
        else:
            out.append(ch)
    return html.escape("".join(out), quote=False)


def als_pdf(r: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    _fonts()
    dunkel, orange, violett, hell = colors.HexColor("#1d3437"), colors.HexColor("#ec6608"), colors.HexColor("#8a5da4"), colors.HexColor("#dccee4")
    n = ParagraphStyle("n", fontName="DLH", fontSize=9.5, leading=13, textColor=dunkel)
    klein = ParagraphStyle("klein", parent=n, fontSize=8.5, leading=11.5)
    h1 = ParagraphStyle("h1", parent=n, fontName="DLH-Bold", fontSize=17, leading=21, textColor=violett, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=n, fontName="DLH-Bold", fontSize=13, leading=17, textColor=violett, spaceBefore=12, spaceAfter=5)
    h3 = ParagraphStyle("h3", parent=n, fontName="DLH-Bold", fontSize=10.5, leading=14, spaceBefore=8, spaceAfter=3)
    kasten = ParagraphStyle("kasten", parent=n, backColor=colors.HexColor("#f4eff7"), borderColor=hell, borderWidth=0.7,
                            borderPadding=7, spaceBefore=6, spaceAfter=10)
    th = ParagraphStyle("th", parent=klein, fontName="DLH-Bold", textColor=colors.white)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm,
                            title="Innovationsfonds-Check – Feedback", author="DLH-Innovationsfonds-Check (KI-gestützt)")
    breite = landscape(A4)[0] - 28 * mm
    s = []
    s.append(Paragraph("DLH-Innovationsfonds-Check – Feedback zur Selbstüberprüfung", h1))
    datum = datetime.date.today().strftime("%d.%m.%Y")
    kopf = f"Erstellt am {datum} · Erkanntes Formular: {_p(r['formular'])}"
    if r.get("projekttitel"):
        kopf += f" · Projekttitel: «{_p(r['projekttitel'])}»"
    s.append(Paragraph(kopf, klein))
    s.append(Paragraph("<b>Disclaimer</b><br/>" + "<br/>".join(_p(x) for x in DISCLAIMER_START), kasten))
    for h in r.get("hinweise", []):
        s.append(Paragraph(_p(h), n))

    def tabelle(kopfzeile, zeilen, spalten):
        daten = [[Paragraph(_p(k), th) for k in kopfzeile]] + zeilen
        tb = Table(daten, colWidths=[breite * x for x in spalten], repeatRows=1)
        tb.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), violett),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b396c4")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#faf7fb")]),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return tb

    if r.get("abbruch"):
        s.append(Paragraph("<b>" + _p(r["abbruch"]["text"]) + "</b>", n))
        s.append(Spacer(1, 6))
        zl = [[Paragraph(_p(z["erwartet"]), klein), Paragraph(_p(z["gefunden"]), klein), Paragraph(_p(z["problem"]), klein)]
              for z in r["abbruch"]["tabelle"]]
        s.append(tabelle(["Erwartet", "Gefunden", "Problem"], zl, [0.36, 0.36, 0.28]))
    else:
        s.append(Paragraph("TEIL A – Prüftabelle", h2))
        zl = []
        for z in r["zeilen"]:
            _, label, farbe = STATUS.get(z["status"], STATUS["nicht_beurteilbar"])
            ab = _p(z["abschnitt"]) + ("<br/><font size='7' color='#5b5b6b'>regelbasiert</font>" if z.get("quelle") == "lokal" else "")
            zl.append([Paragraph(ab, klein), Paragraph(f"<font color='{farbe}'><b>{_p(label)}</b></font>", klein),
                       Paragraph(_p(z["befund"]), klein), Paragraph(_p(z["todo"]), klein)])
        s.append(tabelle(["Abschnitt", "Status", "Befund", "To-do"], zl, [0.19, 0.09, 0.36, 0.36]))
        if r.get("messwerte"):
            s.append(Paragraph("Längenmessung", h3))
            for m in r["messwerte"]:
                marke = " – über der Vorgabe" if m["ueber"] else ""
                zusatz = f" {m['hinweis']}" if m.get("hinweis") else ""
                s.append(Paragraph(f"• <b>{_p(m['label'])}</b> ({_p(m['soll'])}): {_p(m['messtext'])}{_p(marke)}{_p(zusatz)}", n))
        s.append(Paragraph("TEIL B – Kurzbewertung", h2))
        s.append(Paragraph("Stärken", h3))
        for x in r["staerken"]:
            s.append(Paragraph("• " + _p(x), n))
        s.append(Paragraph("Mögliche kritische Rückfragen", h3))
        for x in r["rueckfragen"]:
            s.append(Paragraph("• " + _p(x), n))
        s.append(Paragraph("Fazit", h3))
        s.append(Paragraph(_p(r["fazit"]), n))
        if r.get("aehnliche_projekte"):
            s.append(Paragraph("Ähnliche bestehende Projekte", h2))
            s.append(Paragraph("Ähnlichkeit ist nicht negativ; die Hinweise dienen der Abgrenzung.", n))
            for a in r["aehnliche_projekte"]:
                s.append(Paragraph(
                    f"• <b>{_p(a['title'])}</b><br/>{_p(a['kurzbeschreibung'])}<br/>"
                    f"<link href='{_p(a['url'])}' color='#8a5da4'>{_p(a['url'])}</link><br/>"
                    f"<i>Ähnlichkeit:</i> {_p(a['begruendung'])}<br/><i>Mögliche Abgrenzungsfrage:</i> {_p(a['abgrenzungsfrage'])}", n))
                s.append(Spacer(1, 4))
    s.append(Paragraph("Beratung &amp; offizielle Anmeldung", h2))
    s.append(Paragraph("Falls Sie Rückfragen haben oder Ihren Antrag gezielt weiterentwickeln möchten:", n))
    s.append(Paragraph(f"• Beratungstermine: <link href='{LINK_TERMINE}' color='#8a5da4'>{LINK_TERMINE}</link>", n))
    s.append(Paragraph(f"• Offizielle Anmeldung und Prüfung über die DLH-Seite: <link href='{LINK_ANMELDUNG}' color='#8a5da4'>{LINK_ANMELDUNG}</link>", n))
    s.append(Paragraph("<b>Disclaimer</b><br/>" + "<br/>".join(_p(x) for x in DISCLAIMER_ENDE) + "<br/>Ende", kasten))

    def fuss(canvas, d):
        canvas.saveState()
        canvas.setFont("DLH", 7.5)
        canvas.setFillColor(colors.HexColor("#5b5b6b"))
        canvas.drawString(14 * mm, 8 * mm, "KI-gestützte, unverbindliche Selbstüberprüfung – ersetzt keine offizielle Prüfung.")
        canvas.drawRightString(landscape(A4)[0] - 14 * mm, 8 * mm, f"Seite {d.page}")
        canvas.setStrokeColor(orange)
        canvas.setLineWidth(1.2)
        canvas.line(14 * mm, landscape(A4)[1] - 9 * mm, landscape(A4)[0] - 14 * mm, landscape(A4)[1] - 9 * mm)
        canvas.restoreState()

    doc.build(s, onFirstPage=fuss, onLaterPages=fuss)
    return buf.getvalue()
