"""生成 Leaflet 可缩放/点击地图（本地米坐标 → CRS.Simple）。"""
from __future__ import annotations

import json
from typing import List, Optional

from spatial_tools import CampusMap


def build_leaflet_html(
    campus: CampusMap,
    user_location_name: Optional[str] = None,
    selected_name: Optional[str] = None,
    highlight_names: Optional[List[str]] = None,
    height_px: int = 560,
) -> str:
    highlight_names = set(highlight_names or [])
    pois = []
    xs, ys = [], []
    for p in campus.all_pois():
        xs.append(p.x)
        ys.append(p.y)
        kind = "normal"
        if user_location_name and p.name == user_location_name:
            kind = "user"
        elif selected_name and p.name == selected_name:
            kind = "selected"
        elif p.name in highlight_names:
            kind = "hi"
        pois.append({"name": p.name, "x": p.x, "y": p.y, "type": p.type, "kind": kind})

    pad = 40
    min_x, max_x = min(xs) - pad, max(xs) + pad
    min_y, max_y = min(ys) - pad, max(ys) + pad
    # Leaflet CRS.Simple: y 向下为正，地图数据 y 向上 → 翻转
    pois_js = []
    for p in pois:
        pois_js.append(
            {
                **p,
                "ly": max_y + min_y - p["y"],  # flip for leaflet
            }
        )

    data = json.dumps(
        {"pois": pois_js, "bounds": [[min_y, min_x], [max_y, max_x]], "min_x": min_x, "max_x": max_x, "min_y": min_y, "max_y": max_y},
        ensure_ascii=False,
    )

    html = f"""
<div id="map-wrap" style="height:{height_px}px;width:100%;border:1px solid #ddd;border-radius:8px;overflow:hidden;position:relative;">
  <div id="blv-map" style="height:100%;width:100%;"></div>
  <div id="map-hint" style="position:absolute;top:8px;left:8px;background:rgba(255,255,255,.92);padding:6px 10px;border-radius:6px;font-size:12px;z-index:1000;box-shadow:0 1px 4px rgba(0,0,0,.12);">
    滚轮缩放 · 拖拽平移 · <b>点击圆点</b>选中地点
  </div>
</div>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
(function() {{
  const DATA = {data};
  // 清理旧地图
  const el = document.getElementById('blv-map');
  if (!el) return;
  el.innerHTML = '';
  if (window._blvMap) {{ try {{ window._blvMap.remove(); }} catch(e) {{}} }}

  // CRS.Simple：用本地米。注意 Leaflet lat= y, lng= x
  const map = L.map('blv-map', {{
    crs: L.CRS.Simple,
    minZoom: -2,
    maxZoom: 4,
  }});
  window._blvMap = map;
  window._selectedPoi = window._selectedPoi || '';

  const minX = DATA.min_x, maxX = DATA.max_x, minY = DATA.min_y, maxY = DATA.max_y;
  // bounds: [[south, west], [north, east]] in (y_flip, x)
  const yFlip = (y) => (maxY + minY - y);
  const bounds = [[yFlip(maxY), minX], [yFlip(minY), maxX]];
  map.fitBounds(bounds, {{ padding: [20, 20] }});

  // 浅色背景网格
  const canvas = L.gridLayer({{
    noWrap: true,
    tileSize: 128,
  }});
  // 简单矩形底
  L.rectangle(bounds, {{
    color: '#bdc3c7', weight: 1, fillColor: '#f7f9fc', fillOpacity: 1
  }}).addTo(map);

  function colorFor(kind) {{
    if (kind === 'user') return '#27ae60';
    if (kind === 'selected') return '#f39c12';
    if (kind === 'hi') return '#e74c3c';
    return '#3498db';
  }}
  function radiusFor(kind) {{
    if (kind === 'user' || kind === 'selected') return 14;
    if (kind === 'hi') return 11;
    return 9;
  }}

  DATA.pois.forEach(function(p) {{
    const lat = yFlip(p.y);
    const lng = p.x;
    const marker = L.circleMarker([lat, lng], {{
      radius: radiusFor(p.kind),
      color: '#1a1a1a',
      weight: 1.5,
      fillColor: colorFor(p.kind),
      fillOpacity: 0.95,
    }}).addTo(map);
    marker.bindTooltip(p.name + (p.kind==='user'?' ←你在这':(p.kind==='selected'?' ←已点选':'')), {{permanent: false, direction: 'top'}});
    marker.bindPopup('<b>' + p.name + '</b><br/>类型: ' + p.type + '<br/><span style="color:#666">点击圆点可选中</span>');
    marker.on('click', function() {{
      window._selectedPoi = p.name;
      // 写入隐藏输入，方便 Gradio 读取
      const box = document.querySelector('#poi-pick textarea, #poi-pick input, textarea[data-testid="textbox"]');
      // 找带 elem id 的
      const t = document.getElementById('poi-pick');
      if (t) {{
        const input = t.querySelector('textarea') || t.querySelector('input');
        if (input) {{
          input.value = p.name;
          input.dispatchEvent(new Event('input', {{ bubbles: true }}));
        }}
      }}
      // 更新提示
      const hint = document.getElementById('map-hint');
      if (hint) hint.innerHTML = '已点选：<b style="color:#e67e22">' + p.name + '</b> · 点击下方「确认选点并询问」';
    }});
  }});

  // 图例
  const legend = L.control({{position: 'bottomright'}});
  legend.onAdd = function() {{
    const d = L.DomUtil.create('div');
    d.style.cssText = 'background:white;padding:6px 8px;border-radius:6px;font-size:11px;line-height:1.6;box-shadow:0 1px 4px rgba(0,0,0,.15)';
    d.innerHTML = '<span style="color:#27ae60">●</span> 你的位置<br/><span style="color:#f39c12">●</span> 点选<br/><span style="color:#e74c3c">●</span> 查询<br/><span style="color:#3498db">●</span> 其他';
    return d;
  }};
  legend.addTo(map);
}})();
</script>
"""
    return html
