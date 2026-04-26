"""Compute 4-pillar impact scores from raw GitHub data."""
from __future__ import annotations
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import networkx as nx
import pandas as pd

from filters import is_bot, is_revert, is_source_file, pr_is_substantive

DATA_DIR = Path(__file__).parent.parent / "data"
RAW = DATA_DIR / "raw"
OUT = DATA_DIR
OUT.mkdir(exist_ok=True)

EXPOSURE_DAYS = 30  # PRs need >=30d post-merge window for Engagement signal

CRITICAL_LABELS = {
    "bug", "p0", "p1", "incident", "critical", "security", "regression",
    "customer", "customer-impact", "kind/bug", "severity/high", "severity/critical",
    "high-priority", "blocker",
}
ARCH_LABELS = {
    "architecture", "refactor", "infrastructure", "schema", "migration",
    "platform", "design",
}


def parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def label_set(node: dict) -> set[str]:
    return {(n.get("name") or "").lower() for n in ((node.get("labels") or {}).get("nodes") or [])}


def is_architectural_pr(pr: dict) -> bool:
    """Heuristic: large refactor / new module / migration / many files."""
    labels = label_set(pr)
    if labels & ARCH_LABELS:
        return True
    if (pr.get("changedFiles") or 0) >= 30:
        return True
    files = [f.get("path", "") for f in ((pr.get("files") or {}).get("nodes") or [])]
    if any("/migrations/" in p or p.endswith(".sql") for p in files):
        return True
    return False


def pr_severity_weight(pr: dict) -> float:
    """Higher weight for PRs closing critical issues or carrying critical labels."""
    base = 1.0
    labels = label_set(pr)
    if labels & CRITICAL_LABELS:
        base += 1.0
    issues = ((pr.get("closingIssuesReferences") or {}).get("nodes")) or []
    for iss in issues:
        ilabels = {(n.get("name") or "").lower() for n in ((iss.get("labels") or {}).get("nodes") or [])}
        if ilabels & CRITICAL_LABELS:
            base += 1.5
            break
    return base


def pr_size_weight(pr: dict) -> float:
    """Log-capped size to avoid LoC gaming. Both LoC=1 and LoC=10000 land in same band-ish."""
    add = pr.get("additions") or 0
    dele = pr.get("deletions") or 0
    total = add + dele
    if total <= 0:
        return 0.5
    return min(3.0, math.log10(total + 1))


def normalize(series: pd.Series) -> pd.Series:
    """Min-max normalize to 0-100. Handles all-zero / all-equal."""
    if series.empty:
        return series
    lo, hi = series.min(), series.max()
    if hi == lo:
        return pd.Series(0.0, index=series.index)
    return (series - lo) / (hi - lo) * 100.0


