# -*- coding: utf-8 -*-
"""
STPS Urnik - namizna aplikacija za urnik STPS Trbovlje.

Zazene majhen lokalni streznik (samo 127.0.0.1) in odpre okno Edge v nacinu
aplikacije. Streznik se sam ugasne, ko okno ni vec odprto.

Uporaba:
    pythonw stps_urnik.py          zagon aplikacije
    python  stps_urnik.py --no-browser --port 8777    razvojni zagon
    python  stps_urnik.py --danes  izpis danasnjega urnika v konzolo
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import urnik_source as src

APP_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(APP_DIR, "web")
DATA_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "STPS-Urnik")
CACHE_FILE = os.path.join(DATA_DIR, "cache.json")
INSTANCE_FILE = os.path.join(DATA_DIR, "instance.json")

# Kako dolgo je predpomnjen odgovor se svez (sekunde).
TTL = {"meta": 6 * 3600, "week": 300, "subs": 300}
# Po tolikem casu brez utripa iz okna se streznik ugasne.
IDLE_TIMEOUT = 90
# Zacetna velikost okna, dokler je vmesnik prvic ne izmeri.
DEFAULT_WINDOW = (900, 600)

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".ico": "image/x-icon",
    ".png": "image/png",
    ".svg": "image/svg+xml",
}


# ---------------------------------------------------------------------------
# Predpomnilnik na disku (deluje tudi kot vir podatkov brez povezave)
# ---------------------------------------------------------------------------

class Cache:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.data = {}
        try:
            with open(path, "r", encoding="utf-8") as fh:
                self.data = json.load(fh)
        except (OSError, ValueError):
            self.data = {}

    def get(self, key):
        with self.lock:
            return self.data.get(key)

    def _merged_with_disk(self):
        """
        Zapis zdruzimo s stanjem na disku, pri vsakem kljucu obvelja novejsi.
        Brez tega bi primerek, ki tece vzporedno, s svojo (starejso) sliko
        povozil tuje kljuce - npr. pravkar shranjeni oddelek.
        """
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                disk = json.load(fh)
        except (OSError, ValueError):
            return dict(self.data)
        if not isinstance(disk, dict):
            return dict(self.data)
        merged = dict(disk)
        for key, entry in self.data.items():
            old = merged.get(key)
            if (not isinstance(old, dict)
                    or not isinstance(entry, dict)
                    or entry.get("ts", 0) >= old.get("ts", 0)):
                merged[key] = entry
        return merged

    def put(self, key, payload):
        with self.lock:
            self.data[key] = {"ts": time.time(), "payload": payload}
            self.data = self._merged_with_disk()
            snapshot = json.dumps(self.data, ensure_ascii=False)
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(snapshot)
            os.replace(tmp, self.path)
        except OSError:
            pass  # predpomnilnik je le pripomocek, napake ne smejo ustaviti aplikacije


CACHE = Cache(CACHE_FILE)


def cached(key, kind, producer, fresh=False):
    """
    Vrne (podatki, meta). Ce vira ni mogoce doseci, vrne zadnje znane podatke
    in jih oznaci kot zastarele, da jih lahko vmesnik prikaze z opozorilom.
    """
    entry = CACHE.get(key)
    age = time.time() - entry["ts"] if entry else None
    if entry and not fresh and age < TTL[kind]:
        return entry["payload"], {"cached": True, "age": round(age), "stale": False}
    try:
        payload = producer()
    except src.SourceError as exc:
        if entry:
            return entry["payload"], {"cached": True, "age": round(age),
                                      "stale": True, "error": str(exc)}
        raise
    CACHE.put(key, payload)
    return payload, {"cached": False, "age": 0, "stale": False}


# ---------------------------------------------------------------------------
# Streznik
# ---------------------------------------------------------------------------

class App:
    def __init__(self):
        self.last_seen = time.time()
        self.stop = threading.Event()
        self._hash = None
        self._hash_ts = 0

    def hash(self):
        if not self._hash or time.time() - self._hash_ts > TTL["meta"]:
            entry = CACHE.get("hash")
            try:
                self._hash = src.discover_hash()
                CACHE.put("hash", self._hash)
            except src.SourceError:
                self._hash = (entry or {}).get("payload") or src.FALLBACK_HASH
            self._hash_ts = time.time()
        return self._hash

    def meta(self, fresh=False):
        return cached("meta", "meta", lambda: src.fetch_meta(self.hash()), fresh)

    def week(self, class_id, week, fresh=False):
        meta, _ = self.meta()
        key = "week:%s:%s" % (class_id, week)
        return cached(key, "week",
                      lambda: src.fetch_week(meta["schoolId"], class_id, week), fresh)

    def subs(self, day, fresh=False):
        return cached("subs:%s" % day, "subs",
                      lambda: src.fetch_substitutions(self.hash(), day), fresh)


APP = App()


def prefs():
    """Shranjene nastavitve vmesnika (zaenkrat le nazadnje izbrani oddelek)."""
    entry = CACHE.get("prefs")
    value = (entry or {}).get("payload")
    return value if isinstance(value, dict) else {}


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # Privzeto server_close() pocaka na niti obdelovalcev. Pri povezavah
    # keep-alive, ki jih zaprto okno pusti za sabo, taka nit visi in proces
    # nikoli ne konca - zato nanje ne cakamo.
    block_on_close = False


class Handler(BaseHTTPRequestHandler):
    server_version = "STPSUrnik/1.0"
    protocol_version = "HTTP/1.1"
    # Viseca povezava se sama sprosti, namesto da bi nit cakala v nedogled.
    timeout = 30

    def log_message(self, *_args):
        pass  # brez izpisa v konzolo

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def _json(self, payload, code=200):
        self._send(code, json.dumps(payload, ensure_ascii=False))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        fresh = query.get("fresh", ["0"])[0] == "1"
        APP.last_seen = time.time()

        try:
            if path.startswith("/api/"):
                return self._api(path, query, fresh)
        except src.SourceError as exc:
            return self._json({"error": str(exc)}, 503)
        except Exception as exc:  # noqa: BLE001 - vmesnik mora vedno dobiti odgovor
            return self._json({"error": "Napaka: %s" % exc}, 500)
        return self._static(path)

    # -- API ---------------------------------------------------------------

    def _api(self, path, query, fresh):
        if path == "/api/ping":
            return self._json({"ok": True, "now": datetime.now().isoformat(timespec="seconds")})

        if path == "/api/quit":
            APP.stop.set()
            return self._json({"ok": True})

        if path == "/api/size":
            # Vmesnik sporoci, kako veliko okno vsebina potrebuje; uporabimo
            # ga ob naslednjem zagonu, ko okna se ni mogoce izmeriti.
            try:
                size = (int(query["w"][0]), int(query["h"][0]))
            except (KeyError, IndexError, ValueError):
                return self._json({"error": "Neveljavna velikost."}, 400)
            if all(200 <= v <= 4000 for v in size):
                CACHE.put("winsize", {"w": size[0], "h": size[1]})
            return self._json({"ok": True})

        if path == "/api/prefs":
            # Nastavitve hranimo pri strezniku, ne v brskalniku: streznik ob
            # vsakem zagonu dobi druga vrata, s tem pa je drugo tudi izvorisce
            # strani in localStorage prejsnjega zagona ni vec viden.
            cls = query.get("class", [""])[0]
            if cls:
                if not cls.isdigit():
                    return self._json({"error": "Neveljaven oddelek."}, 400)
                CACHE.put("prefs", {"classId": cls})
            return self._json(prefs())

        if path == "/api/meta":
            data, info = APP.meta(fresh)
            out = dict(data)
            out["_meta"] = info
            out["today"] = date.today().isoformat()
            out["prefs"] = prefs()
            return self._json(out)

        if path == "/api/urnik":
            class_id = query.get("class", [""])[0]
            week = query.get("week", [""])[0]
            if not class_id.isdigit() or not week.isdigit():
                return self._json({"error": "Manjka oddelek ali teden."}, 400)
            data, info = APP.week(class_id, int(week), fresh)
            out = dict(data)
            out["_meta"] = info
            return self._json(out)

        if path == "/api/nadomescanja":
            day = query.get("date", [date.today().isoformat()])[0]
            try:
                datetime.strptime(day, "%Y-%m-%d")
            except ValueError:
                return self._json({"error": "Neveljaven datum."}, 400)
            data, info = APP.subs(day, fresh)
            out = dict(data)
            out["_meta"] = info
            return self._json(out)

        return self._json({"error": "Neznana pot."}, 404)

    # -- staticne datoteke -------------------------------------------------

    def _static(self, path):
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        full = os.path.normpath(os.path.join(WEB_DIR, rel))
        if not full.startswith(WEB_DIR) or not os.path.isfile(full):
            return self._send(404, "Ni najdeno", "text/plain; charset=utf-8")
        ctype = MIME.get(os.path.splitext(full)[1].lower(), "application/octet-stream")
        with open(full, "rb") as fh:
            return self._send(200, fh.read(), ctype)


# ---------------------------------------------------------------------------
# Zagon
# ---------------------------------------------------------------------------

def edge_path():
    for base in (os.environ.get("PROGRAMFILES(X86)"), os.environ.get("PROGRAMFILES"),
                 os.environ.get("LOCALAPPDATA")):
        if not base:
            continue
        candidate = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
        if os.path.isfile(candidate):
            return candidate
    return None


def window_size():
    """Velikost, ki jo je vmesnik ob zadnjem zagonu izmeril kot potrebno."""
    entry = CACHE.get("winsize")
    size = (entry or {}).get("payload") or {}
    try:
        w, h = int(size["w"]), int(size["h"])
    except (KeyError, TypeError, ValueError):
        return DEFAULT_WINDOW
    if 200 <= w <= 4000 and 200 <= h <= 4000:
        return w, h
    return DEFAULT_WINDOW


def open_window(url):
    exe = edge_path()
    if exe:
        try:
            subprocess.Popen(
                [exe, "--app=%s" % url, "--window-size=%d,%d" % window_size(),
                 "--disable-features=Translate,msEdgeSplitScreen"],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return
        except OSError:
            pass
    webbrowser.open(url)


def existing_instance():
    """Ce aplikacija ze tece, vrne njen naslov."""
    try:
        with open(INSTANCE_FILE, "r", encoding="utf-8") as fh:
            port = int(json.load(fh)["port"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.6) as sock:
            sock.sendall(b"GET /api/ping HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n")
            if b"200" in sock.recv(64):
                return "http://127.0.0.1:%d/" % port
    except OSError:
        pass
    return None


def clear_instance():
    """Zapis odstranimo le, ce je se vedno nas - sicer bi povozili drug primerek."""
    try:
        with open(INSTANCE_FILE, "r", encoding="utf-8") as fh:
            mine = json.load(fh).get("pid") == os.getpid()
        if mine:
            os.remove(INSTANCE_FILE)
    except (OSError, ValueError):
        pass


def watchdog(server, launch):
    while not APP.stop.wait(5):
        if time.time() - APP.last_seen > IDLE_TIMEOUT:
            break
    threading.Thread(target=server.shutdown, daemon=True).start()
    # Ce se zaustavitev iz kakrsnegakoli razloga zatakne, koncamo na trdo -
    # aplikacija v ozadju ne sme pustiti procesa za sabo.
    time.sleep(10)
    if launch:
        clear_instance()
    os._exit(0)


def run(port=0, launch=True):
    server = Server(("127.0.0.1", port), Handler)
    port = server.server_address[1]
    url = "http://127.0.0.1:%d/" % port

    os.makedirs(DATA_DIR, exist_ok=True)
    # Kot "tekoci primerek" se zabelezi samo pravi zagon z oknom; razvojni
    # zagon (--no-browser) sicer povozi zapis prave aplikacije.
    if launch:
        try:
            with open(INSTANCE_FILE, "w", encoding="utf-8") as fh:
                json.dump({"port": port, "pid": os.getpid()}, fh)
        except OSError:
            pass

    APP.last_seen = time.time()
    threading.Thread(target=watchdog, args=(server, launch), daemon=True).start()
    if launch:
        threading.Timer(0.25, open_window, args=(url,)).start()
    else:
        print("STPS Urnik tece na %s" % url)

    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if launch:
            clear_instance()


def print_today(wanted=""):
    """Kratek izpis v konzolo - uporabno za preverjanje brez okna."""
    meta, _ = APP.meta()
    names = {c["name"]: c["id"] for c in meta["classes"]}
    class_name = wanted if wanted in names else meta["classes"][0]["name"]
    grid, _ = APP.week(names[class_name], meta["currentWeek"])
    today = date.today().isoformat()
    if today not in [d["date"] for d in grid["days"]]:
        today = grid["days"][0]["date"]
    print("%s - %s" % (class_name, today))
    for hour in grid["hours"]:
        blocks = grid["cells"].get("%s|%d" % (today, hour["n"]))
        if not blocks:
            continue
        for b in blocks:
            tag = "[%s] " % b["statusCode"] if b["statusCode"] else ""
            print("  %-8s %-14s %s%s  %s  %s" % (
                hour["name"], hour["time"], tag, b["short"], b["teacher"], b["room"]))


def report_crash(exc_text):
    """Brez konzole (pythonw) je edini nacin, da uporabnik izve za napako, okno."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        log = os.path.join(DATA_DIR, "error.log")
        with open(log, "a", encoding="utf-8") as fh:
            fh.write("\n=== %s ===\n%s\n" % (datetime.now().isoformat(timespec="seconds"),
                                             exc_text))
    except OSError:
        log = "(dnevnika ni bilo mogoce zapisati)"
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None,
            "Urnika ni bilo mogoce zagnati.\n\n%s\n\nPodrobnosti: %s"
            % (exc_text.strip().splitlines()[-1], log),
            "STPŠ Urnik", 0x10)
    except Exception:  # noqa: BLE001
        sys.stderr.write(exc_text)


def main():
    ap = argparse.ArgumentParser(description="STPS Urnik")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--danes", nargs="?", const="", help="izpis danasnjega urnika")
    args, _ = ap.parse_known_args()

    if args.danes is not None:
        return print_today(args.danes)

    if not args.no_browser:
        running = existing_instance()
        if running:
            open_window(running)
            return
    run(port=args.port, launch=not args.no_browser)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001 - zadnja obramba, da napaka ni tiha
        import traceback
        report_crash(traceback.format_exc())
        sys.exit(1)
