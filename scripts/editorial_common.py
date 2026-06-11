#!/usr/bin/env python3
"""Shared helpers for conservative editorial ingestion."""
from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from research_common import ROOT, sha256_text, slugify, utc_now

GENERIC_TERMS = {
    "hashtag", "urn", "https", "http", "query", "search", "result", "results",
    "captured", "linkedin", "post", "posts", "visible", "text", "source",
    "sources", "follow", "followers", "connection", "connect", "like", "comment",
    "share", "repost", "feed", "update", "activity", "profile", "company",
    "content", "metadata", "sanitized", "archive", "daily", "manual", "type",
    "status", "unknown", "none", "open", "questions", "book", "chapter",
    "the", "and", "for", "from", "this", "that", "these", "those", "then",
    "here", "what", "you", "your", "all", "one", "every", "everyone", "today",
    "days", "june", "jun", "visit", "follow", "edited", "multipost", "medium",
    "critical", "introduction", "building", "engineer", "engineering", "product",
    "design", "integration", "finance", "healthcare", "university", "speaker",
    "founder", "co-founder", "ceo", "cto", "phd", "inc", "b2b", "usa", "nyc",
    "associate", "professor", "software", "senior", "leader", "entrepreneur",
    "consultant", "developer", "researcher", "student", "engineer",
}

ENTITY_TYPE_ORDER = ["person", "company", "project", "tool", "concept", "framework", "publication", "unknown"]

ORG_SUFFIXES = ("Labs", "Research", "Systems", "Technologies", "Technology", "Inc", "Corp", "Corporation", "Company", "Group", "Institute")
PUBLICATION_WORDS = ("newsletter", "blog", "podcast", "magazine", "report", "paper", "journal")
FRAMEWORK_WORDS = ("framework", "architecture", "protocol", "standard", "model", "methodology", "pattern")
TOOL_WORDS = ("tool", "cli", "sdk", "api", "agent", "browser", "runtime", "platform")
PROJECT_WORDS = ("project", "repo", "repository", "product", "system", "app")


