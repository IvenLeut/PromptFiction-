"""Visual comparisons of supplied KPIs, without investment scoring logic."""
from collections import Counter

import plotly.graph_objects as go

from models import EvaluatedLead
from ui_theme import (
    BLACK, CHARCOAL, COMPARISON_LIMIT, FONT, GRID_LIGHT, INK, MINT, MUTED, NEUTRAL, ORANGE, RUST, SCORE_MAX,
    STAGE_COLORS, TEAL, TEAL_DARK, WHITE, format_score,
)


def stage_figure(leads: list[EvaluatedLead], labels: list[str] | None = None) -> go.Figure:
    """Donut chart of the stage classification from step 3 (or of ``labels``, one per lead)."""
    counts = Counter(labels if labels is not None else (lead.stage_classification for lead in leads))
    stages = [stage for stage in STAGE_COLORS if stage in counts] + sorted(set(counts) - set(STAGE_COLORS))
    fig = go.Figure(go.Pie(labels=stages, values=[counts[stage] for stage in stages], hole=.76,
        sort=False, marker=dict(colors=[STAGE_COLORS.get(stage, NEUTRAL) for stage in stages], line=dict(color=WHITE, width=4)),
        textinfo="none", hovertemplate="%{label}: %{value} startups (%{percent})<extra></extra>"))
    fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=40), paper_bgcolor=WHITE,
        font=dict(family=FONT, color=INK, size=13),
        annotations=[dict(text=f"<b>{len(leads):02}</b><br><span style='font-size:12px'>STARTUPS</span>",
                          showarrow=False, font=dict(size=35), x=.5, y=.5)],
        legend=dict(orientation="h", y=-.08, x=.5, xanchor="center"))
    return fig


def comparison_figure(leads: list[EvaluatedLead]) -> go.Figure:
    """Grouped bars for the first ``COMPARISON_LIMIT`` leads, best on top."""
    chosen = list(reversed(leads[:COMPARISON_LIMIT]))
    fig = go.Figure()
    for name, field, color in [("Company", "company_score", CHARCOAL),
                                ("Market potential", "market_potential_score", ORANGE),
                                ("Risk · lower is better", "risk_score", TEAL_DARK)]:
        fig.add_trace(go.Bar(name=name, y=[lead.name for lead in chosen], x=[getattr(lead, field) for lead in chosen],
                            orientation="h", marker_color=color,
                            hovertemplate="%{y}<br>%{x}/100<extra>" + name + "</extra>"))
    fig.update_layout(barmode="group", bargap=.3, height=max(290, len(chosen) * 54),
        paper_bgcolor=WHITE, plot_bgcolor=WHITE, margin=dict(l=0, r=15, t=5, b=25),
        font=dict(family=FONT, color=INK, size=13),
        xaxis=dict(range=[0, SCORE_MAX], gridcolor=GRID_LIGHT, title=None, fixedrange=True),
        yaxis=dict(automargin=True, fixedrange=True),
        legend=dict(orientation="h", y=1.12, x=0),
        hoverlabel=dict(bgcolor=INK, font_color=WHITE))
    return fig


def profile_figure(lead: EvaluatedLead) -> go.Figure:
    """Horizontal bars with the four scores of one lead."""
    labels = ["Score", "Company", "Market potential", "Risk"]
    values = [lead.overall_score, lead.company_score, lead.market_potential_score, lead.risk_score]
    fig = go.Figure(go.Bar(x=values[::-1], y=labels[::-1], orientation="h",
        marker_color=[TEAL, ORANGE, BLACK, RUST],
        text=[format_score(score) for score in values[::-1]], textposition="outside",
        hovertemplate="%{y}: %{x}/100<extra></extra>"))
    # 115 leaves room for the value labels right of a full bar.
    fig.update_layout(height=235, xaxis=dict(range=[0, 115], tickvals=[0, 25, 50, 75, 100], gridcolor=GRID_LIGHT),
                      paper_bgcolor=WHITE, plot_bgcolor=WHITE, margin=dict(l=0, r=10, t=0, b=20),
                      font=dict(color=INK, family=FONT))
    return fig


def backtest_figure(companies: list[dict]) -> go.Figure:
    """Months of lead time per backtest company (AGENT_TEAM/eval/backtest.json), longest on top.

    Companies outside the headline (aggregator, upper bound) are drawn in grey and named in the hover.
    """
    rows = sorted((c for c in companies if c.get("lead_months") is not None), key=lambda c: c["lead_months"])
    fig = go.Figure(go.Bar(
        x=[c["lead_months"] for c in rows], y=[c["name"] for c in rows], orientation="h",
        marker_color=[ORANGE if c.get("in_headline") else NEUTRAL for c in rows],
        text=[f"{c['lead_months']:.0f}" for c in rows], textposition="outside",
        customdata=[[c.get("signal_date") or "?", c.get("external_date") or "?",
                     "funding announcement" if c.get("external_kind") == "finanzierungsmeldung" else "DB entry",
                     "" if c.get("in_headline") else " · not in the headline"] for c in rows],
        hovertemplate="<b>%{y}</b>%{customdata[3]}<br>Funding-catalogue signal %{customdata[0]}<br>"
                      "first %{customdata[2]} %{customdata[1]}<br>%{x:.1f} months lead time<extra></extra>"))
    fig.update_layout(height=max(260, 30 * len(rows) + 60), paper_bgcolor=WHITE, plot_bgcolor=WHITE,
                      margin=dict(l=0, r=30, t=10, b=30), font=dict(family=FONT, color=INK, size=13),
                      xaxis=dict(title="Months lead time", gridcolor=GRID_LIGHT, fixedrange=True, color=MUTED),
                      yaxis=dict(automargin=True, fixedrange=True),
                      hoverlabel=dict(bgcolor=INK, font_color=WHITE))
    return fig


def timeline_figure(events: list[tuple]) -> go.Figure:
    """Dated signals of one lead on a time axis; events are (date, label, source, url, key)."""
    fig = go.Figure(go.Scatter(
        x=[e[0] for e in events], y=[0] * len(events), mode="markers",
        marker=dict(size=[16 if e[4] else 11 for e in events], color=[ORANGE if e[4] else MINT for e in events],
                    line=dict(color=INK, width=1)),
        customdata=[[e[1], e[2]] for e in events],
        hovertemplate="<b>%{x|%d.%m.%Y}</b><br>%{customdata[0]}<br><i>%{customdata[1]}</i><extra></extra>"))
    fig.update_layout(height=150, paper_bgcolor=WHITE, plot_bgcolor=WHITE, showlegend=False,
                      margin=dict(l=10, r=10, t=10, b=30), font=dict(family=FONT, color=INK, size=12),
                      xaxis=dict(showgrid=True, gridcolor=GRID_LIGHT, fixedrange=True, color=MUTED, tickformat="%m/%Y"),
                      yaxis=dict(visible=False, fixedrange=True, range=[-1, 1]),
                      hoverlabel=dict(bgcolor=INK, font_color=WHITE))
    fig.add_hline(y=0, line_color=NEUTRAL, line_width=2)
    return fig
