import fnmatch
import logging
import re
import sqlite3
import subprocess
import threading
import time
import traceback
import urllib.error
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml
from flask import Flask, jsonify, render_template, request

HERE = Path(__file__).resolve().parent

DEFAULTS = {
    "port": 8400,
    "check_interval": 30,
    "check_timeout": 5,
    "retention_days": 30,
    "db": "data/warden.db",
    "failure_threshold": 3,
    "restart_cooldown": 300,
    "max_restart_backoff": 3600,
    "max_action_workers": 4,
}

TAIL_BYTES = 256 * 1024
TAIL_DEFAULT_LINES = 500
TAIL_MAX_LINES = 2000
SEARCH_BYTES = 50 * 1024 * 1024
MATCH_KEEP = 10_000
MATCH_RETURN = 500
LINE_TRUNCATE = 2_000

SCHEMA = """
CREATE TABLE IF NOT EXISTS deploys (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  service TEXT NOT NULL,
  commit_sha TEXT NOT NULL,
  started_at REAL NOT NULL,
  duration_s REAL,
  exit_code INTEGER,
  output TEXT
);
CREATE TABLE IF NOT EXISTS checks (
  service TEXT NOT NULL,
  ts REAL NOT NULL,
  ok INTEGER NOT NULL,
  latency_ms REAL,
  PRIMARY KEY (service, ts)
);
"""

state_lock = threading.Lock()
state = {
    "started_at": time.time(),
    "head": "",
    "origin_head": "",
    "synced": True,
    "dirty": False,
    "last_poll": None,
    "poll_interval": 60,
    "last_error": None,
}

running_actions = {}
running_lock = threading.Lock()
consec_lock = threading.Lock()
consec_fails = {}
watchdog_last_restart = {}
watchdog_backoff = {}
action_locks = {}
action_locks_guard = threading.Lock()

app = Flask(__name__)


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


def set_state(**kwargs):
    with state_lock:
        state.update(kwargs)


def snapshot_state():
    with state_lock:
        s = dict(state)
    with running_lock:
        s["current_actions"] = sorted(running_actions.values(), key=lambda a: a["since"])
    return s


def load_config():
    cfg = {**DEFAULTS, **yaml.safe_load((HERE / "config.yaml").read_text())}
    cfg["db_path"] = HERE / cfg["db"]
    return cfg


def db_exec(cfg, sql, params=()):
    conn = sqlite3.connect(cfg["db_path"], timeout=5)
    try:
        with conn:
            conn.execute(sql, params)
    finally:
        conn.close()


def db_query(cfg, sql, params=()):
    conn = sqlite3.connect(cfg["db_path"], timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def git(repo, *args):
    p = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout.strip()


def record_deploy(cfg, service, commit, started, duration, exit_code, output):
    db_exec(
        cfg,
        "INSERT INTO deploys (service, commit_sha, started_at, duration_s, exit_code, output)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (service, commit, started, duration, exit_code, output[-4096:]),
    )


def service_lock(name):
    with action_locks_guard:
        return action_locks.setdefault(name, threading.Lock())


def run_action(cfg, svc, commit):
    name = svc["name"]
    with service_lock(name):
        started = time.time()
        with running_lock:
            running_actions[name] = {"service": name, "command": svc["action"], "since": started}
        log(f"[{name}] running: {svc['action']}")
        try:
            p = subprocess.run(
                ["bash", "-c", svc["action"]],
                cwd=cfg["repo"],
                capture_output=True,
                text=True,
                timeout=cfg["action_timeout"],
            )
            output = (p.stdout + p.stderr).strip()
            if p.returncode == 0:
                log(f"[{name}] ok {p.stdout.strip()}")
            else:
                log(f"[{name}] ERROR exit {p.returncode}\n{output}")
            record_deploy(cfg, name, commit, started, time.time() - started, p.returncode, output)
        except subprocess.TimeoutExpired:
            log(f"[{name}] ERROR timed out after {cfg['action_timeout']}s")
            record_deploy(cfg, name, commit, started, time.time() - started, None,
                          f"timed out after {cfg['action_timeout']}s")
        finally:
            with running_lock:
                running_actions.pop(name, None)


def cycle(cfg):
    repo = Path(cfg["repo"])
    remote_ref = f"origin/{cfg['branch']}"
    git(repo, "fetch", "origin")
    head = git(repo, "rev-parse", "HEAD")
    remote = git(repo, "rev-parse", remote_ref)
    dirty = git(repo, "status", "--porcelain", "--untracked-files=no")
    set_state(head=head, origin_head=remote, synced=head == remote, dirty=bool(dirty),
              last_poll=time.time(), last_error=None)
    if head == remote:
        return
    if dirty:
        log(f"ERROR working tree dirty, skipping cycle:\n{dirty}")
        return
    changed = git(repo, "diff", "--name-only", head, remote).splitlines()
    git(repo, "merge", "--ff-only", remote_ref)
    log(f"merged {head[:8]} -> {remote[:8]}, {len(changed)} files changed")
    set_state(head=remote, synced=True)
    triggered = []
    for svc in cfg.get("tasks", []) + cfg.get("services", []):
        matched = [p for p in changed if any(fnmatch.fnmatch(p, pat) for pat in svc["paths"])]
        if matched:
            log(f"[{svc['name']}] changed: {', '.join(matched)}")
            triggered.append(svc)
    parallel = [s for s in triggered if not s.get("final")]
    if parallel:
        workers = min(cfg["max_action_workers"], len(parallel))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(lambda s: run_action(cfg, s, remote), parallel))
    for svc in triggered:
        if svc.get("final"):
            run_action(cfg, svc, remote)


