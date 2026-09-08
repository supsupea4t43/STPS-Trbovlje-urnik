# -*- coding: utf-8 -*-
"""
Pridobivanje in razclenjevanje urnikov STPS Trbovlje (eAsistent javni urnik).

Vir podatkov:
  1. https://www.stps-trbovlje.si/urniki/  -> iz strani preberemo eAsistentov hash sole
  2. https://urniki.easistent.com/urniki/<hash>
         -> id sole, seznam oddelkov, tekoci teden, seznam tednov
  3. .../urniki/ajax_urnik/<sola>/<razred>/0/0/0/<teden>/0/1
         -> urnik za izbrani teden (drobec HTML, polja locena z znakom 0x1F)
  4. .../nadomescanja/<hash>/<YYYY-MM-DD>/seznam
         -> dnevni seznam nadomescanj za celo solo (JSON)

Modul je namenoma odvisen samo od standardne knjiznice.
"""

import html as _html
import json
import re
import time
import urllib.error
import urllib.request

SCHOOL_PAGE = "https://www.stps-trbovlje.si/urniki/"
EA_BASE = "https://urniki.easistent.com"
# Zasilna vrednost, ce solske strani ni mogoce prebrati.
FALLBACK_HASH = "cc45c5d0d303f954588402a186f5cdba5edb51d6"
FALLBACK_SCHOOL_ID = "263"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) STPS-Urnik/1.0"
TIMEOUT = 25

# Stanja ure, kot jih eAsistent zapise v razred celice.
STATUS_LABELS = {
    "nadomescanje": ("NAD", "Nadomeščanje"),
    "zaposlitev": ("ZAP", "Zaposlitev"),
    "odpadla-ura": ("ODP", "Odpadla ura"),
    "ni-bilo-pouka": ("ODP", "Ni bilo pouka"),
    "dogodek": ("DOG", "Dogodek"),
}
STATUS_RE = re.compile(
    r"ednevnik-seznam_ur_teden-td-(nadomescanje|zaposlitev|odpadla-ura|ni-bilo-pouka|dogodek)\b"
)

# Kljucne besede na zacetku dostopnostnega opisa celice.
_SR_STATUS_WORDS = [
    ("nadomeščanje", "nadomescanje"),
    ("zaposlitev", "zaposlitev"),
    ("odpadla ura", "odpadla-ura"),
    ("ni bilo pouka", "ni-bilo-pouka"),
    ("dogodek", "dogodek"),
    ("šolski koledar", "dogodek"),
]

# Znacke ob uri so drugi, neodvisen vir istega podatka o stanju.
TAG_STATUS = {
    "substitution": "nadomescanje",
    "babysitting": "zaposlitev",
    "cancelled": "odpadla-ura",
    "no-lesson": "ni-bilo-pouka",
    "event": "dogodek",
}


class SourceError(RuntimeError):
    """Napaka pri branju ali razclenjevanju vira."""


def _get(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept-Language": "sl,en;q=0.8",
        "X-Requested-With": "XMLHttpRequest",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.URLError as exc:
        raise SourceError("Povezava ni uspela: %s" % exc) from exc
    except OSError as exc:
        raise SourceError("Napaka omrezja: %s" % exc) from exc
    return raw.decode("utf-8", "replace")


def _text(fragment):
    """HTML drobec -> ciste besede."""
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", fragment)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", _html.unescape(t))
    # Odstranjeni znacki pogosto pustita presledek pred locilom ("Kirn Samo , OPP").
    return re.sub(r"\s+([,.;:])", r"\1", t).strip()


# ---------------------------------------------------------------------------
# Metapodatki: hash sole, oddelki, tedni
# ---------------------------------------------------------------------------

def discover_hash():
    """Hash javnega urnika preberemo s solske strani, da prezivi menjavo hasha."""
    try:
        page = _get(SCHOOL_PAGE)
    except SourceError:
        return FALLBACK_HASH
    m = re.search(r"easistent\.com/urniki/([0-9a-f]{20,})", page)
    return m.group(1) if m else FALLBACK_HASH


