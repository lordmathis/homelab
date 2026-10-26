import fnmatch
import logging
import sqlite3
import subprocess
import threading
import time
import traceback
import urllib.error
import urllib.request
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
}

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
    "current_action": None,
}

app = Flask(__name__)


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


def set_state(**kwargs):
    with state_lock:
        state.update(kwargs)


def snapshot_state():
    with state_lock:
        return dict(state)


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


def run_action(cfg, svc, commit):
    name = svc["name"]
    started = time.time()
    set_state(current_action={"service": name, "command": svc["action"], "since": started})
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
        set_state(current_action=None)


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
    for svc in cfg["services"]:
        matched = [p for p in changed if any(fnmatch.fnmatch(p, pat) for pat in svc["paths"])]
        if matched:
            log(f"[{svc['name']}] changed: {', '.join(matched)}")
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
    except urllib.error.HTTPError as e:
        record_check(cfg, name, 0, (time.monotonic() - start) * 1000)
        log(f"[{name}] health check failed: HTTP {e.code}")
    except Exception as e:
        record_check(cfg, name, 0, None)
        log(f"[{name}] health check error: {e}")


def health_loop(cfg):
    services = [s for s in cfg["services"] if s.get("health_url")]
    while True:
        start = time.monotonic()
        for svc in services:
            check_service(cfg, svc)
        db_exec(cfg, "DELETE FROM checks WHERE ts < ?",
                (time.time() - cfg["retention_days"] * 86400,))
        time.sleep(max(0, cfg["check_interval"] - (time.monotonic() - start)))


def warden_cfg():
    return app.config["WARDEN"]


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/state")
def api_state():
    cfg = warden_cfg()
    services = []
    for svc in cfg["services"]:
        name = svc["name"]
        check = db_query(cfg, "SELECT ts, ok, latency_ms FROM checks WHERE service = ?"
                         " ORDER BY ts DESC LIMIT 1", (name,))
        deploy = db_query(cfg, 'SELECT commit_sha AS "commit", started_at, duration_s, exit_code FROM deploys'
                          " WHERE service = ? ORDER BY id DESC LIMIT 1", (name,))
        services.append({
            "name": name,
            "has_health": bool(svc.get("health_url")),
            "last_check": dict(check[0]) if check else None,
            "last_deploy": dict(deploy[0]) if deploy else None,
        })
    w = snapshot_state()
    w["uptime_s"] = time.time() - w["started_at"]
    return jsonify({"warden": w, "services": services})


@app.get("/api/deploys")
def api_deploys():
    cfg = warden_cfg()
    limit = min(int(request.args.get("limit", 50)), 200)
    rows = db_query(cfg, 'SELECT service, commit_sha AS "commit", started_at, duration_s, exit_code, output'
                    " FROM deploys ORDER BY id DESC LIMIT ?", (limit,))
    return jsonify({"deploys": [dict(r) for r in rows]})


@app.get("/api/history/<service>")
def api_history(service):
    cfg = warden_cfg()
    if service not in [s["name"] for s in cfg["services"]]:
        return jsonify({"error": "unknown service"}), 404
    hours = min(float(request.args.get("hours", 24)), 168)
    rows = db_query(cfg, "SELECT ts, ok, latency_ms FROM checks WHERE service = ? AND ts >= ?"
                    " ORDER BY ts ASC", (service, time.time() - hours * 3600))
    return jsonify({"checks": [dict(r) for r in rows]})


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
