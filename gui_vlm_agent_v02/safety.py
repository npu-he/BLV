"""
安全与错误传播阻断（轻量版）
---------------------------------
目标：
1. 工具结果置信度/唯一性检查
2. 多轮对话中的矛盾检测（简单记忆）
3. 高风险回答拦截（距离/方位不可靠时）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FactMemory:
    """会话内已确认的空间事实（仅工具返回的 ok=True 结果）。"""
    facts: List[Dict[str, Any]] = field(default_factory=list)

    def add(self, tool_name: str, result: Dict[str, Any]) -> None:
        if not result.get("ok"):
            return
        self.facts.append({"tool": tool_name, "result": result})

    def recent_messages(self, n: int = 6) -> List[str]:
        msgs = []
        for f in self.facts[-n:]:
            m = f["result"].get("message")
            if m:
                msgs.append(m)
        return msgs


class SafetyGate:
    """
    规则 + 关键词的轻量风险路由。
    后续可替换为小型审查模型。
    """

    RISK_KEYWORDS = [
        "不确定", "可能", "大概", "估计", "我觉得", "好像",
        "也许", "或许", "应该是", "差不多",
    ]

    def __init__(self, memory: Optional[FactMemory] = None):
        self.memory = memory or FactMemory()

    def check_tool_result(self, tool_name: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        检查单次工具结果。
        返回：{allow: bool, reason: str, rewritten?: str}
        """
        if not result.get("ok"):
            return {
                "allow": False,
                "reason": "tool_failed",
                "advice": "请明确地点名称，或先列出地图上的地点。",
                "user_message": result.get("message", "查询失败，无法给出可靠空间信息。"),
            }

        # identify 多匹配 → 不直接给出方位/距离，要求澄清
        if tool_name == "identify" and len(result.get("matches", [])) > 1:
            names = "、".join(m["name"] for m in result["matches"])
            return {
                "allow": False,
                "reason": "ambiguous_entity",
                "advice": "存在多个匹配，需用户澄清。",
                "user_message": f"「{result.get('query')}」可能指：{names}。请确认您指的是哪一个？",
            }

        self.memory.add(tool_name, result)
        return {"allow": True, "reason": "ok"}

    def check_final_answer(self, answer: str, used_tools: List[str], tool_results=None) -> Dict[str, Any]:
        """
        对最终自然语言回答做轻量审查。
        - 若回答含模糊词且未调用过确定性工具 → 拦截
        - 若回答声称具体距离/方位但本轮未调 distance/relation → 警告
        """
        lower = answer.lower()
        has_risk_word = any(k in answer for k in self.RISK_KEYWORDS)

        # 强空间断言：明确报距离数字或“XX方向”，避免 POI 名里的「南门」误伤
        import re
        strong_spatial = bool(
            re.search(r"\d+(\.\d+)?\s*米", answer)
            or re.search(r"[东南西北]{1,2}(?:方向|边|侧|面)", answer)
            or any(w in answer for w in ["更近", "更远", "直线距离"])
        )
        used_spatial = any(
            t in used_tools
            for t in ("distance", "relation", "nearby", "compare_distance")
        )

        if tool_results is not None:
            used_spatial = any(x["tool"] in {"distance", "relation", "nearby", "compare_distance"} and x["result"].get("ok") for x in tool_results)
        if strong_spatial and not used_spatial:
            return {
                "allow": False,
                "reason": "spatial_claim_without_tool",
                "user_message": (
                    "为了安全，关于距离和方位的信息必须来自地图计算，"
                    "当前回答缺少可靠数据支撑，请重新提问或换一种问法。"
                ),
            }

        if has_risk_word and not used_tools:
            return {
                "allow": False,
                "reason": "hedging_without_evidence",
                "user_message": "当前信息不足以给出可靠回答，建议先确认地点名称。",
            }

        return {"allow": True, "reason": "ok"}

    def contradiction_hint(self) -> Optional[str]:
        """简单返回近期事实摘要，供 Agent 系统提示使用。"""
        msgs = self.memory.recent_messages(4)
        if not msgs:
            return None
        return "近期已确认的空间事实：\n- " + "\n- ".join(msgs)
