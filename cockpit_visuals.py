"""Pure charts of supplied observations. No synthetic trajectories or missing-as-zero."""
from collections import Counter
from html import escape
import plotly.graph_objects as go


def base(height=235):
    fig = go.Figure()
    fig.update_layout(template="plotly_white", height=height, margin=dict(l=10,r=16,t=8,b=28),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="Arial, sans-serif",size=12,color="#393630"), showlegend=False,
                      colorway=["#80b4ba","#393630","#e8b79f"], dragmode=False)
    fig.update_xaxes(gridcolor="#e9e4dc", zeroline=False, fixedrange=True, automargin=True)
    fig.update_yaxes(gridcolor="#e9e4dc", zeroline=False, fixedrange=True, automargin=True)
    return fig


def pipeline_scatter(leads):
    rows = [l for l in leads if l.scores.get("Quality") is not None and l.confidence is not None]
    fig = base()
    for excluded, color, label in ((False,"#80b4ba","In sourcing scope"),(True,"#ccc6bd","Sourcing excluded")):
        group = [l for l in rows if l.excluded == excluded]
        if group:
            fig.add_trace(go.Scatter(x=[l.scores["Quality"] for l in group], y=[l.confidence*100 for l in group],
                mode="markers", ids=[l.id for l in group], text=[escape(l.name) for l in group], name=label,
                marker=dict(size=9,color=color,line=dict(width=.7,color="white")),
                hovertemplate="%{text}<br>Quality %{x:.1f}/100<br>Confidence %{y:.0f}%<extra>%{fullData.name}</extra>"))
    fig.update_xaxes(title="Reported quality / 100",range=[0,100],dtick=25)
    fig.update_yaxes(title="Evidence confidence",range=[0,100],dtick=25,ticksuffix="%")
    return fig


def stage_bars(leads):
    counts = Counter(l.stage for l in leads)
    fig = base()
    labels = sorted(counts)
    fig.add_trace(go.Bar(x=[counts[k] for k in labels],y=[escape(k) for k in labels],orientation="h",marker_color="#393630",text=[counts[k] for k in labels],textposition="auto"))
    fig.update_xaxes(title="Companies",dtick=1 if len(leads)<8 else None,rangemode="tozero")
    fig.update_yaxes(autorange="reversed",showgrid=False)
    fig.update_layout(bargap=.5)
    return fig


def score_profile(lead):
    rows = [(key,lead.scores[key]) for key in ("Quality","Market","Team") if lead.scores.get(key) is not None]
    fig = base(200)
    fig.add_trace(go.Bar(x=[r[1] for r in rows],y=[r[0] for r in rows],orientation="h",marker_color="#80b4ba",text=[f"{r[1]:.0f}" for r in rows],textposition="auto"))
    fig.update_xaxes(title="Reported score · higher is better",range=[0,100],dtick=25)
    fig.update_yaxes(autorange="reversed",showgrid=False)
    fig.update_layout(bargap=.5)
    return fig


def evidence_coverage(lead):
    categories = [x for x in ("Team","Market","Risk","Stage","Other") if any(e["category"]==x for e in lead.evidence)]
    fig = base(200)
    for sourced, color, label in ((True,"#80b4ba","With source URL"),(False,"#e8b79f","No source URL")):
        values = [sum(e["category"]==c and bool(e["url"])==sourced for e in lead.evidence) for c in categories]
        fig.add_trace(go.Bar(x=values,y=categories,orientation="h",name=label,marker_color=color,
            hovertemplate="%{y}: %{x} records<extra>%{fullData.name}</extra>"))
    fig.update_layout(barmode="stack",bargap=.4,showlegend=True,legend=dict(orientation="h",y=-.3,font_size=11))
    fig.update_xaxes(title="Evidence records",dtick=1)
    fig.update_yaxes(showgrid=False,autorange="reversed")
    return fig
