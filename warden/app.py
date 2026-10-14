import fnmatch
import subprocess
import time
import traceback
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


def git(repo, *args):
    p = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout.strip()


def run_action(cfg, svc):
    name = svc["name"]
    log(f"[{name}] running: {svc['action']}")
    try:
        p = subprocess.run(
            ["bash", "-c", svc["action"]],
            cwd=cfg["repo"],
            capture_output=True,
            text=True,
            timeout=cfg["action_timeout"],
        )
    except subprocess.TimeoutExpired:
        log(f"[{name}] ERROR timed out after {cfg['action_timeout']}s")
        return
    if p.returncode != 0:
        log(f"[{name}] ERROR exit {p.returncode}\n{p.stdout}\n{p.stderr}")
    else:
        log(f"[{name}] ok {p.stdout.strip()}")


def cycle(cfg):
    repo = Path(cfg["repo"])
    remote_ref = f"origin/{cfg['branch']}"
    git(repo, "fetch", "origin")
    head = git(repo, "rev-parse", "HEAD")
    remote = git(repo, "rev-parse", remote_ref)
    if head == remote:
        return
    dirty = git(repo, "status", "--porcelain", "--untracked-files=no")
    if dirty:
        log(f"ERROR working tree dirty, skipping cycle:\n{dirty}")
        return
    changed = git(repo, "diff", "--name-only", head, remote).splitlines()
    git(repo, "merge", "--ff-only", remote_ref)
    log(f"merged {head[:8]} -> {remote[:8]}, {len(changed)} files changed")
    for svc in cfg["services"]:
        matched = [p for p in changed if any(fnmatch.fnmatch(p, pat) for pat in svc["paths"])]
        if matched:
            log(f"[{svc['name']}] changed: {', '.join(matched)}")
            run_action(cfg, svc)


def main():
    cfg = yaml.safe_load((HERE / "config.yaml").read_text())
    log(f"warden started, polling every {cfg['poll_interval']}s")
    while True:
        try:
            cycle(cfg)
        except Exception:
            log("ERROR cycle failed:\n" + traceback.format_exc())
        time.sleep(cfg["poll_interval"])


if __name__ == "__main__":
    main()