def record_check(cfg, service, ok, latency_ms):
    db_exec(cfg, "INSERT OR REPLACE INTO checks (service, ts, ok, latency_ms) VALUES (?, ?, ?, ?)",
            (service, time.time(), ok, latency_ms))


def check_service(cfg, svc):
    name = svc["name"]
    start = time.monotonic()
    try:
        with urllib.request.urlopen(svc["health_url"], timeout=cfg["check_timeout"]) as resp:
            resp.read()
        record_check(cfg, name, 1, (time.monotonic() - start) * 1000)
        return True
    except urllib.error.HTTPError as e:
        record_check(cfg, name, 0, (time.monotonic() - start) * 1000)
        log(f"[{name}] health check failed: HTTP {e.code}")
        return False
    except Exception as e:
        record_check(cfg, name, 0, None)
        log(f"[{name}] health check error: {e}")
        return False


def watchdog_restart(cfg, svc, fails):
    name = svc["name"]
    if not svc.get("action"):
        return
    last = watchdog_last_restart.get(name, 0.0)
    cooldown = watchdog_backoff.get(name, cfg["restart_cooldown"])
    if time.time() - last < cooldown:
        return
    watchdog_last_restart[name] = time.time()
    watchdog_backoff[name] = min(cooldown * 2, cfg["max_restart_backoff"])
    log(f"[{name}] down for {fails} consecutive checks, restarting "
        f"(next allowed in {watchdog_backoff[name]}s)")
    threading.Thread(target=run_action, args=(cfg, svc, "watchdog"), daemon=True).start()


def health_round(cfg, services):
    for svc in services:
        name = svc["name"]
        ok = check_service(cfg, svc)
        with consec_lock:
            if ok:
                consec_fails[name] = 0
                watchdog_backoff[name] = cfg["restart_cooldown"]
            else:
                fails = consec_fails.get(name, 0) + 1
                consec_fails[name] = fails
        if not ok:
            with consec_lock:
                fails = consec_fails[name]
            if fails >= cfg["failure_threshold"]:
                watchdog_restart(cfg, svc, fails)
    cutoff = time.time() - cfg["retention_days"] * 86400
    db_exec(cfg, "DELETE FROM checks WHERE ts < ?", (cutoff,))
    db_exec(cfg, "DELETE FROM deploys WHERE started_at < ?", (cutoff,))


def health_loop(cfg):
    services = [s for s in cfg["services"] if s.get("health_url")]
    while True:
        start = time.monotonic()
        health_round(cfg, services)
        time.sleep(max(0, cfg["check_interval"] - (time.monotonic() - start)))


def warden_cfg():
    return app.config["WARDEN"]


def get_service(cfg, name):
    return next((s for s in cfg["services"] if s["name"] == name), None)


def read_window(path, size):
    with open(path, "rb") as f:
        f.seek(0, 2)
        end = f.tell()
        f.seek(max(0, end - size))
        return end, f.read()


def tail_file(path, max_lines):
    try:
        end, data = read_window(path, TAIL_BYTES)
    except OSError:
        return None
    lines = data.decode("utf-8", errors="replace").splitlines()
    if end > TAIL_BYTES and lines:
        lines = lines[1:]
    return [ln[:LINE_TRUNCATE] for ln in lines[-max_lines:]]


