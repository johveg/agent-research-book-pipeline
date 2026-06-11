#!/usr/bin/env python3
"""Verify the editorial role instruction system is present and linked."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
INST = DOCS / "operations" / "instructions"
REQUIRED = [
    "master-editorial-system.md",
    "book-role.md",
    "author-role.md",
    "editor-role.md",
    "curator-function.md",
    "content-pipeline.md",
    "claim-status.md",
    "chapter-briefs.md",
    "author-style-sheet.md",
    "source-quality.md",
    "weekly-curation.md",
    "acceptance-criteria.md",
    "do-not-publish.md",
]


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    roles_path = DOCS / "operations" / "roles.md"
    mkdocs_path = ROOT / "mkdocs.yml"
    roles = roles_path.read_text(encoding="utf-8", errors="ignore") if roles_path.exists() else ""
    mkdocs = mkdocs_path.read_text(encoding="utf-8", errors="ignore") if mkdocs_path.exists() else ""

    for name in REQUIRED:
        path = INST / name
        if not path.exists():
            errors.append(f"missing instruction file: {path.relative_to(ROOT)}")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
        if not text:
            errors.append(f"empty instruction file: {path.relative_to(ROOT)}")
        if len(text) < 200:
            warnings.append(f"short instruction file: {path.relative_to(ROOT)}")
        rel = f"instructions/{name}"
        if rel not in roles:
            errors.append(f"roles.md does not link to {rel}")
        nav_rel = f"operations/instructions/{name}"
        if nav_rel not in mkdocs:
            errors.append(f"mkdocs.yml does not include {nav_rel}")

    all_text = "\n".join(
        (INST / name).read_text(encoding="utf-8", errors="ignore")
        for name in REQUIRED
        if (INST / name).exists()
    )
    joined = (roles + "\n" + all_text).lower()
    required_concepts = {
        "role boundaries are documented": ["role boundaries", "collector", "curator", "editor", "author", "book role"],
        "do-not-publish rules are documented": ["do not publish", "block chapter publication", "unsafe files"],
        "claim statuses are documented": ["candidate", "needs_review", "weakly_supported", "promoted_to_chapter"],
        "source quality scale is documented": ["a = primary", "b = credible", "c = named", "d = social", "e = duplicate"],
        "author style sheet exists": ["author style sheet", "evidence style"],
        "weekly curation process exists": ["weekly curation", "what did we learn"],
    }
    for label, needles in required_concepts.items():
        missing = [needle for needle in needles if needle not in joined]
        if missing:
            errors.append(f"{label}: missing {missing}")

    content_pipeline = (INST / "content-pipeline.md").read_text(encoding="utf-8", errors="ignore").lower() if (INST / "content-pipeline.md").exists() else ""
    if "planned" not in content_pipeline or "todo" not in content_pipeline:
        errors.append("content-pipeline.md must document planned/TODO work for non-implemented steps")

    result = {"status": "ok" if not errors else "error", "errors": errors, "warnings": warnings}
    print(result)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
