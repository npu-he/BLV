from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent import MapAgent
from safety import SafetyGate
import llm_client
BASE=Path(__file__).resolve().parents[1]
def sample():return MapAgent(BASE/'data/campus_map.json',mode='rule',enable_safety=True)
def test_unknown_location():
    a=sample();r=a.chat('附近有什么');assert '请先' in r and a.user_location is None
def test_compound_location():
    a=sample();r=a.chat('我在图书馆，体育馆在哪？');assert a.user_location=='图书馆' and '89.4' in r
def test_same_and_tie():
    t=sample().tools;assert t.relation('图书馆','图书馆')['direction']=='同一位置'
    assert t.compare_distance('南门','图书馆','图书馆')['tie']
def test_gate_requires_successful_spatial_evidence():
    g=SafetyGate();assert not g.check_final_answer('图书馆在西边，999米。',['identify'])['allow']
    assert not g.check_final_answer('图书馆在西边。',['distance'],[{'tool':'distance','result':{'ok':False}}])['allow']
def test_llm_position_prompt_and_fallback(monkeypatch):
    a=sample();a.user_location='南门';a.mode='llm';a.api_key='placeholder'
    seen=[]
    def fake(**kw):
        seen.extend(kw['messages']);return {'content':'测试回答','tool_calls':[]}
    monkeypatch.setattr(llm_client,'chat_completions',fake)
    a.chat('我在图书馆，体育馆在哪？')
    assert any(m['content']=='用户当前位置：图书馆。' for m in seen)
    def fail(**kw):raise TimeoutError('test')
    monkeypatch.setattr(llm_client,'chat_completions',fail)
    assert '89.4' in a.chat('体育馆在哪？') and a.last_execution_mode=='rule_fallback'
def test_map_and_projection():
    a=MapAgent(BASE/'data/nwpu_changan.geojson',mode='rule')
    assert len(a.campus.features)>100 and len(a.campus.all_pois())>30
    assert a.tools.identify('图书馆')['ok']
    assert a.campus.meta['calculation_crs']=='EPSG:32649'
    assert all(108<p.lon<109 and 34<p.lat<35 for p in a.campus.all_pois())
    from campus_view import map_html
    h=map_html(a);assert '<iframe' in h and 'OpenStreetMap' in h

def test_exact_id_and_invalid_radius():
    t=sample().tools;assert len(t.identify('library')['matches'])==1
    assert not t.nearby('图书馆',radius_m=-1)['ok']
