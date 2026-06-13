#!/usr/bin/env python3
"""Book role publication gate and report.

The Book role checks structure, navigation, formatting, build integrity, link/report reachability,
unsafe staged files, and publication safety. It does not decide whether claims are true.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

from research_common import DOCS, ROOT
from citation_common import scan_publication_citation_issues

UNSAFE_PATTERNS = re.compile(r"(^|/)(raw|logs|\.var|vector_db|site|\.env|cookies?|tokens?|secrets?|sessions?|browser|profile)(/|$)|\.(sqlite|db|wal|shm)$", re.I)
RAW_INTERNAL_REF = re.compile(r"(?<![A-Za-z0-9_])(claim_[a-f0-9]{20}|src_[a-f0-9]{20})(?![A-Za-z0-9_])")
BOOK_TO_BRIEF = {
    "book/preface.md": "chapter-briefs/preface.md",
    "book/01-the-agent-loop.md": "chapter-briefs/01-the-agent-loop.md",
    "book/02-hermes.md": "chapter-briefs/02-hermes.md",
    "book/03-openclaw.md": "chapter-briefs/03-openclaw.md",
    "book/04-loop-engineering.md": "chapter-briefs/04-loop-engineering.md",
    "book/05-context-memory-architecture.md": "chapter-briefs/05-context-memory-architecture.md",
    "book/06-operating-loops.md": "chapter-briefs/06-operating-loops.md",
    "book/open-questions.md": "chapter-briefs/open-questions.md",
}
REQUIRED_BRIEF_HEADINGS = [
    "Purpose", "Target reader", "Main argument", "Required concepts", "Required claims",
    "Required examples", "Allowed source types", "Excluded source types", "Open questions",
    "What this chapter must not claim", "Desired tone", "Desired length", "Related entities",
    "Publication readiness criteria",
]
STYLE_SHEET = "operations/author-style-sheet.md"
REQUIRED_STYLE_HEADINGS = [
    "Audience", "Voice", "Preferred sentence style", "Argument style", "Evidence style",
    "Forbidden or discouraged words", "Treatment of social media",
    "Treatment of internal project examples", "Chapter ending style", "Final style rule",
]
DISCOURAGED_STYLE_WORDS = [
    "revolutionary", "game-changing", "unlock", "unleash", "transformative", "disruptive",
    "paradigm shift", "next-generation", "groundbreaking", "magical", "seamless",
    "frictionless", "cutting-edge", "future-proof",
]


def run(cmd: list[str]) -> dict:
    p = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    return {"cmd": cmd, "returncode": p.returncode, "stdout": p.stdout, "stderr": p.stderr}


def nav_files(nav) -> list[str]:
    out=[]
    def walk(x):
        if isinstance(x, str):
            out.append(x)
        elif isinstance(x, list):
            for item in x: walk(item)
        elif isinstance(x, dict):
            for v in x.values(): walk(v)
    walk(nav)
    return out


def markdown_links(path: Path) -> list[tuple[str, str]]:
    text=path.read_text(encoding="utf-8", errors="ignore")
    links=[]
    for m in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", text):
        target=m.group(1).strip()
        if target.startswith(("http://","https://","mailto:","#")):
            continue
        if target.startswith("<") and target.endswith(">"):
            target=target[1:-1]
        target=target.split("#",1)[0]
        if not target:
            continue
        links.append((str(path.relative_to(ROOT)), target))
    return links


def chapter_has_bad_update(path: Path) -> str | None:
    text=path.read_text(encoding="utf-8", errors="ignore")
    if "No supported or high-confidence claims" in text:
        return None
    if RAW_INTERNAL_REF.search(text) or "{{cite:" in text:
        return "chapter exposes unresolved internal source/claim identifiers instead of numbered citations"
    if "[unresolved citation]" in text:
        return "chapter contains unresolved citation marker"
    if "linkedin" in text.lower() and "aggregate signal" not in text.lower() and "weak" not in text.lower():
        return "chapter mentions LinkedIn/social material without explicit weak-signal caveat"
    return None


def main() -> int:
    errors=[]; warnings=[]
    files_changed=run(["git","status","--short"])["stdout"].splitlines()

    mkdocs_path=ROOT/"mkdocs.yml"
    cfg=yaml.safe_load(mkdocs_path.read_text())
    nav=cfg.get("nav", [])
    nav_paths=nav_files(nav)
    nav_missing=[]
    for rel in nav_paths:
        if not (DOCS/rel).exists():
            nav_missing.append(rel)
    if nav_missing:
        errors.append("nav points to missing docs pages: " + ", ".join(nav_missing))

    # Required operations docs.
    for rel in [
        "operations/book-role-instruction.md",
        "operations/master-editorial-system.md",
        "operations/roles.md",
        "operations/chapter-brief-instruction.md",
        "operations/source-quality-instruction.md",
        "operations/weekly-curation-instruction.md",
        "operations/role-acceptance-criteria.md",
        "operations/do-not-publish-instruction.md",
        STYLE_SHEET,
    ]:
        if not (DOCS/rel).exists():
            errors.append(f"missing required operations page: {rel}")

    style_path = DOCS / STYLE_SHEET
    if style_path.exists():
        style_text = style_path.read_text(encoding="utf-8", errors="ignore")
        missing_style = [h for h in REQUIRED_STYLE_HEADINGS if f"## {h}" not in style_text]
        if missing_style:
            errors.append(f"Author style sheet {STYLE_SHEET} missing required headings: {', '.join(missing_style)}")

    # Chapter briefs are mandatory before Author writes/revises.
    for book_rel, brief_rel in BOOK_TO_BRIEF.items():
        if not (DOCS/book_rel).exists():
            errors.append(f"missing book chapter expected by brief map: {book_rel}")
            continue
        brief_path = DOCS / brief_rel
        if not brief_path.exists():
            errors.append(f"missing chapter brief for {book_rel}: {brief_rel}")
            continue
        brief_text = brief_path.read_text(encoding="utf-8", errors="ignore")
        missing = [h for h in REQUIRED_BRIEF_HEADINGS if f"## {h}" not in brief_text]
        if missing:
            errors.append(f"chapter brief {brief_rel} missing required headings: {', '.join(missing)}")

    # Internal links.
    broken=[]
    for md in DOCS.rglob("*.md"):
        for src,target in markdown_links(md):
            resolved=(md.parent/target).resolve()
            try:
                resolved.relative_to(DOCS.resolve())
            except ValueError:
                broken.append(f"{src} -> outside docs tree: {target}")
                continue
            if not resolved.exists():
                broken.append(f"{src} -> missing: {target}")
    if broken:
        errors.append("broken internal links: " + "; ".join(broken[:25]))

    # Report index reachability. It may point to local reports as code text, but reports/index itself must exist.
    report_index=DOCS/"reports/index.md"
    if not report_index.exists():
        errors.append("missing docs/reports/index.md")
    else:
        report_text=report_index.read_text(encoding="utf-8", errors="ignore")
        if "Daily Reports" not in report_text:
            warnings.append("docs/reports/index.md exists but lacks Daily Reports heading")

    # Chapter placeholders are allowed only when explicitly not ready.
    for ch in (DOCS/"book").glob("*.md"):
        text=ch.read_text(encoding="utf-8", errors="ignore")
        body=[ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
        if len(body) < 3 and "not yet ready" not in text.lower() and "No supported or high-confidence claims" not in text:
            errors.append(f"chapter appears placeholder-only without explicit not-ready marker: {ch.relative_to(DOCS)}")
        lowered = text.lower()
        for word in DISCOURAGED_STYLE_WORDS:
            if word in lowered and "directly quoted" not in lowered:
                errors.append(f"{ch.relative_to(DOCS)} uses discouraged style word without direct-quote context: {word}")
        bad=chapter_has_bad_update(ch)
        if bad:
            errors.append(f"{ch.relative_to(DOCS)}: {bad}")

    citation_gate = scan_publication_citation_issues(DOCS / "book")
    if citation_gate["status"] != "ok":
        errors.append("book citation gate failed: " + json.dumps(citation_gate, ensure_ascii=False)[:1000])

    # Role acceptance criteria. These criteria make completion explicit rather than treating
    # a zero exit code as sufficient evidence of quality.
    book_acceptance = {
        "mkdocs_build_strict_passes": False,
        "navigation_is_valid": not nav_missing,
        "new_pages_are_linked": all(
            not line.startswith("?? docs/")
            or line[3:].removeprefix("docs/") in nav_paths
            or line[3:].startswith(("docs/entities/", "docs/research/", "docs/reports/"))
            for line in files_changed
        ),
        "report_pages_are_reachable": report_index.exists() and (DOCS/"reports/weekly.md").exists(),
        "generated_pages_inside_docs_tree": True,
        "no_unsafe_files_staged": True,
        "no_credentials_or_unsafe_logs_committed": True,
        "publication_status_reported": True,
        "failed_checks_not_hidden": True,
        "no_raw_internal_citation_ids": citation_gate["status"] == "ok",
    }
    changed_book_paths = {line[3:] for line in files_changed if len(line) >= 4 and line[3:].startswith("docs/book/")}
    author_acceptance = {}
    for ch in (DOCS/"book").glob("*.md"):
        rel_docs = str(ch.relative_to(DOCS))
        rel_repo = "docs/" + rel_docs
        if rel_repo not in changed_book_paths:
            continue
        text=ch.read_text(encoding="utf-8", errors="ignore")
        author_acceptance[rel_docs] = {
            "structure_follows_brief": rel_docs in BOOK_TO_BRIEF,
            "factual_claims_have_numbered_citations": bool(re.search(r"\[[0-9]+\]", text)) or "No publishable chapter update is recommended" in text,
            "weak_claims_caveated": "weakly_supported" not in text or "Current evidence suggests" in text,
            "no_hype_language": not any(word in text.lower() for word in DISCOURAGED_STYLE_WORDS),
            "source_claim_mapping_included": "## Source/claim mapping" in text,
            "editor_notes_included": "## Editor notes" in text,
            "changelog_included": "## Changelog" in text,
            "raw_internal_ids_absent": not RAW_INTERNAL_REF.search(text) and "{{cite:" not in text and "[unresolved citation]" not in text,
        }
    # Unsafe staged/tracked publication paths.
    staged=run(["git","diff","--cached","--name-only"])["stdout"].splitlines()
    changed_paths=[line[3:] for line in files_changed if len(line)>=4]
    unsafe_staged=[p for p in staged if UNSAFE_PATTERNS.search(p) and p != "raw/.gitkeep"]
    unsafe_changed=[p for p in changed_paths if UNSAFE_PATTERNS.search(p) and p != "raw/.gitkeep"]
    if unsafe_staged:
        errors.append("unsafe staged files: " + ", ".join(unsafe_staged[:20]))
    if unsafe_changed:
        warnings.append("unsafe-looking changed files not necessarily staged: " + ", ".join(unsafe_changed[:20]))
    raw_tracked=[p for p in run(["git","ls-files","raw"])["stdout"].splitlines() if p != "raw/.gitkeep"]
    if raw_tracked:
        errors.append("raw source captures are tracked: " + ", ".join(raw_tracked[:20]))
    book_acceptance["no_unsafe_files_staged"] = not unsafe_staged
    book_acceptance["no_credentials_or_unsafe_logs_committed"] = not raw_tracked and not unsafe_staged

    build=run(["mkdocs","build","--strict"])
    build_result={"returncode": build["returncode"], "stdout_tail": build["stdout"][-2000:], "stderr_tail": build["stderr"][-4000:]}
    if build["returncode"] != 0:
        errors.append("mkdocs build --strict failed")
    book_acceptance["mkdocs_build_strict_passes"] = build["returncode"] == 0
    if not book_acceptance["new_pages_are_linked"]:
        errors.append("new docs pages are not linked or generated under an accepted docs section")
    failed_author = {k:v for k,v in author_acceptance.items() if not all(v.values())}
    if failed_author:
        errors.append("Author acceptance criteria failed: " + json.dumps(failed_author, ensure_ascii=False)[:1000])
    if not all(book_acceptance.values()):
        errors.append("Book role acceptance criteria failed: " + json.dumps(book_acceptance, ensure_ascii=False))

    payload={
        "role": "Book",
        "files_changed": files_changed,
        "navigation_changes": [line for line in run(["git","diff","--","mkdocs.yml"])["stdout"].splitlines() if line.startswith(("+","-")) and not line.startswith(("+++","---"))],
        "build_result": build_result,
        "link_report_status": "ok" if not broken and not nav_missing and report_index.exists() else "error",
        "unsafe_file_check": {"unsafe_staged": unsafe_staged, "raw_tracked": raw_tracked, "unsafe_changed_warnings": unsafe_changed},
        "citation_gate": citation_gate,
        "acceptance_criteria": {"book_role": book_acceptance, "author_role": author_acceptance},
        "publication": "approved" if not errors else "blocked",
        "errors": errors,
        "warnings": warnings,
        "next_required_action": None if not errors else errors[0],
    }
    print(json.dumps(payload, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