def search_file(path, rx):
    try:
        _, data = read_window(path, SEARCH_BYTES)
    except OSError:
        return {"name": Path(path).name, "exists": False, "total": 0, "matches": []}
    total = 0
    kept = deque(maxlen=MATCH_KEEP)
    for lineno, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
        if rx.search(line):
            total += 1
            kept.append({"line": lineno, "text": line[:LINE_TRUNCATE]})
    matches = list(kept)[-MATCH_RETURN:]
    matches.reverse()
    return {"name": Path(path).name, "exists": True, "total": total, "matches": matches}


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/state")
def api_state():
    cfg = warden_cfg()
    now = time.time()
    with consec_lock:
        consec = dict(consec_fails)
    uptime_rows = db_query(cfg, "SELECT service,"
                           " AVG(CASE WHEN ts >= ? THEN ok END) AS u24,"
                           " AVG(CASE WHEN ts >= ? THEN ok END) AS u7"
                           " FROM checks GROUP BY service",
                           (now - 86400, now - 7 * 86400))
    uptime = {r["service"]: (r["u24"], r["u7"]) for r in uptime_rows}
    services = []
    for svc in cfg["services"]:
        name = svc["name"]
        has_health = bool(svc.get("health_url"))
        check = db_query(cfg, "SELECT ts, ok, latency_ms FROM checks WHERE service = ?"
                         " ORDER BY ts DESC LIMIT 1", (name,))
        u24, u7 = uptime.get(name, (None, None))
        services.append({
            "name": name,
            "has_health": has_health,
            "has_logs": bool(svc.get("logs")),
            "last_check": dict(check[0]) if check else None,
            "consecutive_failures": consec.get(name, 0) if has_health else 0,
            "uptime_24h": u24,
            "uptime_7d": u7,
        })
    w = snapshot_state()
    w["uptime_s"] = time.time() - w["started_at"]
    return jsonify({"warden": w, "services": services,
                    "failure_threshold": cfg["failure_threshold"]})


@app.get("/api/history/<service>")
def api_history(service):
    cfg = warden_cfg()
    if get_service(cfg, service) is None:
        return jsonify({"error": "unknown service"}), 404
    hours = min(float(request.args.get("hours", 24)), 168)
    rows = db_query(cfg, "SELECT ts, ok, latency_ms FROM checks WHERE service = ? AND ts >= ?"
                    " ORDER BY ts ASC", (service, time.time() - hours * 3600))
    return jsonify({"checks": [dict(r) for r in rows]})


@app.get("/api/logs/<service>")
def api_logs(service):
    cfg = warden_cfg()
    svc = get_service(cfg, service)
    if svc is None:
        return jsonify({"error": "unknown service"}), 404
    raw = request.args.get("lines", "")
    try:
        lines = int(raw) if raw else TAIL_DEFAULT_LINES
    except ValueError:
        return jsonify({"error": f"invalid lines: {raw}"}), 500
    lines = max(1, min(lines, TAIL_MAX_LINES))
    files = [{"name": Path(p).name, "lines": tail_file(p, lines)} for p in svc.get("logs") or []]
    return jsonify({"files": files})


@app.get("/api/search/<service>")
def api_search(service):
    cfg = warden_cfg()
    svc = get_service(cfg, service)
    if svc is None:
        return jsonify({"error": "unknown service"}), 404
    q = request.args.get("q", "")
    if not q:
        return jsonify({"error": "missing q"}), 400
    try:
        rx = re.compile(q, re.IGNORECASE)
    except re.error as e:
        return jsonify({"error": f"invalid pattern: {e}"}), 400
    return jsonify({"files": [search_file(p, rx) for p in svc.get("logs") or []]})


def flask_loop(cfg):
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    app.run(host="127.0.0.1", port=cfg["port"], threaded=True, use_reloader=False)


def main():
    cfg = load_config()
    state["poll_interval"] = cfg["poll_interval"]
    cfg["db_path"].parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(cfg["db_path"])
    conn.executescript(SCHEMA)
    conn.close()
    app.config["WARDEN"] = cfg

    log(f"warden started, polling every {cfg['poll_interval']}s, dashboard on 127.0.0.1:{cfg['port']}")
    threading.Thread(target=health_loop, args=(cfg,), daemon=True).start()
    threading.Thread(target=flask_loop, args=(cfg,), daemon=True).start()
    while True:
        try:
            cycle(cfg)
        except Exception:
            err = traceback.format_exc()
            set_state(last_error=err)
            log("ERROR cycle failed:\n" + err)
        time.sleep(cfg["poll_interval"])


if __name__ == "__main__":
    main()