def fetch_meta(hash_=None):
    """Seznam oddelkov, tekoci teden in seznam tednov solskega leta."""
    hash_ = hash_ or discover_hash()
    page = _get("%s/urniki/%s" % (EA_BASE, hash_))

    def var(name, default=""):
        m = re.search(r"var\s+%s\s*=\s*'([^']*)'" % name, page)
        return m.group(1) if m else default

    school_id = var("id_sola", FALLBACK_SCHOOL_ID)
    current_week = int(var("teden", "1") or 1)

    classes = []
    sel = re.search(r'<select[^>]+id="id_parameter".*?</select>', page, re.S)
    if sel:
        for m in re.finditer(r'<option\s+value="(\d+)"[^>]*>(.*?)</option>',
                             sel.group(0), re.S):
            classes.append({"id": m.group(1), "name": _text(m.group(2))})
    if not classes:
        raise SourceError("Seznama oddelkov ni bilo mogoce prebrati.")

    weeks = []
    for m in re.finditer(r'data-teden="(\d+)"[^>]*aria-label="Teden \d+:\s*(.*?)"', page):
        weeks.append({"n": int(m.group(1)),
                      "label": _html.unescape(m.group(2)).strip()})
    weeks.sort(key=lambda w: w["n"])

    name = ""
    m = re.search(r'<div class="bold">(.*?)</div>', page, re.S)
    if m:
        name = _text(m.group(1))

    return {
        "hash": hash_,
        "schoolId": school_id,
        "schoolName": name or "STPŠ Trbovlje",
        "classes": classes,
        "currentWeek": current_week,
        "weeks": weeks,
        "fetchedAt": time.time(),
    }


# ---------------------------------------------------------------------------
# Razclenjevanje urnika
# ---------------------------------------------------------------------------

def _parse_sr_segment(seg):
    """
    'nadomeščanje. Obdelava in prenos podatkov. profesor Samo Kirn. učilnica 107'
    -> (stanje, polno ime predmeta, profesor, ucilnica)

    Deluje tudi za razlicico z vejicami, ki jo eAsistent uporabi pri vec skupinah
    ('sklop 1: nadomeščanje, Športna vzgoja, profesor Anže Krajnc, učilnica T1').
    """
    s = seg.strip()
    status = None
    for word, key in _SR_STATUS_WORDS:
        m = re.match(r"%s\s*[.,]?\s*" % re.escape(word), s, re.I)
        if m:
            status = key
            s = s[m.end():]
            break

    room = teacher = None
    m = re.search(r"\bučilnica\s+(.+?)\s*$", s, re.I)
    if m:
        room = m.group(1).strip(" .,")
        s = s[:m.start()]
    m = re.search(r"\b(?:profesorica|profesor|učiteljica|učitelj)\s+(.+?)\s*$",
                  s.rstrip(" .,"), re.I)
    if m:
        teacher = m.group(1).strip(" .,")
        s = s[:m.start()]

    subject = s.strip(" .,")
    if subject.lower() in ("brez vsebine", ""):
        subject = ""
    return status, subject, teacher, room


def _split_sr(sr_text):
    """Dostopnostni opis celice -> seznam opisov, po en na skupino."""
    if not sr_text:
        return []
    body = re.sub(r"^.*?\bura\s+od\b.*?\.\s*", "", sr_text, count=1, flags=re.S)
    if not body.strip():
        body = sr_text
    if re.search(r"sklop\s*\d+\s*:", body, re.I):
        parts = re.split(r"sklop\s*\d+\s*:", body, flags=re.I)
        return [p.strip(" .;") for p in parts if p.strip(" .;")]
    return [body.strip()]


_BLOCK_RE = re.compile(
    r'<div\s+id="ednevnik-seznam_ur_teden-blok-wrap-[^"]*"\s+class="([^"]*)"\s*>')
_TITLE_RE = re.compile(r'<td[^>]*class="ednevnik-title"[^>]*>(.*?)</td>', re.S)
_SUBTITLE_RE = re.compile(r'<div class="ednevnik-subtitle">(.*?)</div>', re.S)
_TAG_RE = re.compile(
    r'<div[^>]*class="wl-tag-xs wl-tag-([a-z-]+)"[^>]*title="([^"]*)"[^>]*>(.*?)</div>', re.S)


def _parse_cell(chunk, sr_segments):
    """En <td> urnika -> seznam skupin (blokov) z vsemi podatki."""
    marks = [(m.start(), m.group(1)) for m in _BLOCK_RE.finditer(chunk)]
    blocks = []
    for i, (pos, cls) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(chunk)
        body = chunk[pos:end]

        m = _TITLE_RE.search(body)
        short = _text(m.group(1)) if m else ""
        m = _SUBTITLE_RE.search(body)
        sub = _text(m.group(1)) if m else ""

        ms = STATUS_RE.search(cls)
        status = ms.group(1) if ms else None

        tags, groups = [], None
        for mt in _TAG_RE.finditer(body):
            key = mt.group(1)
            label = _text(mt.group(3))
            if key == "more-events":
                try:
                    groups = int(label)
                except ValueError:
                    groups = None
                continue
            tags.append({"key": key,
                         "title": _html.unescape(mt.group(2)),
                         "label": label})

        seg = sr_segments[i] if i < len(sr_segments) else (
            sr_segments[0] if sr_segments else "")
        sr_status, subject_full, teacher, room = _parse_sr_segment(seg)
        if status is None and len(marks) == 1:
            status = sr_status

        # Dogodki nimajo podnaslova; sestavimo ga iz dostopnostnega opisa.
        if not sub:
            sub = ", ".join(x for x in (teacher, room) if x)

        code, label = STATUS_LABELS.get(status, (None, None))
        # Znacka je natancnejsa od razreda celice ("Šolski koledar" proti "Dogodek").
        status_tag = next((t for t in tags if t["key"] in TAG_STATUS), None)
        if status_tag:
            status = status or TAG_STATUS[status_tag["key"]]
            code = status_tag["label"] or code
            label = status_tag["title"] or label
        blocks.append({
            "short": short,
            "subject": subject_full or short,
            "teacher": teacher or "",
            "room": room or "",
            "sub": sub,
            "status": status,
            "statusCode": code,
            "statusLabel": label,
            "tags": tags,
            "groups": groups,
        })
    return blocks


