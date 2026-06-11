#!/usr/bin/env python3
"""Shared helpers for the Terefo Heal Reboa research book loop."""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DOCS = ROOT / "docs"
RAW = ROOT / "raw"
REPORTS = ROOT / "reports"
LOGS = ROOT / "logs"
RUNTIME = ROOT / ".var"
DB_PATH = RUNTIME / "book.sqlite"
SCHEMA_PATH = DATA / "schema.sql"
CONFIG_PATH = DATA / "search_config.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_id_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def slugify(value: str, max_len: int = 80) -> str:
    value = html.unescape(value or "").lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return (value[:max_len].strip("-") or "item")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text())


def ensure_dirs() -> None:
    for p in [DATA, DOCS, RAW / "web", RAW / "linkedin", REPORTS / "daily", REPORTS / "discovery", LOGS / "runs", LOGS / "runs" / "state", RUNTIME, ROOT / "vector_db"]:
        p.mkdir(parents=True, exist_ok=True)


def connect_db() -> sqlite3.Connection:
    ensure_dirs()
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db() -> None:
    ensure_dirs()
    with connect_db() as con:
        con.executescript(SCHEMA_PATH.read_text())


def upsert_source(con: sqlite3.Connection, **kw: Any) -> str:
    source_id = kw.get("id") or "src_" + sha256_text((kw.get("url") or "") + (kw.get("content_hash") or "") + (kw.get("captured_at") or ""))[:20]
    fields = {
        "id": source_id,
        "source_type": kw.get("source_type", "unknown"),
        "query": kw.get("query"),
        "url": kw.get("url"),
        "title": kw.get("title"),
        "publisher": kw.get("publisher"),
        "author": kw.get("author"),
        "published_at": kw.get("published_at"),
        "captured_at": kw.get("captured_at") or utc_now(),
        "archived_path": kw.get("archived_path"),
        "content_hash": kw.get("content_hash"),
        "reliability_tier": kw.get("reliability_tier", "unknown"),
        "visibility": kw.get("visibility", "public_or_search_result"),
        "run_id": kw.get("run_id"),
    }
    cols = list(fields)
    con.execute(
        f"INSERT OR IGNORE INTO sources ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
        [fields[c] for c in cols],
    )
    return source_id


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    tmp.replace(path)


def append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")


def read_pass(path: str) -> str:
    try:
        out = subprocess.check_output(["pass", "show", path], text=True, stderr=subprocess.DEVNULL)
        return out.splitlines()[0].strip()
    except Exception:
        return ""


def brave_key() -> str:
    return os.environ.get("BRAVE_SEARCH_API_KEY", "").strip() or read_pass("websearch/brave/api-key")


def safe_git_env() -> dict[str, str]:
    env = os.environ.copy()
    key = "/root/.ssh/id_ed25519_github_hermione_hermes"
    if Path(key).exists():
        env["GIT_SSH_COMMAND"] = f"ssh -o BatchMode=yes -o IdentitiesOnly=yes -i {key}"
    return env


def git_commit_push(message: str, paths: list[str]) -> dict[str, Any]:
    env = safe_git_env()
    status_before = subprocess.run(["git", "status", "--short"], cwd=ROOT, text=True, capture_output=True, env=env)
    unsafe = []
    for line in status_before.stdout.splitlines():
        p = line[3:] if len(line) > 3 else line
        low = p.lower()
        if any(x in low for x in [".env", "cookie", "token", "secret", "credential", ".var/", "browser-profile"]):
            unsafe.append(p)
    if unsafe:
        return {"committed": False, "pushed": False, "error": "unsafe files present", "unsafe": unsafe}
    subprocess.run(["git", "add", *paths], cwd=ROOT, check=False, env=env)
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT, env=env)
    if staged.returncode == 0:
        return {"committed": False, "pushed": False, "reason": "nothing staged"}
    subprocess.run(["git", "commit", "-m", message], cwd=ROOT, check=True, env=env)
    sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True, env=env).strip()
    push = subprocess.run(["git", "push", "origin", "main"], cwd=ROOT, text=True, capture_output=True, env=env)
    return {"committed": True, "pushed": push.returncode == 0, "commit_sha": sha, "push_stdout": push.stdout[-1000:], "push_stderr": push.stderr[-1000:]}


def strip_html(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    raw = re.sub(r"\s+", " ", raw)
    return raw.strip()


def extract_title(raw: str) -> str:
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
    return strip_html(m.group(1))[:300] if m else ""
