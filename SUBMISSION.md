# Submission — PostHog Engineering Impact

## Dashboard URL

https://posthog-impact-dashboard-np5m2h9hvlp9gqw5hrvsvd.streamlit.app/

## Approach

Identifying "impactful engineers" is a multi-dimensional problem that single-metric scorecards (LoC, commit count, PR count) systematically distort. Different valuable contribution patterns — the independent shipper, the platform builder, the technical lead, the OSS maintainer — collapse into noise under a scalar score. This dashboard is built around the opposite premise: **impact is a profile, not a number.**

### The 4-pillar framework

Engineers are scored on four orthogonal pillars, presented side-by-side. A composite (`Ship 0.35 + Lift 0.30 + Reach 0.25 + Steer 0.10`) exists only for ordering — the dashboard exposes per-pillar leaderboards so different shapes of contribution surface.

| Pillar | What it captures |
|---|---|
| **Ship** | Code that *landed and stayed in the live cycle.* Severity-weighted PR count, log-capped on size to defeat LoC gaming, plus **Engagement** = % of source files this PR touched that *later* PRs (by others) also touched. Engagement requires ≥30d post-merge exposure (so recent work isn't unfairly zeroed); imputed via global mean for engineers with fewer than 2 eligible PRs. Reverts penalized. |
| **Lift** | Sync + async leverage on others. Review-graph PageRank (whose review do others want), deep reviews (≥3 inline comments, filtering rubber-stamp approvals), and **OSS-external triage** — replies from org members on issues opened by non-members, weighted by resolution rate. PostHog is open-source; this is real work no other pillar would surface. |
| **Reach** | Depth in critical subsystems. CODEOWNERS membership combined with a *de-facto-owner* heuristic (≥3 PRs in a CODEOWNERS path), since PostHog uses team handles rather than individual users. Architectural changes (new modules, migrations, large refactors), maintainer-applied critical labels, and issues formally closed by their PRs. |
| **Steer** *(weak signal)* | Judgment and direction-setting. Review push-back (`CHANGES_REQUESTED`) and maintainer-initiated review requests received. Marked *weak* in-product because most of this signal lives in internal docs (RFCs, design reviews, Slack), not public GitHub. |

### Filters

- **Bots** removed via 3-layer check: `user.type == "Bot"`, `[bot]` suffix, known-pattern list. Known-list alone misses new bots; API-only misses user-account bots.
- **No-semantic PRs** dropped by PR-level substantiveness check (zero source-file additions/deletions = pure docs / lockfile / snapshot). We deliberately do **not** use a PR-count threshold — a single critical fix is exactly the signal the assignment asks us to surface.

### Deliberate non-decisions

- **No LLM-generated counterfactual narrative.** Tempting, but sycophantic and unverifiable. Structured evidence (top PRs with signal tags + URLs) is shown instead; judgment is left to the reader.
- **No single composite as headline.** The composite orders the cards, but the four pillars are the substance.
- **In-product Goodhart warning.** A metric that becomes a target ceases to be a good measure; the dashboard is for asking better questions, not replacing judgment.

### Theoretical grounding

The framework is a synthesis, not a reproduction of one paper. The multi-dimensional structure is closest to **SPACE** (Forsgren, Storey, Maddila, Zimmermann, Houck, Nagappan, *ACM Queue* 2021), extended with two impact-specific axes (Reach, Steer) that productivity frameworks don't cover. Specific signals draw on code-review research (Bacchelli & Bird, *ICSE* 2013), OSS newcomer / triage work (Steinmacher et al., Pinto et al.), bus-factor literature (Avelino et al., *SANER* 2016), and reviewer-network graph methods (Yu et al., *ICSME* 2014). The Engagement metric and de-facto-owner heuristic are domain-specific judgment calls, not peer-reviewed.

### Acknowledged blind spots

- **Steer** is structurally under-observed in public data.
- 90 days is too short for true code longevity; Engagement is a proxy.
- Refactors that close few formal issues are systematically under-credited; per-pillar leaderboards exist partly to compensate.
- CODEOWNERS at PostHog uses team handles; individual ownership is inferred via the de-facto-owner heuristic.

## AI session log

All work in this submission was done in collaboration with Claude Code (Opus 4.7). Full unedited session transcript: [`claude-session.jsonl`](./claude-session.jsonl) *(recruiter email redacted; no other modifications)*.

Notable moments:
- I pushed back on the initial framework with 5 specific critiques: (1) the "still alive at window end" engagement metric was structurally wrong for a 90-day window; (2) the no-semantic PR filter risked killing surgical 1-line fixes — switch to AST-aware / source-file-only check; (3) LLM counterfactual narratives are sycophantic and unverifiable — drop or RAG-cite; (4) PostHog being open-source means external-issue triage is real work that needed its own signal; (5) bot detection should not rely solely on a known-list — use `user.type == "Bot"` + `[bot]` suffix as well.
- All 5 were incorporated and visibly changed the design — see Engagement formula, no-semantic filter, OSS-triage signal in Lift, and 3-layer bot check.

## Time

| Phase | Window | Duration |
|---|---|---|
| Framework alignment discussion | 2026-04-26 14:50 → 2026-04-26 15:14 | ~24 min |
| Implementation (fetch + analyze + dashboard + deploy) | 2026-04-26 15:14 → 2026-04-26 15:48 | ~33 min |
| **Total** | | **~57 min** |
