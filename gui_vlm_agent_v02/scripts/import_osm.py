"""Convert an OSM XML snapshot into RFC 7946 features. No invented roads or POIs."""
from pathlib import Path
import xml.etree.ElementTree as ET
import json
from datetime import datetime, timezone

def convert(source, destination):
    root = ET.parse(source).getroot()
    nodes = {e.attrib['id']: [float(e.attrib['lon']), float(e.attrib['lat'])] for e in root.findall('node')}
    ways = {e.attrib['id']: e for e in root.findall('way')}
    def tags(e): return {t.attrib['k']: t.attrib['v'] for t in e.findall('tag')}
    def coords(w): return [nodes[n.attrib['ref']] for n in w.findall('nd') if n.attrib['ref'] in nodes]
    boundary = coords(ways['273391732'])
    def inside(p):
        x,y=p; yes=False
        for a,b in zip(boundary,boundary[1:]):
            if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]: yes=not yes
        return yes
    def center(cs):
        pts=cs[:-1] if cs[0]==cs[-1] else cs
        return [sum(p[0] for p in pts)/len(pts),sum(p[1] for p in pts)/len(pts)]
    features=[]
    def add(e,g,t,layer):
        ident=e.tag+'/'+e.attrib['id']
        props={'id':ident,'name':t.get('name',''),'layer':layer,'osm_tags':t,'source':'OpenStreetMap','verified':False,'accessibility_status':'unknown'}
        if t.get('amenity')=='library': props['aliases']=['图书馆']
        features.append({'type':'Feature','id':ident,'properties':props,'geometry':g})
    for w in ways.values():
        cs=coords(w);t=tags(w)
        if len(cs)<2:continue
        if w.attrib['id']=='273391732':add(w,{'type':'Polygon','coordinates':[cs]},t,'boundary');continue
        if not inside(center(cs)):continue
        if t.get('building') or t.get('water') or t.get('natural')=='water' or t.get('leisure'):
            if len(cs)>=4 and cs[0]==cs[-1]:add(w,{'type':'Polygon','coordinates':[cs]},t,'building' if t.get('building') else 'area')
        elif t.get('highway'):
            add(w,{'type':'LineString','coordinates':cs},t,'road')
    for n in root.findall('node'):
        t=tags(n);p=nodes[n.attrib['id']]
        if inside(p) and t.get('name') and (t.get('amenity') or t.get('building') or t.get('barrier')=='gate'):
            add(n,{'type':'Point','coordinates':p},t,'poi')
    # Assemble multipolygon rings by shared OSM node IDs. Incomplete relations are skipped.
    for rel in root.findall('relation'):
        t=tags(rel)
        if t.get('type')!='multipolygon' or not t.get('name'):continue
        rings={}
        for role in ['outer','inner']:
            chains=[]
            for m in rel.findall('member'):
                if m.attrib.get('type')=='way' and m.attrib.get('role','outer')==role and m.attrib['ref'] in ways:
                    chains.append([n.attrib['ref'] for n in ways[m.attrib['ref']].findall('nd')])
            merged=[]
            while chains:
                chain=chains.pop()
                changed=True
                while chain[0]!=chain[-1] and changed:
                    changed=False
                    for i,c in enumerate(chains):
                        if chain[-1]==c[0]:chain+=c[1:]
                        elif chain[-1]==c[-1]:chain+=list(reversed(c))[1:]
                        elif chain[0]==c[-1]:chain=c[:-1]+chain
                        elif chain[0]==c[0]:chain=list(reversed(c))[:-1]+chain
                        else:continue
                        chains.pop(i);changed=True;break
                if len(chain)>=4 and chain[0]==chain[-1] and all(n in nodes for n in chain):merged.append([nodes[n] for n in chain])
            rings[role]=merged
        if len(rings['outer'])==1 and inside(center(rings['outer'][0])):
            add(rel,{'type':'Polygon','coordinates':rings['outer']+rings['inner']},t,'building')
    result={'type':'FeatureCollection','metadata':{'name':'西北工业大学长安校区 · OSM公开数据待核实','crs':'WGS84','source':'https://www.openstreetmap.org/way/273391732','license':'ODbL-1.0','attribution':'© OpenStreetMap contributors','snapshot_at':root.attrib.get('timestamp') or (root.find('meta').attrib.get('osm_base') if root.find('meta') is not None else 'unknown'),'imported_at':datetime.now(timezone.utc).isoformat(),'verified':False,'scope':'boundary 273391732; roads selected by center inside boundary; incomplete relations omitted','official_reference':'https://peixun.nwpu.edu.cn/index/xydt.htm'},'features':features}
    Path(destination).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Converted',len(features),'features')
if __name__=='__main__':
    base=Path(__file__).resolve().parents[1]
    convert(base/'data/nwpu_changan_source.osm',base/'data/nwpu_changan.geojson')