def ensure_editorial_schema(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS entity_sources (
          entity_id TEXT NOT NULL,
          source_id TEXT NOT NULL,
          mention_count INTEGER DEFAULT 1,
          first_seen_at TEXT,
          last_seen_at TEXT,
          sample TEXT,
          PRIMARY KEY (entity_id, source_id),
          FOREIGN KEY (entity_id) REFERENCES entities(id),
          FOREIGN KEY (source_id) REFERENCES sources(id)
        )
        """
    )
    claim_cols = {r[1] for r in con.execute("PRAGMA table_info(claims)")}
    if "evidence_strength" not in claim_cols:
        con.execute("ALTER TABLE claims ADD COLUMN evidence_strength TEXT DEFAULT 'weak'")
    if "source_count" not in claim_cols:
        con.execute("ALTER TABLE claims ADD COLUMN source_count INTEGER DEFAULT 0")
    if "updated_at" not in claim_cols:
        con.execute("ALTER TABLE claims ADD COLUMN updated_at TEXT")
    con.commit()


def clean_text(text: str, max_len: int = 30000) -> str:
    text = re.sub(r"https?://\S+", " ", text or "")
    text = re.sub(r"\burn:[\w:.-]+", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    return text.strip()[:max_len]


def source_text(row: sqlite3.Row, max_len: int = 30000) -> str:
    parts = [row["title"] or "", row["query"] or "", row["publisher"] or "", row["url"] or ""]
    archived = row["archived_path"] if "archived_path" in row.keys() else None
    if archived:
        path = ROOT / archived
        try:
            if path.exists() and path.suffix.lower() in {".md", ".txt"}:
                parts.append(path.read_text(encoding="utf-8", errors="ignore")[:max_len])
        except OSError:
            pass
    return clean_text("\n".join(parts), max_len=max_len)


def split_sentences(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [clean_text(c, 800) for c in chunks if len(clean_text(c, 800)) >= 50]


def normalize_entity_name(name: str) -> str:
    name = re.sub(r"^[#@]+", "", name or "")
    name = re.sub(r"\s+", " ", name).strip(" -–—:;,.()[]{}'\"")
    return name[:120]


def is_generic_entity(name: str) -> bool:
    n = normalize_entity_name(name)
    if len(n) < 3 or len(n) > 80:
        return True
    low = n.lower()
    if low in GENERIC_TERMS:
        return True
    tokens = [p for p in re.split(r"\W+", n) if p]
    low_tokens = [p.lower() for p in tokens]
    if low_tokens and low_tokens[0] in GENERIC_TERMS:
        # Avoid captured UI fragments such as "Follow Hermes Agent" or "This ...".
        return True
    if any(part in GENERIC_TERMS for part in low_tokens):
        # Allow meaningful phrases containing AI/agent terms, but block pure structural terms.
        meaningful = [p for p in tokens if p.lower() not in GENERIC_TERMS]
        if len(meaningful) == 0:
            return True
    if re.fullmatch(r"[0-9a-f]{8,}", low):
        return True
    if re.fullmatch(r"\d+", low):
        return True
    if low.startswith(("www", "com", "html")):
        return True
    return False


def candidate_entity_names(text: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    patterns = [
        r"\b(?:[A-Z][A-Za-z0-9&.+-]{2,}|AI|LLM|MCP)(?:\s+(?:[A-Z][A-Za-z0-9&.+-]{1,}|AI|LLM|MCP)){0,4}\b",
        r"\b(?:agentic|loop|context|memory|continual|autonomous|multi-agent|workflow|orchestration)\s+(?:[a-z][a-z0-9+-]+\s*){0,2}(?:architecture|engineering|agent|agents|workflow|memory|learning|system|framework|loop)\b",
        r"\b(?:[a-z][a-z0-9+-]+\s+){1,3}(?:architecture|engineering|framework|protocol|workflow|memory|agent|agents|loop)\b",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, flags=re.I if pat.startswith("\\b(?:agentic") or pat.startswith("\\b(?:[a-z]") else 0):
            name = normalize_entity_name(m.group(0))
            if not is_generic_entity(name):
                counts[name] += 1
    return counts


def classify_entity(name: str, context: str = "") -> str:
    n = normalize_entity_name(name)
    low = (n + " " + context[:500]).lower()
    if re.search(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b", n) and not any(w.lower() in low for w in ORG_SUFFIXES):
        if not any(w in low for w in ["architecture", "engineering", "framework", "agent"]):
            return "person"
    if any(w in low for w in FRAMEWORK_WORDS):
        return "framework" if "framework" in low else "concept"
    if n.lower() in {"loop engineering", "loop engineer", "context architecture", "memory architecture", "agentic ai", "continual learning", "autonomous coding agents", "ai coding agents"}:
        return "concept"
    if any(w in low for w in TOOL_WORDS):
        return "tool"
    if any(s.lower() in low for s in ORG_SUFFIXES) or re.search(r"\b(inc|corp|ltd|company|startup)\b", low):
        return "company"
    if any(w in low for w in PUBLICATION_WORDS):
        return "publication"
    if any(w in low for w in PROJECT_WORDS):
        return "project"
    if n.isupper() and 2 <= len(n) <= 8:
        return "tool"
    if n.lower() in {"openclaw", "hermes", "hermes agent"}:
        return "tool"
    if n.lower() in {"loop engineering", "loop engineer", "context architecture", "memory architecture"}:
        return "concept"
    return "unknown"


def entity_id_for(canonical_name: str) -> str:
    return "ent_" + sha256_text(canonical_name.lower())[:20]


def claim_id_for(claim_text: str) -> str:
    return "claim_" + sha256_text(claim_text.lower())[:20]


def evidence_strength(source_count: int, confidence: str) -> str:
    if confidence == "high" or source_count >= 3:
        return "strong"
    if confidence == "medium" or source_count >= 2:
        return "moderate"
    return "weak"


def confidence_from_source_count(source_count: int) -> str:
    if source_count >= 3:
        return "high"
    if source_count >= 2:
        return "medium"
    return "low"


PUBLISH_ENTITY_ALLOWLIST = {
    "loop engineering", "loop engineer", "hermes agent", "hermes", "openclaw",
    "nous research", "ai agents", "ai agent", "agentic ai", "ai coding agents",
    "autonomous coding agents", "continual learning", "context architecture",
    "memory architecture", "enterprise architecture", "claude code", "claude",
    "anthropic", "openai", "github", "microsoft", "google", "nvidia", "aws",
    "mcp", "rag", "langgraph", "xgboost", "hivemind", "outpost",
    "thenextgentechinsider.com", "python",
}


def is_publishable_entity(name: str, typ: str, source_count: int) -> bool:
    """Return whether an extracted entity is meaningful enough for a public page."""
    n = normalize_entity_name(name)
    low = n.lower()
    if is_generic_entity(n):
        return False
    if low in PUBLISH_ENTITY_ALLOWLIST:
        return True
    if source_count < 3:
        return False
    if typ == "unknown":
        return False
    tokens = [p for p in re.split(r"\W+", n) if p]
    if len(tokens) == 1 and not (n.isupper() and 2 <= len(n) <= 8):
        return False
    if tokens and tokens[0].lower() in GENERIC_TERMS:
        return False
    if any(t.lower() in GENERIC_TERMS for t in tokens):
        return False
    # Avoid UI/job-title fragments that repeat in LinkedIn result cards.
    low_words = set(t.lower() for t in tokens)
    if low_words & {"follow", "hiring", "speaker", "advisor", "author", "available", "creator", "head"}:
        return False
    return typ in {"company", "project", "tool", "concept", "framework", "publication", "person"}


def md_link(path: str, label: str | None = None) -> str:
    label = label or path
    return f"[{label}]({path})"
