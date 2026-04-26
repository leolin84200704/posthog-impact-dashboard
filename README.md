# PostHog Engineering Impact Dashboard

Take-home for Workweave. Identifies the top 5 most impactful engineers in PostHog/posthog over the last 90 days using a 4-pillar framework.

## Approach

Instead of a single composite "impact score", we measure four orthogonal pillars so different *kinds* of contribution stay visible:

| Pillar | What it captures |
|---|---|
| **Ship** | What landed AND stayed in the live cycle. Weighted by severity + size (capped to defeat LoC gaming). Engagement = % of source files later PRs touched (only PRs with ≥30d post-merge exposure counted). |
| **Lift** | Sync + async leverage. Review-graph PageRank, deep reviews, and **OSS-external triage** — replies to non-org-member issues + their resolution rate. PostHog is open-source; this work is a big chunk of real impact and would otherwise be invisible. |
| **Reach** | Depth in critical subsystems: CODEOWNERS membership, architectural changes (new modules, migrations, large refactors), maintainer-applied critical labels, formally closed issues. |
| **Steer** | Judgment & direction-setting. **Marked weak signal** because most of it (design docs, RFCs, what-they-prevented) lives outside public GitHub. Proxied via review push-back and maintainer-initiated review requests. |

The dashboard treats the composite as an ordering tool, not a verdict — every Top 5 card opens an Evidence Panel with PR links and signal tags so a reader can validate.

## Filters

- **Bots** removed via 3-layer check: `user.type == "Bot"`, `[bot]` suffix, known-pattern list (dependabot, renovate, github-actions, etc.).
- **No-semantic PRs** dropped: PRs where source-file additions/deletions = 0 (pure docs / lockfile / snapshot bumps). Small but substantive PRs are preserved — a one-line critical bug fix still counts.
- **Non-merged PRs** excluded from Ship.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python src/fetch.py    # ~5 min for 90d of PostHog
python src/analyze.py
streamlit run app.py
```

## Acknowledged blind spots

- **Steer** is structurally under-observed in public data.
- 90-day window is too short for true code longevity; Engagement is a proxy.
- Refactors that close few formal issues are systematically under-credited; the per-pillar leaderboards exist partly to compensate.
- We do not call any LLM to generate counterfactual narratives — sycophancy + unverifiability outweighed the upside for a take-home. Evidence is presented structurally for the reader to interpret.

## Goodhart warning

This dashboard is built for asking better questions, not for replacing judgment. If it ever became a formal KPI, the metrics would optimize themselves into uselessness.
