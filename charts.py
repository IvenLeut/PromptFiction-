"""Visual comparisons of supplied KPIs, without investment scoring logic."""
from collections import Counter

import plotly.graph_objects as go

from models import EvaluatedLead
from ui_theme import (
    BLACK, CHARCOAL, COMPARISON_LIMIT, FONT, GRID_LIGHT, INK, ORANGE, RUST, SCORE_MAX, STAGE_COLORS, TEAL,
    TEAL_DARK, WHITE, format_score,
)


def stage_figure(leads: list[EvaluatedLead]) -> go.Figure:
    """Donut chart of the stage classification from step 3."""
    counts = Counter(lead.stage_classification for lead in leads)
    stages = [stage for stage in STAGE_COLORS if stage in counts]
    fig = go.Figure(go.Pie(labels=stages, values=[counts[stage] for stage in stages], hole=.76,
        sort=False, marker=dict(colors=[STAGE_COLORS[stage] for stage in stages], line=dict(color=WHITE, width=4)),
        textinfo="none", hovertemplate="%{label}: %{value} Startups (%{percent})<extra></extra>"))
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
    for name, field, color in [("Unternehmen", "company_score", CHARCOAL),
                                ("Marktpotenzial", "market_potential_score", ORANGE),
                                ("Risiko · niedriger ist besser", "risk_score", TEAL_DARK)]:
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
    labels = ["Score", "Unternehmen", "Marktpotenzial", "Risiko"]
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
