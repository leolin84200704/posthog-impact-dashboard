"""Bot filtering (3-layer) and no-semantic PR filtering."""
from __future__ import annotations
import re
from pathlib import Path

KNOWN_BOT_PATTERNS = [
    r"^dependabot",
    r"^renovate",
    r"^github-actions",
    r"^codecov",
    r"^posthog-bot",
    r"^pre-commit-ci",
    r"^sentry-io",
    r"^greptile",
    r"^posthog-contributions-bot",
    r"^posthog-renovate",
    r"^imgbot",
    r"^allcontributors",
    r"^semantic-release",
    r"^codeflow",
    r"^stale",
    r"^netlify",
    r"^vercel",
    r"^cypress",
]

_BOT_REGEX = re.compile("|".join(KNOWN_BOT_PATTERNS), re.IGNORECASE)


def is_bot(login: str | None, user_type: str | None = None) -> bool:
    """Three-layer bot detection."""
    if login is None:
        return True
    if user_type and user_type.lower() == "bot":
        return True
    if login.endswith("[bot]") or "[bot]" in login.lower():
        return True
    if _BOT_REGEX.search(login):
        return True
    return False


# Files we consider definitely non-source (cosmetic / docs / fixtures)
NON_SOURCE_PATTERNS = [
    r"\.md$",
    r"\.mdx$",
    r"\.txt$",
    r"^LICENSE",
    r"^CHANGELOG",
    r"^\.github/",
    r"^docs/",
    r"\.lock$",
    r"package-lock\.json$",
    r"yarn\.lock$",
    r"pnpm-lock\.yaml$",
    r"poetry\.lock$",
    r"Pipfile\.lock$",
    r"\.snap$",
    r"snapshots?/",
    r"fixtures?/",
    r"__snapshots__/",
    r"test_data/",
    r"\.svg$",
    r"\.png$",
    r"\.jpg$",
    r"\.jpeg$",
    r"\.gif$",
    r"\.ico$",
    r"\.woff",
    r"\.ttf$",
]
_NON_SOURCE_REGEX = re.compile("|".join(NON_SOURCE_PATTERNS), re.IGNORECASE)

SOURCE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java",
    ".rb", ".sql", ".kt", ".swift", ".c", ".cpp", ".h", ".hpp",
    ".cs", ".scala", ".vue", ".svelte", ".sh", ".yaml", ".yml",
    ".tf", ".hcl", ".proto", ".graphql",
}


def is_source_file(path: str) -> bool:
    """Whether a file path is considered source code (not docs/fixtures/binary)."""
    if _NON_SOURCE_REGEX.search(path):
        return False
    ext = Path(path).suffix.lower()
    return ext in SOURCE_EXTENSIONS


def pr_is_substantive(pr: dict) -> bool:
    """Drop PRs with zero source-file changes.

    We approximate 'no semantic change' with 'no source-file additions/deletions'.
    A full AST-level diff is out of scope; this heuristic catches typo PRs,
    pure-doc PRs, lockfile bumps, and snapshot updates while preserving small
    but meaningful source edits (e.g. one-line critical bug fixes).
    """
    files = (pr.get("files") or {}).get("nodes") or []
    if not files:
        # No files data: keep, can't decide
        return True
    src_changes = 0
    for f in files:
        if is_source_file(f.get("path", "")):
            src_changes += (f.get("additions") or 0) + (f.get("deletions") or 0)
    return src_changes > 0


def is_revert(pr: dict) -> bool:
    title = (pr.get("title") or "").lower()
    if title.startswith("revert "):
        return True
    labels = [n.get("name", "").lower() for n in ((pr.get("labels") or {}).get("nodes") or [])]
    if any("revert" in l for l in labels):
        return True
    return False
