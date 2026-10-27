"""
免费/低成本 LLM 配置（OpenAI 兼容接口）

推荐（按稳定性）：
1. Groq      — 完全免费额度，免信用卡，国外快
2. DeepSeek  — 国内可用，价格极低/有赠金
3. SiliconFlow — 国内，部分模型免费
4. 通义千问 DashScope — 国内，有免费额度

环境变量（任选其一套）：
  LLM_PROVIDER=groq|deepseek|siliconflow|dashscope|openai|custom
  LLM_API_KEY=...
  LLM_MODEL=...          # 可选，用默认
  LLM_API_BASE=...       # custom 时必填

也可在同目录放 llm_secrets.env（不要提交 git）：
  LLM_PROVIDER=groq
  LLM_API_KEY=gsk_xxx
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

# 加载本地 secrets
_secrets = Path(__file__).resolve().parent / "llm_secrets.env"
if _secrets.exists():
    for line in _secrets.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

PROVIDERS: Dict[str, Dict[str, Any]] = {
    "groq": {
        "name": "Groq（推荐·免费）",
        "api_base": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "key_env": ["LLM_API_KEY", "GROQ_API_KEY"],
        "signup": "https://console.groq.com/keys",
        "notes": "免信用卡，工具调用稳定，国外节点",
    },
    "deepseek": {
        "name": "DeepSeek（国内友好）",
        "api_base": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
        "key_env": ["LLM_API_KEY", "DEEPSEEK_API_KEY"],
        "signup": "https://platform.deepseek.com/api_keys",
        "notes": "中文强，有赠送额度",
    },
    "siliconflow": {
        "name": "硅基流动 SiliconFlow",
        "api_base": "https://api.siliconflow.cn/v1",
        "default_model": "Qwen/Qwen2.5-7B-Instruct",  # 硅基流动常有免费额度
        # 也可试: THUDM/glm-4-9b-chat
        "key_env": ["LLM_API_KEY", "SILICONFLOW_API_KEY"],
        "signup": "https://cloud.siliconflow.cn/account/ak",
        "notes": "国内直连，新用户有免费额度，推荐完整版",
    },
    "dashscope": {
        "name": "通义千问 DashScope",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-turbo",  # 便宜/常有免费额度；也可用 qwen-plus
        "key_env": ["LLM_API_KEY", "DASHSCOPE_API_KEY"],
        "signup": "https://dashscope.console.aliyun.com/apiKey",
        "notes": "阿里云百炼，新用户通常有免费Token（以控制台为准）",
    },
    "openai": {
        "name": "OpenAI",
        "api_base": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "key_env": ["LLM_API_KEY", "OPENAI_API_KEY"],
        "signup": "https://platform.openai.com/api-keys",
        "notes": "需付费",
    },
    "ollama": {
        "name": "Ollama 本地（完全免费）",
        "api_base": "http://127.0.0.1:11434/v1",
        "default_model": "qwen2.5:7b",
        "key_env": ["LLM_API_KEY", "OLLAMA_API_KEY"],
        "signup": "https://ollama.com/download",
        "notes": "本机运行，不收token费；需先 ollama pull qwen2.5:7b",
    },
    "doubao": {
        "name": "豆包（火山方舟）",
        "api_base": "https://ark.cn-beijing.volces.com/api/v3",
        "default_model": "doubao-pro-32k",  # 控制台创建接入点后改成 ep-xxx
        "key_env": ["LLM_API_KEY", "ARK_API_KEY", "DOUBAO_API_KEY"],
        "signup": "https://console.volcengine.com/ark",
        "notes": "新用户有免费推理额度；模型名需用方舟「接入点 ID」",
    },
    "custom": {
        "name": "自定义 OpenAI 兼容",
        "api_base": os.getenv("LLM_API_BASE", "http://127.0.0.1:8000/v1"),
        "default_model": os.getenv("LLM_MODEL", "default"),
        "key_env": ["LLM_API_KEY", "OPENAI_API_KEY"],
        "signup": "",
        "notes": "本地 vLLM / Ollama 等",
    },
}


def resolve_llm_config(
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    api_base: Optional[str] = None,
) -> Dict[str, Any]:
    """解析最终使用的 provider / key / model / base。"""
    prov = (provider or os.getenv("LLM_PROVIDER", "deepseek")).lower().strip()
    if prov not in PROVIDERS:
        prov = "groq"
    meta = PROVIDERS[prov]

    key = api_key or ""
    if not key:
        for env_name in meta["key_env"]:
            if env_name == "LLM_API_KEY" and prov != os.getenv("LLM_PROVIDER", "deepseek").lower().strip():
                continue
            key = os.getenv(env_name, "")
            if key:
                break
    if not key:
        key = os.getenv("OPENAI_API_KEY", "") if prov == "openai" else ""

    base = api_base or os.getenv("LLM_API_BASE") or meta["api_base"]
    mdl = model or os.getenv("LLM_MODEL") or meta["default_model"]

    # Ollama 本地不需要真 Key；custom 可能也不需要
    ready = bool(key) or prov in ("ollama", "custom")
    if prov == "ollama" and not key:
        key = "ollama"  # openai 客户端要求非空

    return {
        "provider": prov,
        "provider_name": meta["name"],
        "api_base": base,
        "api_key": key,
        "model": mdl,
        "signup": meta.get("signup", ""),
        "notes": meta.get("notes", ""),
        "ready": ready,
    }


def describe_providers() -> str:
    lines = ["可用 LLM 提供商（均 OpenAI 兼容）："]
    for k, v in PROVIDERS.items():
        lines.append(f"  - {k}: {v['name']} | 默认模型 {v['default_model']} | {v['notes']}")
        if v.get("signup"):
            lines.append(f"      申请 Key: {v['signup']}")
    return "\n".join(lines)
