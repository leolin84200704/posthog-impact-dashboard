"""Fetch PostHog merged PRs (last 90 days) via GraphQL search, chunked by week.

Search API caps at 1000 results per query; we chunk by 7-day window so each
chunk is well within the cap (PostHog merges ~30 PRs/day).
"""
from __future__ import annotations
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_OWNER = "PostHog"
REPO_NAME = "posthog"
WINDOW_DAYS = 90
CHUNK_DAYS = 7
PAGE_SIZE = 50

DATA_DIR = Path(__file__).parent.parent / "data" / "raw"
DATA_DIR.mkdir(parents=True, exist_ok=True)

NOW = datetime.now(timezone.utc)
SINCE = NOW - timedelta(days=WINDOW_DAYS)


def log(msg: str):
    print(msg, file=sys.stderr, flush=True)


SEARCH_QUERY = """
query($q:String!, $cursor:String, $first:Int!) {
  search(query:$q, type:ISSUE, first:$first, after:$cursor) {
    issueCount
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        number title url state merged mergedAt createdAt updatedAt
        additions deletions changedFiles
        author { login ... on User { databaseId } }
        labels(first:15) { nodes { name } }
        reviews(first:30) {
          nodes {
            author { login }
            state
            comments { totalCount }
          }
        }
        reviewRequests(first:10) {
          nodes { requestedReviewer { ... on User { login } } }
        }
        files(first:80) { nodes { path additions deletions } }
        closingIssuesReferences(first:5) {
          nodes { number title labels(first:5){ nodes { name } } }
        }
      }
    }
  }
}
"""


def search_chunk(start: datetime, end: datetime) -> list[dict]:
    q = f"repo:{REPO_OWNER}/{REPO_NAME} is:pr is:merged merged:{start.date()}..{end.date()}"
    items = []
    cursor = None
    page = 0
    while True:
        page += 1
        args = ["graphql", "-f", f"query={SEARCH_QUERY}", "-f", f"q={q}", "-F", f"first={PAGE_SIZE}"]
        if cursor:
            args += ["-f", f"cursor={cursor}"]
        result = subprocess.run(["gh", "api"] + args, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            log(f"  chunk {start.date()}..{end.date()} page {page} FAILED: {result.stderr[:300]}")
            # one retry
            result = subprocess.run(["gh", "api"] + args, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                raise RuntimeError(result.stderr[:300])
        data = json.loads(result.stdout)
        s = data["data"]["search"]
        nodes = [n for n in s["nodes"] if n]  # filter empties from non-PR types
        items.extend(nodes)
        log(f"  chunk {start.date()}..{end.date()} page {page}: +{len(nodes)} (cumulative {len(items)}/{s['issueCount']})")
        if not s["pageInfo"]["hasNextPage"]:
            break
        cursor = s["pageInfo"]["endCursor"]
        if page > 25:  # safety
            log(f"  chunk page cap hit, stopping")
            break
    return items


ISSUE_QUERY = """
query($q:String!, $cursor:String, $first:Int!) {
  search(query:$q, type:ISSUE, first:$first, after:$cursor) {
    issueCount
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on Issue {
        number title url state createdAt updatedAt closedAt
        author { login }
        authorAssociation
        labels(first:15) { nodes { name } }
        comments(first:20) {
          nodes { author { login } authorAssociation createdAt }
        }
      }
    }
  }
}
"""


def search_issues(start: datetime, end: datetime) -> list[dict]:
    q = f"repo:{REPO_OWNER}/{REPO_NAME} is:issue updated:{start.date()}..{end.date()}"
    items = []
    cursor = None
    page = 0
    while True:
        page += 1
        args = ["graphql", "-f", f"query={ISSUE_QUERY}", "-f", f"q={q}", "-F", f"first={PAGE_SIZE}"]
        if cursor:
            args += ["-f", f"cursor={cursor}"]
        result = subprocess.run(["gh", "api"] + args, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            log(f"  issues chunk {start.date()}..{end.date()} page {page} FAILED: {result.stderr[:300]}")
            result = subprocess.run(["gh", "api"] + args, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                raise RuntimeError(result.stderr[:300])
        data = json.loads(result.stdout)
        s = data["data"]["search"]
        nodes = [n for n in s["nodes"] if n]
        items.extend(nodes)
        log(f"  issues {start.date()}..{end.date()} page {page}: +{len(nodes)} (cum {len(items)}/{s['issueCount']})")
        if not s["pageInfo"]["hasNextPage"]:
            break
        cursor = s["pageInfo"]["endCursor"]
        if page > 25:
            break
    return items


def gh_api(args: list[str]):
    result = subprocess.run(["gh", "api"] + args, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[:500])
    return json.loads(result.stdout) if result.stdout.strip() else {}


def fetch_codeowners() -> str:
    import base64
    for path in [".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"]:
        try:
            data = gh_api([f"repos/{REPO_OWNER}/{REPO_NAME}/contents/{path}"])
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        except Exception:
            continue
    return ""


def fetch_org_members() -> list[str]:
    try:
        out = subprocess.run(
            ["gh", "api", f"orgs/{REPO_OWNER}/public_members", "--paginate"],
            capture_output=True, text=True, timeout=60,
        )
        if out.returncode == 0:
            members = json.loads(out.stdout)
            return [m["login"] for m in members] if isinstance(members, list) else []
    except Exception as e:
        log(f"  org members failed: {e}")
    return []


def main():
    log(f"Window: {SINCE.date()} to {NOW.date()}")
    log("Fetching merged PRs by week-chunks...")
    all_prs = []
    chunk_start = SINCE
    while chunk_start < NOW:
        chunk_end = min(chunk_start + timedelta(days=CHUNK_DAYS), NOW)
        chunk = search_chunk(chunk_start, chunk_end)
        all_prs.extend(chunk)
        # incremental save
        (DATA_DIR / "prs.json").write_text(json.dumps(all_prs))
        log(f"  -> total {len(all_prs)} PRs after chunk {chunk_start.date()}..{chunk_end.date()}")
        chunk_start = chunk_end + timedelta(seconds=1)

    log(f"DONE PRs: {len(all_prs)}")

    log("Fetching issues by week-chunks...")
    all_issues = []
    chunk_start = SINCE
    while chunk_start < NOW:
        chunk_end = min(chunk_start + timedelta(days=CHUNK_DAYS), NOW)
        chunk = search_issues(chunk_start, chunk_end)
        all_issues.extend(chunk)
        (DATA_DIR / "issues.json").write_text(json.dumps(all_issues))
        log(f"  -> total {len(all_issues)} issues after chunk {chunk_start.date()}..{chunk_end.date()}")
        chunk_start = chunk_end + timedelta(seconds=1)

    log(f"DONE issues: {len(all_issues)}")

    log("Fetching CODEOWNERS...")
    co = fetch_codeowners()
    (DATA_DIR / "codeowners.txt").write_text(co)
    log(f"CODEOWNERS: {len(co)} chars")

    log("Fetching org public members...")
    members = fetch_org_members()
    (DATA_DIR / "org_members.json").write_text(json.dumps(members))
    log(f"Public members: {len(members)}")

    meta = {
        "since": SINCE.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "now": NOW.isoformat(),
        "window_days": WINDOW_DAYS,
    }
    (DATA_DIR / "meta.json").write_text(json.dumps(meta))
    log("ALL DONE")


if __name__ == "__main__":
    main()
