"""Visual comparisons of supplied KPIs, without investment scoring logic."""
from collections import Counter

import plotly.graph_objects as go


def stage_figure(leads):
    counts = Counter(x.stage_classification for x in leads)
    stages = [x for x in ("Pre-Seed", "Seed", "Early Growth", "Unbekannt") if x in counts]
    colors = {"Pre-Seed": "#f5653f", "Seed": "#171717", "Early Growth": "#94cbd0", "Unbekannt": "#c9cdd2"}
    fig = go.Figure(go.Pie(labels=stages, values=[counts[x] for x in stages], hole=.76,
        sort=False, marker=dict(colors=[colors[x] for x in stages], line=dict(color="white", width=4)),
        textinfo="none", hovertemplate="%{label}: %{value} Startups (%{percent})<extra></extra>"))
    fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=40), paper_bgcolor="white",
        font=dict(family="Arial", color="#221f19", size=13),
        annotations=[dict(text=f"<b>{len(leads):02}</b><br><span style='font-size:12px'>STARTUPS</span>",
                          showarrow=False, font=dict(size=35), x=.5, y=.5)],
        legend=dict(orientation="h", y=-.08, x=.5, xanchor="center"))
    return fig


def comparison_figure(leads):
    chosen = list(reversed(leads[:10]))
    fig = go.Figure()
    for name, field, color in [("Unternehmen", "company_score", "#161616"),
                                ("Marktpotenzial", "market_potential_score", "#f5653f"),
                                ("Risiko · niedriger ist besser", "risk_score", "#78bfc5")]:
        fig.add_trace(go.Bar(name=name, y=[x.name for x in chosen], x=[getattr(x, field) for x in chosen],
                            orientation="h", marker_color=color,
                            hovertemplate="%{y}<br>%{x}/100<extra>" + name + "</extra>"))
    fig.update_layout(barmode="group", bargap=.3, height=max(290, len(chosen) * 54),
        paper_bgcolor="white", plot_bgcolor="white", margin=dict(l=0, r=15, t=5, b=25),
        font=dict(family="Arial", color="#221f19", size=13),
        xaxis=dict(range=[0, 100], gridcolor="#ededed", title=None, fixedrange=True),
        yaxis=dict(automargin=True, fixedrange=True),
        legend=dict(orientation="h", y=1.12, x=0),
        hoverlabel=dict(bgcolor="#221f19", font_color="white"))
    return fig


def profile_figure(lead):
    labels = ["Score", "Unternehmen", "Marktpotenzial", "Risiko"]
    values = [lead.overall_score, lead.company_score, lead.market_potential_score, lead.risk_score]
    fig = go.Figure(go.Bar(x=values[::-1], y=labels[::-1], orientation="h",
        marker_color=["#94cbd0", "#f5653f", "#171717", "#b63716"],
        text=["Unbekannt" if x is None else f"{x:.1f}" for x in values[::-1]], textposition="outside",
        hovertemplate="%{y}: %{x}/100<extra></extra>"))
    fig.update_layout(height=235, xaxis=dict(range=[0, 115], tickvals=[0, 25, 50, 75, 100], gridcolor="#ededed"),
                      paper_bgcolor="white", plot_bgcolor="white", margin=dict(l=0, r=10, t=0, b=20),
                      font=dict(color="#221f19", family="Arial"))
    return fig
