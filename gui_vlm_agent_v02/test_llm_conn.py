#!/usr/bin/env python3
"""验证国内 LLM 是否真正跑通（请先配置 llm_secrets.env）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from llm_config import resolve_llm_config, describe_providers
from llm_client import chat_completions
from agent import MapAgent


def main():
    cfg = resolve_llm_config()
    print("=== 当前配置 ===")
    print(f"provider : {cfg['provider']} ({cfg['provider_name']})")
    print(f"api_base : {cfg['api_base']}")
    print(f"model    : {cfg['model']}")
    print(f"key      : {'已设置' if cfg['api_key'] else '未设置'}")
    print(f"ready    : {cfg['ready']}")
    if not cfg["api_key"]:
        print("\n[失败] 没有 API Key。")
        print("免费方案：安装 Ollama → LLM_PROVIDER=ollama（见 llm_secrets.env.example）")
        print("云端千问/硅基等：新用户可能有赠送，用完需付费")
        print("2) copy llm_secrets.env.example llm_secrets.env")
        print("3) 把 sk- 开头的密钥写入 LLM_API_KEY=")
        sys.exit(1)

    print("\n=== 1) 连通性：简单对话 ===")
    try:
        out = chat_completions(
            api_base=cfg["api_base"],
            api_key=cfg["api_key"],
            model=cfg["model"],
            messages=[{"role": "user", "content": "请只回答：好的"}],
            tools=None,
            timeout=30.0,
        )
        print("回复:", out.get("content"))
        print("[OK] 基础对话成功")
    except Exception as e:
        print("[失败] 基础对话:", e)
        print("常见原因：")
        print("  - 402 Payment Required = 要充值（DeepSeek 常见）→ 改用硅基流动免费模型")
        print("  - 401 = Key 填错")
        print("  - 超时 = 网络问题")
        sys.exit(2)

    print("\n=== 2) 工具调用（function calling）===")
    tools = [
        {
            "type": "function",
            "function": {
                "name": "distance",
                "description": "计算两点距离",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "string"},
                        "b": {"type": "string"},
                    },
                    "required": ["a", "b"],
                },
            },
        }
    ]
    try:
        out = chat_completions(
            api_base=cfg["api_base"],
            api_key=cfg["api_key"],
            model=cfg["model"],
            messages=[
                {
                    "role": "system",
                    "content": "必须调用 distance 工具，不要自己编距离。",
                },
                {"role": "user", "content": "南门到图书馆多远？"},
            ],
            tools=tools,
            tool_choice="auto",
            timeout=30.0,
        )
        print("content:", out.get("content"))
        print("tool_calls:", json.dumps(out.get("tool_calls"), ensure_ascii=False))
        if not out.get("tool_calls"):
            print("[警告] 模型没有发起 tool_call，完整版空间推理会受影响")
        else:
            print("[OK] 工具调用成功")
    except Exception as e:
        print("[失败] 工具调用:", e)
        sys.exit(3)

    print("\n=== 3) 完整 Agent 链路 ===")
    agent = MapAgent(
        Path(__file__).parent / "data" / "campus_map.json",
        mode="llm",
        provider=cfg["provider"],
        api_key=cfg["api_key"],
        model=cfg["model"],
        api_base=cfg["api_base"],
    )
    agent.user_location = "南门"
    q = "帮我看看食堂和图书馆哪个离南门更近，用口语说"
    print("Q:", q)
    a = agent.chat(q)
    print("A:", a)
    print("tools used:", agent.last_used_tools)
    if "食堂" in a or "近" in a or "米" in a:
        print("\n[成功] 国内 LLM 完整链路可用，可以给老师演示。")
        sys.exit(0)
    print("\n[注意] 有回复但内容异常，请把上面输出发给开发者。")
    sys.exit(4)


if __name__ == "__main__":
    main()
