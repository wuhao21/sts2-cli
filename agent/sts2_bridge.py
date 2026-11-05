#!/usr/bin/env python3
"""HTTP bridge for STS2 headless game. Lets Claude Code interact one command at a time.

Usage:
    python3 agent/sts2_bridge.py [port] [--compact] [--log FILE]
    python3 agent/sts2_bridge.py replay <logfile> [--until STEP] [--port PORT]

Examples:
    # Normal play with logging
    python3 agent/sts2_bridge.py 9876 --compact --log /tmp/game.jsonl

    # Replay a logged game up to step 42, then continue interactively
    python3 agent/sts2_bridge.py replay /tmp/game.jsonl --until 42 --port 9876
"""
import json, subprocess, os, sys, threading, re, time, shutil
from http.server import HTTPServer, BaseHTTPRequestHandler

# --- Arg parsing ---
COMPACT = "--compact" in sys.argv
REPLAY_MODE = len(sys.argv) > 1 and sys.argv[1] == "replay"
LOG_FILE = None
REPLAY_FILE = None
REPLAY_UNTIL = None
PORT = 9876

if REPLAY_MODE:
    # replay <logfile> [--until STEP] [--port PORT]
    REPLAY_FILE = sys.argv[2] if len(sys.argv) > 2 else None
    for i, a in enumerate(sys.argv):
        if a == "--until" and i + 1 < len(sys.argv): REPLAY_UNTIL = int(sys.argv[i + 1])
        if a == "--port" and i + 1 < len(sys.argv): PORT = int(sys.argv[i + 1])
else:
    filtered = [a for a in sys.argv[1:] if not a.startswith("--")]
    PORT = int(filtered[0]) if filtered else 9876
    for i, a in enumerate(sys.argv):
        if a == "--log" and i + 1 < len(sys.argv): LOG_FILE = sys.argv[i + 1]

# --- JSON helpers ---
_STRIP_KEYS = {"description", "after_upgrade", "enchantment", "enchantment_amount",
               "affliction", "affliction_amount", "id", "draw_pile_count",
               "discard_pile_count", "upgraded", "act_name"}


def compact_json(obj, depth=0):
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            if k in _STRIP_KEYS: continue
            if k == "context" and obj.get("decision") == "combat_play": continue
            if k == "player" and obj.get("decision") == "combat_play":
                if isinstance(v, dict):
                    potions = v.get("potions")
                    if potions: result["potions"] = compact_json(potions, depth + 1)
                continue
            if k == "relics" and isinstance(v, list) and depth > 0:
                result[k] = [compact_json(r, depth + 1) if isinstance(r, dict) else r for r in v]
                continue
            result[k] = compact_json(v, depth + 1)
        return result
    if isinstance(obj, list): return [compact_json(v, depth + 1) for v in obj]
    return obj


def sanitize_json(obj):
    if isinstance(obj, str): return re.sub(r'[\x00-\x1f\x7f]', '', obj)
    if isinstance(obj, dict): return {k: sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, list): return [sanitize_json(v) for v in obj]
    return obj


# --- Game process ---
class Game:
    def __init__(self):
        self.lock = threading.Lock()
        self.step = 0
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        os.environ.setdefault("STS2_GAME_DIR", os.path.join(root, "lib"))
        dotnet = shutil.which("dotnet") or os.path.expanduser("~/.dotnet-arm64/dotnet")
        self.proc = subprocess.Popen(
            [dotnet, "run", "--no-build",
             "--project", os.path.join(root, "src", "Sts2Headless", "Sts2Headless.csproj")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, cwd=root)
        def _forward_stderr():
            for line in self.proc.stderr:
                print(f"[GAME] {line.rstrip()}", file=sys.stderr)
        threading.Thread(target=_forward_stderr, daemon=True).start()
        ready = self._read()
        print(f"Game ready: {ready}", file=sys.stderr)

    def _read(self):
        while True:
            line = self.proc.stdout.readline().strip()
            if not line:
                return {"type": "error", "message": "EOF - game process ended"}
            if line.startswith("{"):
                return json.loads(line)

    def send(self, cmd):
        with self.lock:
            self.step += 1
            self.proc.stdin.write(json.dumps(cmd) + "\n")
            self.proc.stdin.flush()
            resp = self._read()
            return self.step, resp


# --- Logging ---
_log_fh = None

def log_entry(step, request, response):
    global _log_fh
    if _log_fh is None and LOG_FILE:
        _log_fh = open(LOG_FILE, "w")
    if _log_fh:
        entry = {"step": step, "ts": time.time(), "req": request, "resp": response}
        _log_fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        _log_fh.flush()


# --- Replay mode ---
def do_replay():
    if not REPLAY_FILE:
        print("Usage: sts2_bridge.py replay <logfile> [--until STEP] [--port PORT]", file=sys.stderr)
        sys.exit(1)

    print(f"Replaying {REPLAY_FILE} until step {REPLAY_UNTIL or 'end'}...", file=sys.stderr)
    game = Game()

    with open(REPLAY_FILE) as f:
        entries = [json.loads(line) for line in f if line.strip()]

    replayed = 0
    last_resp = None
    for entry in entries:
        step = entry["step"]
        if REPLAY_UNTIL and step > REPLAY_UNTIL:
            break
        req = entry["req"]
        step_num, resp = game.send(req)
        resp = sanitize_json(resp)
        last_resp = resp
        replayed += 1

        dec = resp.get("decision", resp.get("type", "?"))
        hp = resp.get("hp", resp.get("player", {}).get("hp", "")) if isinstance(resp, dict) else ""
        print(f"  Step {step}: {req.get('cmd','?')}/{req.get('action','')} → {dec} (hp={hp})", file=sys.stderr)

    print(f"\nReplayed {replayed} steps. Game is at step {replayed}.", file=sys.stderr)
    if last_resp:
        dec = last_resp.get("decision", last_resp.get("type", "?"))
        print(f"Current state: {dec}", file=sys.stderr)
        # Print the full current state for debugging
        print(json.dumps(last_resp, ensure_ascii=False, indent=2)[:2000], file=sys.stderr)

    # Now start interactive bridge from this point
    print(f"\nStarting interactive bridge on port {PORT}...", file=sys.stderr)

    class ReplayHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            step_num, result = game.send(data)
            result = sanitize_json(result)
            if COMPACT: result = compact_json(result)
            body = json.dumps(result, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', len(body))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, fmt, *args): pass

    HTTPServer(('127.0.0.1', PORT), ReplayHandler).serve_forever()


# --- Normal mode ---
if REPLAY_MODE:
    do_replay()
    sys.exit(0)

game = Game()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        step, result = game.send(data)
        raw_result = sanitize_json(result)
        # Log FULL response (before compact) for replay
        log_entry(step, data, raw_result)
        # Apply compact for client
        client_result = compact_json(raw_result) if COMPACT else raw_result
        body = json.dumps(client_result, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # silent


mode = "compact" if COMPACT else "full"
log_info = f", logging to {LOG_FILE}" if LOG_FILE else ""
print(f"STS2 bridge on port {PORT} (mode={mode}{log_info})", file=sys.stderr)
HTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
