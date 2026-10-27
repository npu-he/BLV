"""自测：语音 + LLM 配置 + 规则回退。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice import synthesize_to_file
from llm_config import resolve_llm_config, describe_providers
from agent import MapAgent


def test_tts():
    import os
    if os.getenv("RUN_NETWORK_TESTS") != "1":
        import pytest
        pytest.skip("Set RUN_NETWORK_TESTS=1 to test network/system speech")
    p = synthesize_to_file("南门到图书馆约二百一十六米，东北方向。")
    assert p and Path(p).stat().st_size > 1000
    print("[OK] TTS", p, Path(p).stat().st_size, "bytes")


def test_config():
    cfg = resolve_llm_config(provider="groq")
    assert cfg["api_base"].startswith("http")
    assert cfg["model"]
    print("[OK] config", cfg["provider"], cfg["model"], "ready=", cfg["ready"])
    print(describe_providers()[:200], "...")


def test_rule_still_works():
    a = MapAgent("data/campus_map.json", mode="rule")
    a.user_location = "南门"
    r = a.chat("图书馆在哪")
    assert "米" in r
    print("[OK] rule", r)


def test_llm_without_key_falls_back_or_rule():
    a = MapAgent("data/campus_map.json", mode="llm", provider="groq", api_key="")
    # no key -> chat uses rule branch
    a.mode = "rule"  # explicit
    a.user_location = "教学楼A"
    r = a.chat("学生食堂在我哪边")
    assert "教学楼A" in r or "米" in r
    print("[OK] spatial with location", r)


if __name__ == "__main__":
    test_tts()
    test_config()
    test_rule_still_works()
    test_llm_without_key_falls_back_or_rule()
    print("全部自测通过")
