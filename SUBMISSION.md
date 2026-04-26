# Submission — PostHog Engineering Impact

## Dashboard URL

`https://posthog-impact-dashboard-<TBD>.streamlit.app/`

## Approach

Single-page Streamlit dashboard ranking PostHog/posthog engineers over the last 90 days using **4 orthogonal pillars** instead of one composite metric. The framework deliberately avoids treating "impact" as a scalar, since different valuable contribution patterns (independent shipper, platform builder, technical lead) collapse into noise under a single score.

| Pillar | What it captures |
|---|---|
| **Ship** | Code that *landed and stayed in the live cycle.* Severity- and size-weighted PR count (size capped to defeat LoC gaming) + Engagement = % of source files this PR touched that *later* PRs (by others) touched too. Engagement requires ≥30d post-merge exposure to avoid systematically under-crediting recent work. Reverts penalized. |
| **Lift** | Sync + async leverage. Review-graph PageRank, deep reviews (≥3 inline comments), and **OSS-external triage** — replies from maintainers on issues opened by non-org-members + their resolution rate. PostHog is open-source; this is real work that no other pillar would surface. |
| **Reach** | Depth in critical subsystems. CODEOWNERS membership (PostHog uses team handles, so we add a *de-facto-owner* heuristic: ≥3 PRs in a CODEOWNERS path = owner). Architectural-change flag (new modules, migrations, schema, large refactors). Maintainer-applied critical labels. Issues formally closed. |
| **Steer** *(weak signal)* | Judgment & direction-setting. Review push-back (CHANGES_REQUESTED) and maintainer-initiated review requests received. Marked *weak* in the dashboard because most of this signal lives in internal docs, not public GitHub. |

### Filters

- **Bots** removed via 3-layer check: `user.type == Bot`, `[bot]` suffix, known-pattern list.
- **No-semantic PRs** dropped: those with zero source-file additions/deletions (pure docs / lockfile / snapshot bumps). Small *substantive* PRs preserved — a one-line critical bug fix still counts. We do NOT filter by PR count threshold; a single high-impact PR is exactly the signal the assignment is asking us to surface.

### Deliberate non-decisions

- **No LLM-generated counterfactual narrative.** Tempting (it would translate evidence into "if X were gone, Y wouldn't have shipped"), but LLMs produce sycophantic and unverifiable text. We show structured evidence (top PRs with signal tags + URLs) and leave judgment to the reader.
- **No single composite as headline.** We compute one for sorting, but the dashboard exposes all four pillars side-by-side and provides per-pillar leaderboards so different patterns of contribution are visible.
- **Goodhart warning shown in-product.** This dashboard is for asking better questions, not for replacing judgment. If it ever became a formal KPI it would optimize itself into uselessness.

### Acknowledged blind spots

- **Steer** pillar is structurally under-observed in public data.
- 90 days is too short for true code longevity; Engagement is a proxy.
- Refactors that close few formal issues are systematically under-credited; per-pillar leaderboards exist partly to compensate.
- CODEOWNERS at PostHog uses team handles; individual ownership is inferred via the de-facto-owner heuristic.

## Time

Start: 2026-04-26 15:14
End: <TBD>
