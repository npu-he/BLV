"""可缩放、可平移、可点击的结构化地图（Plotly）。"""
from __future__ import annotations

from typing import List, Optional

import plotly.graph_objects as go

from spatial_tools import CampusMap


def build_plotly_map(
    campus: CampusMap,
    user_location_name: Optional[str] = None,
    selected_name: Optional[str] = None,
    highlight_names: Optional[List[str]] = None,
    title: str = "可点击地图（滚轮缩放 · 拖拽平移 · 点击标记）",
) -> go.Figure:
    highlight_names = set(highlight_names or [])
    pois = campus.all_pois()

    xs, ys, texts, colors, sizes, custom = [], [], [], [], [], []
    for p in pois:
        is_user = user_location_name and p.name == user_location_name
        is_sel = selected_name and p.name == selected_name
        is_hi = p.name in highlight_names
        if is_user:
            c, s = "#27ae60", 22
        elif is_sel:
            c, s = "#f39c12", 20
        elif is_hi:
            c, s = "#e74c3c", 16
        else:
            c, s = "#3498db", 12
        xs.append(p.x)
        ys.append(p.y)
        label = p.name
        if is_user:
            label += " ←你在这"
        elif is_sel:
            label += " ←已点选"
        texts.append(label)
        colors.append(c)
        sizes.append(s)
        custom.append(p.name)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=xs,
            y=ys,
            mode="markers+text",
            text=texts,
            textposition="top center",
            textfont=dict(size=11, color="#2c3e50"),
            marker=dict(
                size=sizes,
                color=colors,
                line=dict(width=1.2, color="#1a1a1a"),
                opacity=0.95,
            ),
            customdata=custom,
            hovertemplate="<b>%{customdata}</b><br>坐标: (%{x:.0f}, %{y:.0f})<extra></extra>",
            name="地点",
        )
    )

    # 用户位置到点选的连线
    name_xy = {p.name: (p.x, p.y) for p in pois}
    if user_location_name in name_xy and selected_name in name_xy and user_location_name != selected_name:
        x0, y0 = name_xy[user_location_name]
        x1, y1 = name_xy[selected_name]
        fig.add_trace(
            go.Scatter(
                x=[x0, x1],
                y=[y0, y1],
                mode="lines",
                line=dict(color="#95a5a6", width=2, dash="dash"),
                hoverinfo="skip",
                showlegend=False,
            )
        )

    fig.update_layout(
        title=dict(text=title, font=dict(size=14)),
        xaxis=dict(
            title="x（米，东）",
            scaleanchor="y",
            scaleratio=1,
            zeroline=True,
            gridcolor="#ecf0f1",
        ),
        yaxis=dict(title="y（米，北）", zeroline=True, gridcolor="#ecf0f1"),
        plot_bgcolor="#fafbfc",
        paper_bgcolor="white",
        margin=dict(l=40, r=20, t=50, b=40),
        height=560,
        clickmode="event+select",
        dragmode="pan",  # 默认拖拽平移；框选可改 select
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    # 滚轮缩放
    fig.update_xaxes(fixedrange=False)
    fig.update_yaxes(fixedrange=False)
    return fig


def point_name_from_click(evt) -> Optional[str]:
    """从 Gradio/Plotly select 或 click 事件解析 POI 名。"""
    if evt is None:
        return None
    # Gradio SelectData: evt.index, evt.value, ...
    try:
        # plotly via gr.Plot select
        if hasattr(evt, "index"):
            # 可能是点索引
            pass
        if hasattr(evt, "value"):
            v = evt.value
            if isinstance(v, str) and v:
                # 去掉标注后缀
                return v.replace(" ←你在这", "").replace(" ←已点选", "").strip()
            if isinstance(v, dict):
                if "customdata" in v:
                    return str(v["customdata"])
                if "text" in v:
                    t = str(v["text"])
                    return t.replace(" ←你在这", "").replace(" ←已点选", "").strip()
        # dict-like
        if isinstance(evt, dict):
            pts = evt.get("points") or []
            if pts:
                p0 = pts[0]
                if p0.get("customdata"):
                    return str(p0["customdata"])
                if p0.get("text"):
                    t = str(p0["text"])
                    return t.replace(" ←你在这", "").replace(" ←已点选", "").strip()
    except Exception:
        return None
    return None