def main():
    prs_raw = json.loads((RAW / "prs.json").read_text())
    try:
        issues_raw = json.loads((RAW / "issues.json").read_text())
    except FileNotFoundError:
        issues_raw = []
        print("WARN: issues.json missing, OSS-external signal will be zero")
    try:
        org_members = set(json.loads((RAW / "org_members.json").read_text()))
    except FileNotFoundError:
        org_members = set()
    try:
        codeowners_text = (RAW / "codeowners.txt").read_text()
    except FileNotFoundError:
        codeowners_text = ""
    try:
        meta = json.loads((RAW / "meta.json").read_text())
    except FileNotFoundError:
        meta = {"now": NOW.isoformat() if False else "2026-04-26T00:00:00Z",
                "since": "2026-01-26T00:00:00Z", "window_days": 90}
    now = parse_dt(meta["now"])
    since = parse_dt(meta["since"])

    # CODEOWNERS: parse path -> [teams/users]. PostHog uses team handles
    # (@PostHog/foo), so individual login matches are rare. We compute
    # de-facto ownership instead: an engineer is a "de-facto owner" of a path
    # prefix if they merged >=3 PRs touching files under that prefix in 90d.
    codeowner_paths: list[str] = []
    codeowner_logins: set[str] = set()
    for line in codeowners_text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if not parts:
            continue
        path_pat = parts[0].rstrip("/").lstrip("/")
        # crude: replace ** and * with empty for prefix match
        path_prefix = path_pat.replace("/**", "").replace("/*", "").replace("**", "")
        if path_prefix:
            codeowner_paths.append(path_prefix)
        for tok in parts[1:]:
            if tok.startswith("@") and "/" not in tok:
                codeowner_logins.add(tok[1:].lower())

    # Filter merged PRs in window, drop bots and non-substantive
    prs = []
    for pr in prs_raw:
        if not pr.get("merged"):
            continue
        merged_at = parse_dt(pr.get("mergedAt"))
        if not merged_at or merged_at < since or merged_at > now:
            continue
        author = pr.get("author") or {}
        login = author.get("login")
        if is_bot(login):
            continue
        if not pr_is_substantive(pr):
            continue
        prs.append(pr)

    print(f"Filtered PRs: {len(prs)} of {len(prs_raw)} (dropped bots/non-substantive/non-merged)")

    # Track all known engineer logins (PR authors + reviewers)
    engineers = set()
    for pr in prs:
        a = (pr.get("author") or {}).get("login")
        if a and not is_bot(a):
            engineers.add(a)
        for r in ((pr.get("reviews") or {}).get("nodes") or []):
            rl = (r.get("author") or {}).get("login")
            if rl and not is_bot(rl):
                engineers.add(rl)

    # ---- Build file -> sequence of (mergedAt, author, files_added_set) ----
    pr_records = []
    for pr in prs:
        files = [f.get("path", "") for f in ((pr.get("files") or {}).get("nodes") or [])]
        src_files = [p for p in files if is_source_file(p)]
        pr_records.append({
            "number": pr["number"],
            "author": (pr.get("author") or {}).get("login"),
            "mergedAt": parse_dt(pr["mergedAt"]),
            "files": src_files,
            "all_files": files,
            "additions": pr.get("additions") or 0,
            "deletions": pr.get("deletions") or 0,
            "labels": label_set(pr),
            "severity_w": pr_severity_weight(pr),
            "size_w": pr_size_weight(pr),
            "is_revert": is_revert(pr),
            "is_arch": is_architectural_pr(pr),
            "title": pr.get("title"),
            "url": pr.get("url"),
            "closing_issues": ((pr.get("closingIssuesReferences") or {}).get("nodes")) or [],
        })

    # Engagement: for each PR with >=30d exposure, % of its source files touched by later PRs
    cutoff_for_exposure = now - timedelta(days=EXPOSURE_DAYS)
    pr_records.sort(key=lambda r: r["mergedAt"])
    # For each PR, look at all later PRs and check file overlap
    for i, rec in enumerate(pr_records):
        if rec["mergedAt"] > cutoff_for_exposure or not rec["files"]:
            rec["engagement"] = None
            continue
        rec_files = set(rec["files"])
        touched = set()
        for later in pr_records[i + 1:]:
            if later["author"] == rec["author"]:
                continue  # only count touches by *others* to avoid self-cycle
            touched |= rec_files & set(later["files"])
        rec["engagement"] = len(touched) / len(rec_files)

    # ---- Per-author aggregation ----
    by_author = defaultdict(lambda: {
        "ship_pr_score": 0.0,
        "ship_engagement_vals": [],
        "ship_revert_count": 0,
        "ship_pr_count": 0,
        "ship_critical_pr_count": 0,
        "reach_arch_count": 0,
        "reach_critical_label_count": 0,
        "reach_codeowner": False,
        "evidence_prs": [],
    })

    for rec in pr_records:
        a = rec["author"]
        if not a:
            continue
        agg = by_author[a]
        weighted = rec["size_w"] * rec["severity_w"]
        if rec["is_revert"]:
            weighted *= 0.3
            agg["ship_revert_count"] += 1
        agg["ship_pr_score"] += weighted
        agg["ship_pr_count"] += 1
        if rec["engagement"] is not None:
            agg["ship_engagement_vals"].append(rec["engagement"])
        if rec["severity_w"] >= 2.0:
            agg["ship_critical_pr_count"] += 1
        if rec["is_arch"]:
            agg["reach_arch_count"] += 1
        if rec["labels"] & CRITICAL_LABELS:
            agg["reach_critical_label_count"] += 1
        agg["evidence_prs"].append({
            "number": rec["number"],
            "title": rec["title"],
            "url": rec["url"],
            "additions": rec["additions"],
            "deletions": rec["deletions"],
            "severity_w": rec["severity_w"],
            "is_arch": rec["is_arch"],
            "is_revert": rec["is_revert"],
            "engagement": rec["engagement"],
            "labels": list(rec["labels"]),
            "closing_issues": rec["closing_issues"],
            "merged_at": rec["mergedAt"].isoformat(),
        })

    for login in engineers:
        if login.lower() in codeowner_logins:
            by_author[login]["reach_codeowner"] = True

    # De-facto ownership: top contributors to each codeowned path get the flag
    if codeowner_paths:
        path_author_count = defaultdict(lambda: defaultdict(int))
        for rec in pr_records:
            for f in rec["files"]:
                for prefix in codeowner_paths:
                    if f.startswith(prefix):
                        path_author_count[prefix][rec["author"]] += 1
                        break
        for prefix, counts in path_author_count.items():
            # Top 2 contributors with >=3 PRs in that codeowned area = de-facto owner
            top = sorted(counts.items(), key=lambda x: -x[1])[:2]
            for author, n in top:
                if n >= 3 and author:
                    by_author[author]["reach_codeowner"] = True

    # ---- Lift: review graph + comments + async refs + OSS external ----
    # Review graph: edge from reviewer -> PR author, weighted by review count
    review_graph = nx.DiGraph()
    review_pushback_count = defaultdict(int)
    review_count_per_reviewer = defaultdict(int)
    deep_review_per_reviewer = defaultdict(int)

    for pr in prs:
        author = (pr.get("author") or {}).get("login")
        if not author or is_bot(author):
            continue
        reviews = (pr.get("reviews") or {}).get("nodes") or []
        for rv in reviews:
            r_login = (rv.get("author") or {}).get("login")
            if not r_login or is_bot(r_login) or r_login == author:
                continue
            comment_count = (rv.get("comments") or {}).get("totalCount") or 0
            review_count_per_reviewer[r_login] += 1
            if comment_count >= 3:
                deep_review_per_reviewer[r_login] += 1
            if rv.get("state") == "CHANGES_REQUESTED":
                review_pushback_count[r_login] += 1
            if review_graph.has_edge(r_login, author):
                review_graph[r_login][author]["weight"] += 1
            else:
                review_graph.add_edge(r_login, author, weight=1)

    # PageRank — directed weighted: who is reviewed-by-many. Higher = trusted reviewer.
    if review_graph.number_of_nodes() > 0:
        pagerank = nx.pagerank(review_graph, weight="weight")
    else:
        pagerank = {}

    # OSS external triage: comments by org/maintainer on issues from non-org-member authors
    oss_external_replies = defaultdict(int)
    oss_external_resolved = defaultdict(int)
    for iss in issues_raw:
        author = (iss.get("author") or {}).get("login")
        assoc = (iss.get("authorAssociation") or "").upper()
        if not author or is_bot(author):
            continue
        # External authors: those NOT MEMBER/OWNER/COLLABORATOR
        external_authors = assoc in ("NONE", "FIRST_TIME_CONTRIBUTOR", "FIRST_TIMER", "CONTRIBUTOR")
        if not external_authors:
            continue
        for c in ((iss.get("comments") or {}).get("nodes") or []):
            cl = (c.get("author") or {}).get("login")
            cassoc = (c.get("authorAssociation") or "").upper()
            if not cl or is_bot(cl):
                continue
            if cassoc in ("MEMBER", "OWNER", "COLLABORATOR"):
                oss_external_replies[cl] += 1
                if iss.get("state") == "CLOSED":
                    oss_external_resolved[cl] += 1

    # Async references: PR/issue body mentioning other people via #N — too expensive; approximate via review counts + closing issues
    # We'll use closing-issues as a proxy for "this person's work resolved formal issues"
    issues_resolved_per_author = defaultdict(int)
    for rec in pr_records:
        if rec["closing_issues"]:
            issues_resolved_per_author[rec["author"]] += len(rec["closing_issues"])

    # Steer: review pushback adopted (proxy = CHANGES_REQUESTED count).
    # Better proxy would be checking if subsequent commits followed within X days, but expensive.
    # Maintainer-initiated review request: count requestedReviewers per reviewer
    review_requests_received = defaultdict(int)
    for pr in prs:
        for req in ((pr.get("reviewRequests") or {}).get("nodes") or []):
            rr = (req.get("requestedReviewer") or {}).get("login")
            if rr and not is_bot(rr):
                review_requests_received[rr] += 1

    # ---- Assemble per-engineer scoreboard ----
    rows = []
    for login in engineers:
        agg = by_author[login]
        eng_vals = agg["ship_engagement_vals"]
        eng_avg = sum(eng_vals) / len(eng_vals) if eng_vals else None
        rows.append({
            "login": login,
            # Ship raw signals
            "ship_pr_score": agg["ship_pr_score"],
            "ship_pr_count": agg["ship_pr_count"],
            "ship_critical_pr_count": agg["ship_critical_pr_count"],
            "ship_revert_count": agg["ship_revert_count"],
            "ship_engagement_avg": eng_avg if eng_avg is not None else 0.0,
            "ship_engagement_n": len(eng_vals),
            # Lift raw signals
            "lift_pagerank": pagerank.get(login, 0.0),
            "lift_review_count": review_count_per_reviewer.get(login, 0),
            "lift_deep_review_count": deep_review_per_reviewer.get(login, 0),
            "lift_oss_replies": oss_external_replies.get(login, 0),
            "lift_oss_resolved": oss_external_resolved.get(login, 0),
            # Reach raw signals
            "reach_codeowner": agg["reach_codeowner"],
            "reach_arch_count": agg["reach_arch_count"],
            "reach_critical_label_count": agg["reach_critical_label_count"],
            "reach_issues_resolved": issues_resolved_per_author.get(login, 0),
            # Steer raw signals
            "steer_pushback_count": review_pushback_count.get(login, 0),
            "steer_review_requests_received": review_requests_received.get(login, 0),
            # Evidence
            "evidence_prs": agg["evidence_prs"],
        })

    df = pd.DataFrame(rows)
    if df.empty:
        print("No engineers found!")
        return

    # ---- Compute 4 normalized pillar scores (0-100) ----
    # Ship: blend of pr_score + engagement (boosted) - reverts
    df["ship_engagement_score"] = df["ship_engagement_avg"] * 100  # already 0-1
    ship_subtotal = (
        normalize(df["ship_pr_score"]) * 0.5
        + df["ship_engagement_score"] * 0.4  # already 0-100
        + normalize(df["ship_critical_pr_count"].astype(float)) * 0.2
        - normalize(df["ship_revert_count"].astype(float)) * 0.1
    )
    df["ship"] = normalize(ship_subtotal).round(1)

    lift_subtotal = (
        normalize(df["lift_pagerank"]) * 0.4
        + normalize(df["lift_deep_review_count"].astype(float)) * 0.3
        + normalize(df["lift_oss_replies"].astype(float)) * 0.2
        + normalize(df["lift_oss_resolved"].astype(float)) * 0.1
    )
    df["lift"] = normalize(lift_subtotal).round(1)

    reach_subtotal = (
        df["reach_codeowner"].astype(float) * 30  # binary boost
        + normalize(df["reach_arch_count"].astype(float)) * 0.4
        + normalize(df["reach_critical_label_count"].astype(float)) * 0.2
        + normalize(df["reach_issues_resolved"].astype(float)) * 0.2
    )
    df["reach"] = normalize(reach_subtotal).round(1)

    steer_subtotal = (
        normalize(df["steer_pushback_count"].astype(float)) * 0.5
        + normalize(df["steer_review_requests_received"].astype(float)) * 0.5
    )
    df["steer"] = normalize(steer_subtotal).round(1)

    # Composite for ordering only — surfaced as "Top 5 by composite" with caveat
    df["composite"] = (df["ship"] * 0.35 + df["lift"] * 0.30 + df["reach"] * 0.25 + df["steer"] * 0.10).round(1)

    df = df.sort_values("composite", ascending=False).reset_index(drop=True)

    # Save trimmed evidence (top 10 PRs per author by severity*size)
    def trim_evidence(prs_list):
        prs_list = sorted(
            prs_list,
            key=lambda p: (p["severity_w"], p["additions"] + p["deletions"], int(p.get("is_arch", False))),
            reverse=True,
        )
        return prs_list[:5]

    df["evidence_prs"] = df["evidence_prs"].apply(trim_evidence)

    out_path = OUT / "scores.json"
    out_path.write_text(df.to_json(orient="records"))
    print(f"Saved scores for {len(df)} engineers -> {out_path}")
    print("\nTop 10 by composite:")
    print(df[["login", "ship", "lift", "reach", "steer", "composite", "ship_pr_count"]].head(10).to_string(index=False))


if __name__ == "__main__":
    main()
