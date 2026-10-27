#!/usr/bin/env python3
"""
GUI-VLM 地图 Agent 演示
用法：
  python demo.py                  # 交互 CLI（规则模式，离线）
  python demo.py --llm            # 使用 OPENAI_API_KEY 的 LLM 模式
  python demo.py --test           # 跑通核心用例
  python demo.py --gradio         # 启动简易 Web UI（需 gradio）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 保证同目录可 import
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import build_default_agent


DEMO_QUERIES = [
    "地图上有哪些地点？",
    "图书馆在哪？",
    "图书馆附近有什么？",
    "南门到图书馆多远？",
    "图书馆和食堂哪个离南门更近？",
    "教学楼A在南门的什么方向？",
    "体育馆旁边有什么？",
]


def run_cli(agent):
    print("=" * 50)
    print("  面向盲人的 GUI-VLM 地图对话助手")
    print("  输入问题，或 q 退出。示例：图书馆在哪？")
    print("=" * 50)
    while True:
        try:
            text = input("\n您：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break
        if not text:
            continue
        if text.lower() in ("q", "quit", "exit", "退出"):
            print("再见。")
            break
        ans = agent.chat(text)
        print(f"助手：{ans}")


def run_tests(agent):
    print("=== 核心用例自动测试 ===\n")
    ok = 0
    for q in DEMO_QUERIES:
        ans = agent.chat(q)
        print(f"Q: {q}")
        print(f"A: {ans}\n")
        # 简单成功判定：非空且不是「无法」开头的失败句
        if ans and "无法" not in ans[:10]:
            ok += 1
    print(f"通过 {ok}/{len(DEMO_QUERIES)} 条（启发式）。")
    return ok == len(DEMO_QUERIES)


def run_gradio(agent):
    try:
        import gradio as gr
    except ImportError:
        print("请先安装：pip install gradio")
        sys.exit(1)

    def respond(message, history):
        return agent.chat(message)

    demo = gr.ChatInterface(
        respond,
        title="面向盲人的 GUI-VLM 地图 Agent",
        description="确定性空间工具 + 对话导航。示例：图书馆在哪？ / 图书馆附近有什么？ / 哪个离南门更近？",
        examples=DEMO_QUERIES,
    )
    demo.launch(server_name="0.0.0.0", server_port=7860)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="使用 LLM function-calling")
    parser.add_argument("--test", action="store_true", help="跑核心用例")
    parser.add_argument("--gradio", action="store_true", help="启动 Web UI")
    parser.add_argument("--map", default=None, help="自定义地图 JSON 路径")
    args = parser.parse_args()

    mode = "llm" if args.llm else "rule"
    if args.map:
        from agent import MapAgent
        agent = MapAgent(map_path=args.map, mode=mode)
    else:
        agent = build_default_agent(mode=mode)
    print(f"[模式] {mode} | POI 数量: {len(agent.campus.all_pois())}")

    if args.test:
        success = run_tests(agent)
        sys.exit(0 if success else 1)
    if args.gradio:
        run_gradio(agent)
    else:
        run_cli(agent)


if __name__ == "__main__":
    main()
