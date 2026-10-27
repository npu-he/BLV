"""Campus exploration UI. Per-session state; offline map; explicit model fallback."""
from pathlib import Path
import json
import os
import uuid
from datetime import datetime, timezone
import gradio as gr
from agent import MapAgent
from campus_view import map_html

ROOT=Path(__file__).resolve().parent

def build_ui(map_path=None, default_location=None, mode='auto', provider=None):
    path=Path(map_path) if map_path else ROOT/'data/nwpu_changan.geojson'
    def fresh():
        a=MapAgent(path,mode=mode,provider=provider,enable_safety=True)
        a.session_id=uuid.uuid4().hex
        if default_location:
            r=a.tools.identify(default_location)
            if r.get('ok') and len(r['matches'])==1:a.user_location=r['matches'][0]['name']
        return a
    preview=fresh();choices=[(p.name+' ['+p.id+']',p.id) for p in preview.campus.all_pois()]
    def status(a):
        return f"确认位置：{a.user_location or '未设置'}；选中：{a.selected_poi or '无'}；配置模式：{a.mode}/{a.provider}；本轮实际模式：{a.last_execution_mode}；工具：{', '.join(a.last_used_tools) or '无'}"+(f"；接口问题：{a.last_error}" if a.last_error else '')
    def outputs(a,h,answer='',tts=False):
        audio=None
        if tts and answer:
            from voice import synthesize_to_file
            audio=synthesize_to_file(answer)
        return a,h,map_html(a),status(a),audio
    def record(a,q,ans):
        if os.getenv('SAVE_SESSION_LOGS','0')!='1':return
        folder=ROOT/'logs';folder.mkdir(exist_ok=True)
        event={'time':datetime.now(timezone.utc).isoformat(),'map':str(path.name),'mode':a.last_execution_mode,'provider':a.provider,'model':a.model,'location':a.user_location,'selected':a.selected_poi,'question':q,'answer':ans,'tools':a.last_tool_results}
        with (folder/(a.session_id+'.jsonl')).open('a',encoding='utf-8') as f:f.write(json.dumps(event,ensure_ascii=False)+'\n')
    def respond(text,h,a,tts):
        h=list(h or []);text=(text or '').strip()
        if not text:return outputs(a,h)
        ans=a.chat(text);h += [{'role':'user','content':text},{'role':'assistant','content':ans}];record(a,text,ans)
        return outputs(a,h,ans,tts)
    def locate(ident,h,a,tts):
        if not ident:return outputs(a,h)
        p=a.campus.get(ident);a.user_location=p.name
        ans=f'已记录您在「{p.name}」。此位置由您确认，并非实时定位。'
        return outputs(a,list(h or [])+[{'role':'assistant','content':ans}],ans,tts)
    def select(ident,h,a,tts):
        if not ident:return outputs(a,h)
        a.last_used_tools=[];a.last_tool_results=[]
        ans=a.select_poi(ident)
        return outputs(a,list(h or [])+[{'role':'assistant','content':ans}],ans,tts)
    def reset(a):
        a=fresh()
        return (*outputs(a,[], '已清空全部会话状态。'),None,None)
    with gr.Blocks(title='西工大长安校区地图探索 Agent') as demo:
        gr.Markdown('# 西北工业大学长安校区 · 地图探索\n公开OSM快照，建筑名称、入口和无障碍信息待核实。距离为地图代表点间直线距离，不能作为行走路线。')
        state=gr.State(value=fresh)
        with gr.Row():
            with gr.Column(scale=4):
                chatbot=gr.Chatbot(height=330,label='地图对话')
                with gr.Row():
                    loc=gr.Dropdown(choices=choices,label='确认我所在的地点')
                    loc_btn=gr.Button('确认位置')
                with gr.Row():
                    target=gr.Dropdown(choices=choices,label='选择要探索的地点')
                    pick=gr.Button('选中地点')
                text=gr.Textbox(label='输入问题（可用Windows的Win+H听写）',placeholder='先确认位置，再问：图书馆在哪？')
                send=gr.Button('发送',variant='primary')
                with gr.Row():
                    what=gr.Button('这是哪里？');near=gr.Button('选中地点附近有什么？');far=gr.Button('离我多远？')
                tts=gr.Checkbox(value=False,label='语音播报（需要网络或本地语音引擎）')
                audio=gr.Audio(type='filepath',autoplay=True,label='回答语音')
                status_box=gr.Textbox(value=status(preview),label='执行状态',interactive=False)
                clear=gr.Button('清空全部会话和位置')
                gr.Markdown('模型配置在 llm_secrets.env；接口失败会显示规则回退。默认不保存对话；研究记录可在配置中设置 SAVE_SESSION_LOGS=1。')
            with gr.Column(scale=6):
                view=gr.HTML(value=map_html(preview))
                gr.Markdown('地图数据：WGS84 GeoJSON；计算投影：WGS84 / UTM 49N。建筑代表点不等于可通行入口。')
        out=[state,chatbot,view,status_box,audio]
        send.click(respond,[text,chatbot,state,tts],out).then(lambda:'',outputs=text)
        text.submit(respond,[text,chatbot,state,tts],out).then(lambda:'',outputs=text)
        loc_btn.click(locate,[loc,chatbot,state,tts],out)
        pick.click(select,[target,chatbot,state,tts],out)
        def qwhat(h,a,t):return respond('这是哪里？',h,a,t)
        def qnear(h,a,t):return respond((a.selected_poi+'附近有什么？') if a.selected_poi else '附近有什么？',h,a,t)
        def qfar(h,a,t):return respond('离我多远？',h,a,t)
        what.click(qwhat,[chatbot,state,tts],out);near.click(qnear,[chatbot,state,tts],out);far.click(qfar,[chatbot,state,tts],out)
        clear.click(reset,[state],out+[loc,target])
    return demo

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('--map');ap.add_argument('--port',type=int,default=7860);ap.add_argument('--provider',default=None);ap.add_argument('--rule',action='store_true');ap.add_argument('--llm',action='store_true');ap.add_argument('--location',default=None)
    args=ap.parse_args()
    build_ui(args.map,args.location,'rule' if args.rule else 'llm' if args.llm else 'auto',args.provider).launch(server_name='127.0.0.1',server_port=args.port,inbrowser=True)
