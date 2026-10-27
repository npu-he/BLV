"""Self-contained offline SVG map: north-up, pan/zoom, real GeoJSON layers."""
import html
import json

def map_html(agent):
    campus=agent.campus
    pois=campus.all_pois()
    from pyproj import Transformer
    project=Transformer.from_crs('EPSG:4326','EPSG:32649',always_xy=True)
    xy=[p.xy for p in pois]
    projected=[]
    for f in campus.features:
        g=f['geometry'];kind=g['type']
        if kind=='Polygon': rings=[[project.transform(*p) for p in ring] for ring in g['coordinates']]
        elif kind=='LineString': rings=[[project.transform(*p) for p in g['coordinates']]]
        else:continue
        projected.append((f,rings));xy.extend(p for ring in rings for p in ring)
    lo=min(p[0] for p in xy)-35;hi=max(p[1] for p in xy)+35
    width=max(p[0] for p in xy)-lo+35;height=hi-min(p[1] for p in xy)+35
    def pts(r):return ' '.join(f'{x-lo:.2f},{hi-y:.2f}' for x,y in r)
    shapes=[]
    for f,rings in sorted(projected,key=lambda x:{'boundary':0,'area':1,'road':2,'building':3}.get(x[0]['properties']['layer'],4)):
        layer=f['properties']['layer'];name=html.escape(f['properties'].get('name') or layer)
        if layer=='road':
            shapes.append(f'<polyline points="{pts(rings[0])}" fill="none" stroke="#c3b6a1" stroke-width="5"><title>{name}；公开道路数据，通行条件未核实</title></polyline>')
        else:
            d=' '.join('M '+' L '.join(f'{x-lo:.2f} {hi-y:.2f}' for x,y in ring)+' Z' for ring in rings)
            color={'boundary':'#f4f7ef','area':'#cfe7db','building':'#d7e2ef'}.get(layer,'#eee')
            shapes.append(f'<path d="{d}" fill="{color}" stroke="#9baebd" stroke-width="1.5" fill-rule="evenodd"><title>{name}</title></path>')
    for p in pois:
        x,y=p.x-lo,hi-p.y
        selected=p.name==agent.selected_poi;user=p.name==agent.user_location
        color='#16784f' if user else '#d86812' if selected else '#2563a0'
        label=html.escape(p.name);suffix='（您确认的位置）' if user else '（选中）' if selected else ''
        shapes.append(f'<g tabindex="0" role="img" aria-label="{label}{suffix}"><title>{label}{suffix}；位置是地图代表点，非核实入口</title><circle cx="{x:.2f}" cy="{y:.2f}" r="{12 if selected or user else 6}" fill="{color}"/><text x="{x+9:.2f}" y="{y-8:.2f}" font-family="Microsoft YaHei,Noto Sans CJK SC,sans-serif" font-size="15" fill="#20384c">{label}{suffix}</text></g>')
    document='''<!doctype html><html lang="zh"><meta charset="utf-8"><style>body{margin:0;font:14px sans-serif;background:#f8fafc}header{padding:10px}button{padding:7px 14px;margin:3px}svg{width:100%;height:510px;touch-action:none;cursor:grab}text{pointer-events:none}</style><header><b>西北工业大学长安校区</b>　北↑<br>公开数据待核实 · 绿色为确认位置，橙色为选中地点<br><button onclick="zoom(.8)">放大</button><button onclick="zoom(1.25)">缩小</button><button onclick="reset()">全图</button> 拖拽平移；悬停/聚焦查看名称。地点选择使用左侧控件。</header><svg id="map" role="img" aria-label="校园建筑、道路及地点地图" viewBox="0 0 WIDTH HEIGHT">SHAPES</svg><footer>© OpenStreetMap contributors · <a target="_blank" href="https://www.openstreetmap.org/copyright">ODbL</a> · 无外部底图依赖</footer><script>const s=document.getElementById('map'),original=[0,0,WIDTH,HEIGHT];let v=[...original],drag=null;function paint(){s.setAttribute('viewBox',v.join(' '))}function zoom(k){v=[v[0]+v[2]*(1-k)/2,v[1]+v[3]*(1-k)/2,v[2]*k,v[3]*k];paint()}function reset(){v=[...original];paint()}s.onwheel=e=>{e.preventDefault();zoom(e.deltaY>0?1.15:.87)};s.onpointerdown=e=>{drag=[e.clientX,e.clientY,...v];s.setPointerCapture(e.pointerId)};s.onpointermove=e=>{if(!drag)return;let scale=Math.min(s.clientWidth/drag[4],s.clientHeight/drag[5]);v[0]=drag[2]-(e.clientX-drag[0])/scale;v[1]=drag[3]-(e.clientY-drag[1])/scale;paint()};s.onpointerup=()=>drag=null;s.onpointercancel=()=>drag=null;</script></html>'''.replace('WIDTH',str(round(width,2))).replace('HEIGHT',str(round(height,2))).replace('SHAPES',''.join(shapes))
    return '<iframe title="校园交互地图" sandbox="allow-scripts allow-popups" style="width:100%;height:640px;border:1px solid #dbe3ec;border-radius:12px" srcdoc="'+html.escape(document,quote=True)+'"></iframe>'
