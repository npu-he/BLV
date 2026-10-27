"""
面向盲人的 GUI-VLM Map Agent
---------------------------------
架构：用户自然语言 → (rule | llm) → 确定性 SpatialTools → SafetyGate → 口语回答

BLV 设计要点（面向真实用户实验）：
- 必须先有「我在哪」（user_location），所有「我/这里」解析到该点
- 回答短句、适合听读（VoiceOver / 读屏）
- 方位用东南西北；距离给米数；禁止臆测
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from safety import FactMemory, SafetyGate
from spatial_tools import CampusMap, SpatialTools, TOOL_SCHEMAS, dispatch_tool


SYSTEM_PROMPT = """你是「面向盲人的 GUI-VLM 地图助手」，帮助视障用户通过对话理解校园地图。

【硬性规则】
1. 距离、方位、远近、附近关系必须调用工具计算，禁止自己猜数字或方向。
2. 回答简短、口语化，适合屏幕阅读器朗读（一两句为主，不要表格）。
3. 用户说的「我」「这里」「这儿」「当前位置」= 系统提供的「用户当前位置」。
4. 地点不唯一时先澄清；只使用地图上真实存在的地点。
5. 多轮时参考已确认事实，发现前后矛盾要主动指出。

【可用工具】
identify, get_position, distance, relation, nearby, compare_distance, list_pois
"""


class MapAgent:
    def __init__(
        self,
        map_path: str | Path,
        mode: str = "rule",
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        enable_safety: bool = False,
    ):
        self.campus = CampusMap.from_json(map_path)
        self.tools = SpatialTools(self.campus)
        self.memory = FactMemory()
        self.safety = SafetyGate(self.memory)
        # Benchmark 阶段默认关闭最终回答拦截，便于收集错误再设计 Safety
        self.enable_safety = enable_safety or os.getenv("ENABLE_SAFETY", "").lower() in ("1", "true", "yes")
        self.history: List[Dict[str, str]] = []
        self.last_used_tools: List[str] = []
        self.last_execution_mode = "none"
        self.last_error = None
        self.last_tool_results = []
        entrances = [p for p in self.campus.all_pois() if p.type == "entrance"]
        self.default_ref = entrances[0].name if entrances else self.campus.all_pois()[0].name
        self.user_location: Optional[str] = None
        self.last_mentioned: Optional[str] = None
        self.selected_poi: Optional[str] = None

        # LLM 配置（免费提供商优先）
        try:
            from llm_config import resolve_llm_config
            cfg = resolve_llm_config(provider=provider, api_key=api_key, model=model, api_base=api_base)
        except Exception:
            cfg = {
                "provider": "openai",
                "api_base": api_base or os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
                "api_key": api_key or os.getenv("OPENAI_API_KEY", ""),
                "model": model or "gpt-4o-mini",
                "provider_name": "openai",
                "ready": bool(api_key or os.getenv("OPENAI_API_KEY")),
            }
        self.llm_cfg = cfg
        self.api_base = cfg["api_base"]
        self.api_key = cfg["api_key"]
        self.model = cfg["model"]
        self.provider = cfg.get("provider", "unknown")
        # mode: rule | llm | auto（有 key 用 llm，失败回退 rule）
        if mode == "auto":
            self.mode = "llm" if cfg.get("ready") else "rule"
        else:
            self.mode = mode

    # ---------- 指代消解 ----------
    def _resolve_ref(self, name: str) -> str:
        """把「我/这里/那儿」等解析成真实 POI 名。"""
        if not name:
            return name
        n = name.strip()
        # 去除语气词
        n = re.sub(r"^(在|到|离|距离)", "", n)
        n = n.strip()
        self_refs = {"我", "这里", "这儿", "当前位置", "我所在", "我这", "本人位置", "我这边"}
        if n in self_refs or n.startswith("我的") or n.startswith("我这"):
            if self.user_location:
                return self.user_location
            return self.default_ref
        if n in {"那里", "那儿", "那栋楼", "那个地方", "刚才那个", "这个", "这", "该地点"} and (self.selected_poi or self.last_mentioned):
            return self.selected_poi or self.last_mentioned
        return n

    def _note_mention(self, *names: str) -> None:
        for n in names:
            if not n:
                continue
            if n in {"我", "这里", "这儿"}:
                continue
            # 若能 identify 成功则记下
            r = self.tools.identify(n)
            if r.get("ok") and r.get("matches"):
                self.last_mentioned = r["matches"][0]["name"]
                return


    def select_poi(self, name_or_id: str) -> str:
        """模拟盲人在地图上点选一处（触摸/焦点落到该点）。"""
        ident = self.tools.identify(name_or_id)
        if not ident.get("ok") or not ident.get("matches"):
            return ident.get("message", "未找到该地点，无法选中。")
        if len(ident["matches"]) > 1:
            names = "、".join(m["name"] for m in ident["matches"])
            return f"不唯一：{names}。请说全名再选。"
        poi_name = ident["matches"][0]["name"]
        self.selected_poi = poi_name
        self.last_mentioned = poi_name
        info = ident["matches"][0]
        # 相对用户位置给一句方位（若有）
        extra = ""
        if self.user_location and self.user_location != poi_name:
            rel = self._call("relation", {"a": poi_name, "b": self.user_location})
            if rel.get("ok"):
                extra = " " + rel.get("message", "")
            else:
                # _call 已记工具；若失败不追加
                extra = ""
                self.last_used_tools = [t for t in self.last_used_tools if t != "relation"]
        return (
            f"已选中地图上的「{poi_name}」（{info.get('type', '')}）。"
            f"您可以问：这是哪里？附近有什么？离我多远？"
            + (f" {extra}" if extra else "")
        )

    # ---------- 主入口 ----------
    def chat(self, user_text: str) -> str:
        self.last_used_tools = []
        self.last_tool_results = []
        self.last_error = None
        self.last_execution_mode = self.mode
        user_text = user_text.strip()
        if not user_text:
            return "请说出您想了解的地点或问题。"

        # 未设位置时，遇到「我/这里」主动提示
        if self.user_location is None and re.search(r"(我|这里|这儿|当前位置)", user_text) and not (self.selected_poi and re.search(r"这是哪里|这里是什么|这是什么", user_text)):
            if not re.search(r"我在|我现在在|当前位置是", user_text):
                return (
                    f"请先告诉我您在哪里，例如「我在{self.default_ref}」。"
                    f"也可以在界面上选择当前位置。设好后就能问「食堂在我哪边」「附近有什么」。"
                )

        # Update location before creating LLM prompts. Split a following question at Chinese/ASCII punctuation.
        m_loc = re.search(r"(?:我现在在|我在|当前位置是|把位置设为)([^，,。.?？!！]+)", user_text)
        if m_loc:
            ident = self.tools.identify(m_loc.group(1).strip())
            if not ident.get("ok") or len(ident.get("matches", [])) != 1:
                return "当前位置未能唯一确认，请使用地图中的完整地点名称。"
            self.user_location = ident["matches"][0]["name"]
            rest = user_text[m_loc.end():].strip(" ，,。.?？!！")
            if not rest:
                return f"已记录您在「{self.user_location}」。此位置由您提供，并非实时定位。"
            user_text = rest
        if self.user_location is None and re.search(r"^(附近|旁边|周围)|在哪|在哪里", user_text):
            return "请先确认当前位置，或明确给出参考地点。"
        if self.mode == "llm" and not self.api_key:
            self.last_execution_mode = "rule_fallback"
            self.last_error = "未配置当前提供商的API密钥"
        if self.mode == "llm" and self.api_key:
            try:
                answer = self._chat_llm(user_text)
            except Exception as e:
                self.last_execution_mode = "rule_fallback"
                self.last_error = type(e).__name__
                print("[MapAgent] LLM调用失败，回退规则模式；详情请在本地检查接口配置。")
                answer = self._chat_rule(user_text)
                # 超时提示短一点，方便语音播报
                if "超时" in str(e) or "timeout" in str(e).lower() or "Timeout" in type(e).__name__:
                    answer = answer  # 规则结果即可，不追加长说明
                else:
                    answer = answer + "。网络不稳定时已用本地规则计算。"
        else:
            answer = self._chat_rule(user_text)

        if self.enable_safety:
            # Evidence-first demo policy: render successful spatial facts directly.
            # This is a deterministic baseline, not a learned risk-routing method.
            spatial = [r["result"] for r in self.last_tool_results if r["tool"] in {"distance", "relation", "nearby", "compare_distance"} and r["result"].get("ok")]
            if self.mode == "llm" and spatial:
                answer = " ".join(dict.fromkeys(r["message"] for r in spatial[-3:]))
            gate = self.safety.check_final_answer(answer, self.last_used_tools, self.last_tool_results)
            if not gate["allow"]:
                answer = gate["user_message"]

        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": answer})
        return answer

    def _call(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        # 参数里的地点名做指代消解
        resolved = {}
        for k, v in args.items():
            if isinstance(v, str) and k in {
                "a", "b", "query", "center", "target", "from_name", "to_name"
            }:
                resolved[k] = self._resolve_ref(v)
            else:
                resolved[k] = v
        self.last_used_tools.append(name)
        result = dispatch_tool(self.tools, name, resolved)
        self.last_tool_results.append({"tool": name, "arguments": resolved, "result": result})
        gate = self.safety.check_tool_result(name, result)
        if not gate["allow"]:
            # 歧义澄清仍返回（利于交互）；其他在关闭 safety 时放行原始结果
            if gate.get("reason") == "ambiguous_entity" or self.enable_safety:
                return {"ok": False, "message": gate["user_message"]}
            # 关闭 safety：工具失败仍把原始 message 交回去，不改写为安全套话
        # 记录提及
        for key in ("from", "to", "subject", "reference", "center", "closer", "name"):
            obj = result.get(key)
            if isinstance(obj, dict) and obj.get("name"):
                self.last_mentioned = obj["name"]
        if result.get("name"):
            self.last_mentioned = result["name"]
        return result

    # ---------- Rule 模式 ----------
    def _chat_rule(self, text: str) -> str:
        t = text

        # 设定位置：我在XX
        m_loc = re.search(r"(?:我在|我现在在|当前位置是|把位置设为)(.+?)(?:[。.?？!！]|$)", t)
        if m_loc:
            place = self._resolve_ref(m_loc.group(1).strip())
            # 若 place 仍是「我」类，失败
            ident = self._call("identify", {"query": place})
            if ident.get("ok") and ident.get("matches"):
                self.user_location = ident["matches"][0]["name"]
                rest = t[m_loc.end() :].strip(" 。.？?！!,，")
                if not rest:
                    return (
                        f"好的，已记录您在「{self.user_location}」。"
                        f"可以问：附近有什么？学生食堂在我哪边？图书馆离我多远？"
                    )
                # 同句还有后续问题，继续处理 rest
                t = rest
            else:
                return ident.get("message", "未能确认您的位置，请换一个地图上的地点名称。")

        # 寒暄（不要当成空间问题）
        if re.fullmatch(r"(好的?|谢谢|感谢|嗯|哦|知道了|行|可以)[。.!！？]?|好的谢谢你?", t.strip()):
            return "好的。您还可以问：附近有什么、某某在我哪边、离我多远。"

        # 我的北边/东边有什么（以当前位置为中心，筛方位）
        m = re.search(r"(?:我的?)?(东|南|西|北)(?:边|面|侧|方)?(?:还有|有)?(?:什么|哪些)?(?:设施|地方|建筑|点)?", t)
        if m and ("有" in t or "啥" in t or "哪些" in t or "什么" in t):
            direction = m.group(1)
            center = self.user_location or self.default_ref
            r = self._call("nearby", {"center": center, "radius_m": 400, "top_k": 100})
            if not r.get("ok"):
                # 退化为 list + relation
                pois = [p.name for p in self.campus.all_pois() if p.name != center]
                hits = []
                for name in pois:
                    rel = self._call("relation", {"a": name, "b": center})
                    if rel.get("ok") and direction in (rel.get("message") or ""):
                        hits.append(rel.get("message"))
                if hits:
                    return f"在您（{center}）的{direction}侧，例如：" + "；".join(hits[:5])
                return f"暂时没有在{center}的{direction}侧找到明确标注的地点。"
            # 用 relation 过滤 nearby 列表
            names = []
            for item in (r.get("nearby") or []):
                nm = item.get("name")
                if not nm or nm == center:
                    continue
                rel = self._call("relation", {"a": nm, "b": center})
                msg = rel.get("message") or ""
                if direction in msg:
                    names.append(f"{nm}（{msg}）")
            if names:
                return f"在您所在的{center}的{direction}侧，有：" + "；".join(names[:6])
            return f"以{center}为中心附近有：" + r.get("message", "") + f"。其中明确在{direction}侧的点较少，可再问具体建筑名。"

        # 点选查询：这是哪里 / 这是什么（依赖 selected_poi 或 last_mentioned）
        if re.search(r"(这是哪里|这是哪儿|这是什么|这是啥|这里是什么|选中的是什么|这个地方是什么)", t):
            target = self.selected_poi or self.last_mentioned
            if not target:
                return "您还没有在地图上点选地点。请先点选一处，或直接说地点名称。"
            r = self._call("identify", {"query": target})
            if not r.get("ok"):
                return r.get("message", "无法识别该点。")
            info = r["matches"][0]
            msg = f"这里是「{info['name']}」，类型：{info['type']}。"
            if self.user_location and self.user_location != info["name"]:
                rel = self._call("relation", {"a": info["name"], "b": self.user_location})
                if rel.get("ok"):
                    msg += rel.get("message", "")
            pos = self._call("get_position", {"query": info["name"]})
            if pos.get("ok"):
                pass  # Do not read internal projected coordinates to users.
            return msg

        # 我在哪
        if re.search(r"我在哪|我在哪里|我的位置|当前位置", t) and "设" not in t:
            if self.user_location:
                return f"根据记录，您现在在「{self.user_location}」。"
            return f"还没有设定位置。请说「我在{self.default_ref}」，或在界面选择。"

        # list
        if re.search(r"(有哪些地点|列出|全部地点|地图上有什么|有什么地方)", t):
            r = self._call("list_pois", {})
            return r.get("message", str(r))

        # 附近（无主语 → 当前位置）
        if re.match(r"^(附近|旁边|周围)(有什么|有哪些|是什么)?[?？。!！]*$", t.strip()) or t.strip() in (
            "附近有什么",
            "附近有哪些",
            "旁边有什么",
        ):
            center = self.user_location or self.default_ref
            r = self._call("nearby", {"center": center})
            return f"以您所在的{center}为中心，" + r.get("message", str(r))

        # compare：A和B哪个离C更近 / 哪个离我更近
        m = re.search(r"(.+?)和(.+?)(?:哪个|谁).*(?:更近|近)", t)
        if m:
            a, b = self._resolve_ref(m.group(1)), self._resolve_ref(m.group(2))
            target = self.user_location or self.default_ref
            m2 = re.search(r"(?:离|距离|到|相对)(.+?)(?:更近|近|远)", t)
            if m2:
                target = self._resolve_ref(m2.group(1).strip())
            self._note_mention(a, b, target)
            r = self._call("compare_distance", {"target": target, "a": a, "b": b})
            return r.get("message", str(r))

        # XX附近
        m = re.search(r"(.+?)(?:附近|旁边|周围)(?:有什么|有哪些|是什么)?", t)
        if m and "和" not in m.group(1):
            center = self._resolve_ref(m.group(1).strip())
            center = re.sub(r"^在", "", center)
            self._note_mention(center)
            r = self._call("nearby", {"center": center})
            return r.get("message", str(r))

        # 距离：离我多远（指选中点或最近提到的）
        if re.search(r"^(?:这个|它|该地点)?(?:离我|距离我|到我这)(?:有)?(?:多远|多少米)", t.strip()) or t.strip() in (
            "离我多远", "距离我多远", "有多远",
        ):
            a = self.selected_poi or self.last_mentioned
            if not a:
                return "请先点选或提到一个地点，再问离您多远。"
            b = self.user_location or self.default_ref
            r = self._call("distance", {"a": a, "b": b})
            return r.get("message", str(r))

        # 距离：A到B多远 / A离我多远 / 我离A多远
        m = re.search(r"(.+?)(?:到|距|离)(.+?)(?:多远|距离|多少米)", t)
        if m:
            a = self._resolve_ref(m.group(1).strip())
            b = self._resolve_ref(m.group(2).strip())
            # 空主语时
            if not a or a in ("", "这个", "它"):
                a = self.selected_poi or self.last_mentioned or a
            self._note_mention(a, b)
            r = self._call("distance", {"a": a, "b": b})
            return r.get("message", str(r))

        # 关系：A在我的哪里 / A在B的什么方向 / A在哪
        # 「学生食堂在我的哪里」「食堂在我哪边」
        m = re.search(
            r"(.+?)在(.+?)的?(东|南|西|北|哪|什么位置|什么地方|何处|什么方向|哪个方向|哪边|哪一侧)",
            t,
        )
        if m:
            a = self._resolve_ref(m.group(1).strip())
            b_raw = m.group(2).strip()
            b = self._resolve_ref(b_raw)
            # 「图书馆在哪」→ b 为哪/什么地方
            if b_raw in ("哪", "什么位置", "什么地方", "何处", "哪边") or b in (
                "哪",
                "什么位置",
                "什么地方",
                "何处",
                "哪边",
            ):
                b = self.user_location or self.default_ref
            self._note_mention(a, b)
            r = self._call("relation", {"a": a, "b": b})
            return r.get("message", str(r))

        m = re.search(r"(.+?)(?:在哪|在哪里|位置|在什么地方|在哪边)", t)
        if m:
            a = self._resolve_ref(m.group(1).strip())
            b = self.user_location or self.default_ref
            self._note_mention(a, b)
            r = self._call("relation", {"a": a, "b": b})
            return r.get("message", str(r))

        # identify fallback
        for p in self.campus.all_pois():
            if p.matches(t) or p.name in t:
                r = self._call("identify", {"query": p.name})
                if r.get("ok") and r["matches"]:
                    info = r["matches"][0]
                    self.last_mentioned = info["name"]
                    return (
                        f"地图上有「{info['name']}」（类型：{info['type']}）。"
                        f"您可以问它在哪、附近有什么，或说「{info['name']}离我多远」。"
                    )

        loc_hint = f"您当前在「{self.user_location}」。" if self.user_location else "请先说「我在南门」设定位置。"
        return (
            loc_hint
            + "例如：附近有什么？学生食堂在我哪边？图书馆离我多远？教学楼A和食堂哪个离我更近？"
        )

    # ---------- LLM 模式 ----------
    def _chat_llm(self, user_text: str) -> str:
        try:
            from llm_client import chat_completions
        except ImportError:
            return self._chat_rule(user_text) + "\n（缺少 llm_client，已回退规则模式。）"

        loc_line = (
            f"用户当前位置：{self.user_location}。"
            if self.user_location
            else f"用户尚未设定位置；若其问「我/这里」，请先请其设定位置（默认参考点 {self.default_ref}）。"
        )
        mention_line = f"最近提到的地点：{self.last_mentioned}。" if self.last_mentioned else ""
        if self.selected_poi:
            mention_line += f"地图点选：{self.selected_poi}。"

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": loc_line + mention_line},
        ]
        hint = self.safety.contradiction_hint()
        if hint:
            messages.append({"role": "system", "content": hint})
        for h in self.history[-8:]:
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": user_text})

        for _ in range(3):
            out = chat_completions(
                api_base=self.api_base,
                api_key=self.api_key,
                model=self.model,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=0.2,
                timeout=20.0,
            )
            if not out.get("tool_calls"):
                return (out.get("content") or "").strip()

            messages.append(
                {
                    "role": "assistant",
                    "content": out.get("content") or "",
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": tc["arguments"]},
                        }
                        for tc in out["tool_calls"]
                    ],
                }
            )
            for tc in out["tool_calls"]:
                name = tc["name"]
                try:
                    args = json.loads(tc.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                for k in list(args.keys()):
                    if isinstance(args[k], str):
                        args[k] = self._resolve_ref(args[k])
                result = self._call(name, args)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        out = chat_completions(
            api_base=self.api_base,
            api_key=self.api_key,
            model=self.model,
            messages=messages,
            tools=None,
            temperature=0.2,
            timeout=20.0,
        )
        return (out.get("content") or "").strip()


def build_default_agent(mode: str = "auto") -> MapAgent:
    root = Path(__file__).resolve().parent
    return MapAgent(map_path=root / "data" / "campus_map.json", mode=mode)
