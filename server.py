"""Reppobjekt web server: serves the static site and proxies AI requests to Anthropic.

The API key is read from the ANTHROPIC_API_KEY environment variable and never sent to the browser.
Prompts are built here, so the endpoints cannot be used as an open relay to the API.
"""
import json
import os
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
PORT = int(os.environ.get("PORT", "8000"))

# Only these paths are served; everything else (server.py, .git, old/) is hidden.
STATIC_FILES = {"/index.html", "/README.md"}
STATIC_DIRS = ("/bilder/",)

CHAT_SYSTEM = (
    "Du er en norsk kundeservicebot for Reppobjekt — en markedsplass for reparasjonsobjekter. "
    "Svar kort (maks 2-3 setninger), på norsk, vennlig og hjelpsomt. Reppobjekt lar folk kjøpe og selge "
    "skadde biler, MC, båter, verktøy og elektronikk billig og reparere dem selv. "
    "Kontakt: samikjan1991@gmail.com. Svar bare på spørsmål om Reppobjekt, kjøp/salg og reparasjoner."
)

MAX_BODY = 16_000
MAX_MSG_CHARS = 1_000
MAX_HISTORY = 10
RATE_LIMIT = 20  # requests per IP per minute
_hits = defaultdict(deque)


def rate_limited(ip):
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        return True
    q.append(now)
    return False


def call_claude(messages, max_tokens, system=None):
    payload = {"model": MODEL, "max_tokens": max_tokens, "messages": messages}
    if system:
        payload["system"] = system
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode(),
        headers={
            "content-type": "application/json",
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as res:
        data = json.load(res)
    return "".join(b.get("text", "") for b in data.get("content", []))


def clean_history(raw):
    """Keep the last few user/assistant turns, trimmed, starting with a user turn."""
    msgs = []
    for m in raw[-MAX_HISTORY:] if isinstance(raw, list) else []:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant"):
            continue
        text = str(m.get("content", "")).strip()[:MAX_MSG_CHARS]
        if text:
            msgs.append({"role": m["role"], "content": text})
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    return msgs


def estimate_prompt(f):
    get = lambda k: str(f.get(k, "")).strip()[:300] or "ukjent"
    return f"""Du er en norsk bilmekaniker og prisekspert. Estimer reparasjonskostnaden for følgende objekt:
Merke: {get('merke')}
Modell: {get('modell')}
Årsmodell: {get('aar')}
Kilometerstand: {get('km')}
Feil/Problem: {get('feil')}

Svar BARE med et JSON-objekt (ingen markdown, ingen forklaring utenfor JSON):
{{
  "prisFra": 15000,
  "prisTil": 25000,
  "valuta": "NOK",
  "sammendrag": "Kort forklaring på 2-3 setninger om hva reparasjonen innebærer og hvorfor kostnaden er slik.",
  "tips": "Ett praktisk tips til kjøperen."
}}"""


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def client_ip(self):
        return self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()

    def send_json(self, status, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            return self.send_json(200, {"ok": True})
        if path == "/":
            self.path = "/index.html"
        elif not (path in STATIC_FILES or (path.startswith(STATIC_DIRS) and ".." not in path)):
            return self.send_error(404)
        super().do_GET()

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path not in ("/api/chat", "/api/estimate"):
            return self.send_error(404)
        if not API_KEY:
            return self.send_json(503, {"error": "AI er ikke konfigurert på serveren."})
        if rate_limited(self.client_ip()):
            return self.send_json(429, {"error": "For mange forespørsler. Vent litt."})
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            return self.send_json(400, {"error": "Ugyldig forespørsel."})
        try:
            body = json.loads(self.rfile.read(length))
        except ValueError:
            return self.send_json(400, {"error": "Ugyldig JSON."})

        try:
            if path == "/api/chat":
                msgs = clean_history(body.get("messages"))
                if not msgs or msgs[-1]["role"] != "user":
                    return self.send_json(400, {"error": "Mangler melding."})
                text = call_claude(msgs, 400, CHAT_SYSTEM)
            else:
                text = call_claude([{"role": "user", "content": estimate_prompt(body)}], 500)
        except urllib.error.HTTPError as e:
            self.log_error("Anthropic API error %s: %s", e.code, e.read()[:300])
            return self.send_json(502, {"error": "AI-tjenesten svarte med en feil."})
        except Exception as e:  # network errors, timeouts
            self.log_error("AI request failed: %r", e)
            return self.send_json(502, {"error": "Kunne ikke nå AI-tjenesten."})
        self.send_json(200, {"text": text})


if __name__ == "__main__":
    print(f"Reppobjekt serving on port {PORT} (model {MODEL}, AI {'on' if API_KEY else 'off'})")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