def parse_grid(grid_html):
    """HTML tabele urnika -> {days, hours, cells}."""
    days = []
    for m in re.finditer(r'<th[^>]*id="urnik-dan-(\d{4}-\d{2}-\d{2})"(.*?)</th>',
                         grid_html, re.S):
        block = m.group(2)
        dm = re.search(r'<div class="days">(.*?)</div>', block, re.S)
        dd = re.search(r'<div class="date">(.*?)</div>', block, re.S)
        days.append({
            "date": m.group(1),
            "name": _text(dm.group(1)) if dm else "",
            "label": _text(dd.group(1)) if dd else "",
        })

    hours = []
    for m in re.finditer(r'<th[^>]*id="urnik-ura-(\d+)"(.*?)</th>', grid_html, re.S):
        block = m.group(2)
        nm = re.search(r'<div class="naziv-ure">(.*?)</div>', block, re.S)
        pm = re.search(r'<div class="potek-ure">(.*?)</div>', block, re.S)
        hours.append({
            "n": int(m.group(1)),
            "name": _text(nm.group(1)) if nm else "%s. ura" % m.group(1),
            "time": _text(pm.group(1)) if pm else "",
        })

    # Celic ne smemo rezati na </tr>: vsaka celica vsebuje se svojo notranjo
    # tabelo. Mejo postavimo na zacetek naslednje celice oz. glave vrstice.
    cells = {}
    chunks = re.split(
        r'(?=<td\b[^>]*\sid="ednevnik-seznam_ur_teden-td-\d+-\d{4}-\d{2}-\d{2}")'
        r'|(?=<th\b[^>]*\sscope="row")',
        grid_html)
    for chunk in chunks:
        m = re.match(
            r'<td\b[^>]*\sid="ednevnik-seznam_ur_teden-td-(\d+)-(\d{4}-\d{2}-\d{2})"',
            chunk)
        if not m:
            continue
        hour, date = int(m.group(1)), m.group(2)
        sm = re.search(r'<span class="public-urnik-sr-only">(.*?)</span>', chunk, re.S)
        sr = _text(sm.group(1)) if sm else ""
        blocks = _parse_cell(chunk, _split_sr(sr))
        if blocks:
            cells["%s|%d" % (date, hour)] = blocks

    return {"days": days, "hours": hours, "cells": cells}


def fetch_week(school_id, class_id, week):
    """Urnik enega oddelka za en teden."""
    url = "%s/urniki/ajax_urnik/%s/%s/0/0/0/%s/0/1" % (EA_BASE, school_id, class_id, week)
    raw = _get(url)
    parts = raw.split(chr(31))
    if len(parts) < 4:
        raise SourceError("Nepricakovan odgovor streznika urnikov.")
    grid = parse_grid(parts[3])
    grid.update({
        "week": int(parts[0] or week),
        "from": parts[1].strip(),
        "to": parts[2].strip(),
        "classId": str(class_id),
        "fetchedAt": time.time(),
    })
    return grid


# ---------------------------------------------------------------------------
# Nadomescanja za celo solo, po dnevih
# ---------------------------------------------------------------------------

def fetch_substitutions(hash_, date):
    """Seznam nadomescanj za posamezen dan (YYYY-MM-DD)."""
    raw = _get("%s/nadomescanja/%s/%s/seznam" % (EA_BASE, hash_, date))
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise SourceError("Neveljaven odgovor za nadomescanja.") from exc
    body = payload.get("data") or ""

    rows, current = [], ""
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if not tds:
            continue
        vals = [_text(t) for t in tds]
        if len(tds) >= 5:
            current = vals[0]
            hour, who, room, note = vals[1], vals[2], vals[3], vals[4]
        elif len(tds) == 4:
            hour, who, room, note = vals[0], vals[1], vals[2], vals[3]
        else:
            continue
        rows.append({
            "class": current,
            "hour": hour,
            "who": who,
            "room": "" if room == "/" else room,
            "note": "" if note == "/" else note,
            "cancelled": "odpade" in who.lower(),
        })
    return {"date": date, "rows": rows, "fetchedAt": time.time()}
