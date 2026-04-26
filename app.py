"""PostHog Engineering Impact Dashboard — single-page Streamlit app."""
from __future__ import annotations
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DATA = Path(__file__).parent / "data"

st.set_page_config(
    page_title="PostHog Impact Dashboard",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- Light styling
st.markdown(
    """
<style>
.block-container { padding-top: 1.5rem; padding-bottom: 1rem; max-width: 1400px; }
h1 { margin-bottom: 0.2rem; }
.small { color: #666; font-size: 0.85rem; }
.tag { display:inline-block; padding:2px 8px; border-radius:10px; background:#eef; color:#225; font-size:0.75rem; margin-right:6px; }
.tag-crit { background:#fee; color:#a22; }
.tag-arch { background:#efe; color:#262; }
.tag-rev { background:#fcf; color:#717; }
.banner { background:#fffaf0; border-left:4px solid #d4a017; padding:0.7rem 1rem; border-radius:4px; margin-bottom:1rem; font-size:0.9rem; }
.evidence-row { padding: 4px 0; border-bottom: 1px solid #eee; }
.metric-row { display:flex; gap:1rem; flex-wrap:wrap; }
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def load() -> tuple[pd.DataFrame, dict]:
    df = pd.read_json(DATA / "scores.json")
    meta = json.loads((DATA / "raw" / "meta.json").read_text())
    return df, meta


df, meta = load()

# ===== Header =====
st.title("PostHog Engineering Impact — last 90 days")
st.caption(
    f"Window: **{meta['since'][:10]} → {meta['now'][:10]}** ({meta['window_days']} days). "
    f"Repo: PostHog/posthog. Engineers analyzed: **{len(df)}**."
)

st.markdown(
    """
<div class="banner">
<strong>How to read this dashboard.</strong> This is a tool for asking better questions, not a scorecard.
Pillars below capture different kinds of contribution and are intentionally <em>not</em> collapsed into a single ranking number.
The composite is shown only for sorting — open the Evidence Panel before drawing conclusions.
The <strong>Steer</strong> pillar is structurally under-observed in public GitHub data (design docs, RFCs, "what they prevented" mostly live internally) — interpret with caution.
</div>
""",
    unsafe_allow_html=True,
)

# ===== Pillar definitions inline =====
with st.expander("Pillar definitions & signals", expanded=False):
    st.markdown(
        """
| Pillar | What it captures | Signals |
|---|---|---|
| **Ship** | Things that landed and stayed in the live cycle | PR weight (size capped + severity weighted) · **Engagement**: % of source files this PR added/changed that *later* PRs touched (only counted for PRs with ≥30d post-merge exposure) · revert penalty |
| **Lift** | Sync + async leverage on others | Review-graph PageRank (whose review do others want) · deep reviews (≥3 inline comments) · **OSS-external triage**: replies to non-org-member issues + their resolution rate |
| **Reach** | Depth in critical subsystems | `CODEOWNERS` membership · architectural changes (new modules, migrations, large refactors) · maintainer-applied critical labels · issues formally closed by their PRs |
| **Steer** | Judgment & direction-setting *(weak signal)* | review push-back (CHANGES_REQUESTED) · maintainer-initiated review requests received |

**Filters applied.** Bots removed via 3-layer check (`user.type==Bot`, `[bot]` suffix, known-pattern list). PRs with zero source-file changes (only docs/lockfiles/snapshots/whitespace) excluded — small but substantive PRs preserved. Non-merged PRs excluded from Ship.

**Known blind spots.** Steer is largely invisible to public data. 90-day window is too short for true code longevity (we use Engagement as a proxy). Refactors and infrastructure work that close few issues are systematically under-credited; pair with the Reach pillar to compensate.
        """
    )

# ===== Top-5 cards =====
top5 = df.head(5).copy()


def render_evidence(prs: list[dict]):
    for p in prs:
        tags = []
        if p.get("severity_w", 1) >= 2.0:
            tags.append('<span class="tag tag-crit">critical</span>')
        if p.get("is_arch"):
            tags.append('<span class="tag tag-arch">architectural</span>')
        if p.get("is_revert"):
            tags.append('<span class="tag tag-rev">revert</span>')
        eng = p.get("engagement")
        if eng is not None and eng > 0.3:
            tags.append(f'<span class="tag">engagement {eng:.0%}</span>')
        closing = p.get("closing_issues") or []
        if closing:
            tags.append(f'<span class="tag">closes #{closing[0]["number"]}</span>')
        size = (p.get("additions", 0) + p.get("deletions", 0))
        st.markdown(
            f'<div class="evidence-row">'
            f'<a href="{p["url"]}" target="_blank">#{p["number"]}</a> · '
            f'{p["title"]} '
            f'<span class="small">(+{p.get("additions",0)}/-{p.get("deletions",0)}, {size} LoC) </span>'
            f'<br/>{" ".join(tags) if tags else ""}'
            f'</div>',
            unsafe_allow_html=True,
        )


def radar(row: pd.Series) -> go.Figure:
    cats = ["Ship", "Lift", "Reach", "Steer"]
    vals = [row["ship"], row["lift"], row["reach"], row["steer"]]
    fig = go.Figure(go.Scatterpolar(
        r=vals + [vals[0]],
        theta=cats + [cats[0]],
        fill="toself",
        line=dict(color="#4a6cf7"),
        fillcolor="rgba(74,108,247,0.18)",
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], showticklabels=False),
            angularaxis=dict(tickfont=dict(size=11)),
        ),
        showlegend=False,
        margin=dict(l=10, r=10, t=10, b=10),
        height=220,
    )
    return fig


st.subheader("Top 5 engineers by composite")
st.caption("Ranked by `Ship 0.35 + Lift 0.30 + Reach 0.25 + Steer 0.10` — composite is for ordering only; the four pillars are the substance.")

cols = st.columns(5)
for i, (_, row) in enumerate(top5.iterrows()):
    with cols[i]:
        st.markdown(f"#### {i+1}. [{row['login']}](https://github.com/{row['login']})")
        st.markdown(
            f'<span class="small">Composite **{row["composite"]:.0f}** · '
            f'{row["ship_pr_count"]} PRs · {row["ship_critical_pr_count"]} critical · '
            f'{row["lift_review_count"]} reviews</span>',
            unsafe_allow_html=True,
        )
        # Headline PR: top of evidence list
        ev = row.get("evidence_prs") or []
        if ev:
            top_pr = ev[0]
            st.markdown(
                f'<div class="small" style="margin-top:4px;">'
                f'Top PR: <a href="{top_pr["url"]}" target="_blank">#{top_pr["number"]}</a> '
                f'{top_pr["title"][:70]}{"..." if len(top_pr["title"]) > 70 else ""}'
                f'</div>',
                unsafe_allow_html=True,
            )
        st.plotly_chart(radar(row), use_container_width=True, config={"displayModeBar": False})
        with st.expander("Evidence", expanded=(i == 0)):
            st.markdown("**Top PRs**")
            render_evidence(row["evidence_prs"])
            st.markdown(
                f'<div class="small">'
                f'Ship: pr_score={row["ship_pr_score"]:.1f}, engagement={row["ship_engagement_avg"]:.0%} '
                f'(n={row["ship_engagement_n"]}{" — imputed (too few eligible PRs)" if row.get("ship_engagement_imputed") else ""}), '
                f'reverts={row["ship_revert_count"]}<br/>'
                f'Lift: PageRank={row["lift_pagerank"]:.4f}, deep_reviews={row["lift_deep_review_count"]}, OSS replies={row["lift_oss_replies"]} (resolved={row["lift_oss_resolved"]})<br/>'
                f'Reach: codeowner={row["reach_codeowner"]}, arch_PRs={row["reach_arch_count"]}, critical_labels={row["reach_critical_label_count"]}, issues_closed={row["reach_issues_resolved"]}<br/>'
                f'Steer: pushback={row["steer_pushback_count"]}, review_requested={row["steer_review_requests_received"]}'
                f'</div>',
                unsafe_allow_html=True,
            )

st.divider()

# ===== 4 leaderboards =====
st.subheader("Per-pillar leaderboards")
st.caption("Top 10 by each pillar — different shapes of contribution surface different people.")

lb_cols = st.columns(4)
for col, pillar, label in zip(
    lb_cols,
    ["ship", "lift", "reach", "steer"],
    ["Ship", "Lift", "Reach", "Steer (weak signal)"],
):
    with col:
        st.markdown(f"**{label}**")
        sub = df[["login", pillar]].sort_values(pillar, ascending=False).head(10).reset_index(drop=True)
        sub.index = sub.index + 1
        st.dataframe(
            sub.rename(columns={"login": "engineer", pillar: "score"}),
            use_container_width=True,
            height=380,
        )

st.divider()

# ===== Full table =====
with st.expander(f"Full ranking ({len(df)} engineers)", expanded=False):
    cols_show = [
        "login", "composite", "ship", "lift", "reach", "steer",
        "ship_pr_count", "ship_critical_pr_count", "ship_engagement_avg",
        "lift_review_count", "lift_oss_replies",
        "reach_codeowner", "reach_arch_count", "reach_issues_resolved",
        "steer_pushback_count",
    ]
    st.dataframe(df[cols_show], use_container_width=True, height=500)

st.divider()
st.markdown(
    f'<div class="small">Generated {meta["now"][:10]} from PostHog/posthog public GitHub data. '
    f'Approach + caveats: see "Pillar definitions & signals" expander above. '
    f'Source: <a href="https://github.com/PostHog/posthog">github.com/PostHog/posthog</a>.</div>',
    unsafe_allow_html=True,
)
