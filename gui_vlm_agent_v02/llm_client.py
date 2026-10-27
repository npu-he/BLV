"""
稳健的 OpenAI 兼容 Chat + Tools 客户端。
优先 openai SDK；失败则 urllib。全程硬超时，避免界面一直转圈。
"""

from __future__ import annotations

import json
import socket
import ssl
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


class LLMTimeoutError(TimeoutError):
    pass



def chat_completions(
    *,
    api_base: str,
    api_key: str,
    model: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: str = "auto",
    temperature: float = 0.2,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """返回 {content, tool_calls}。优先 urllib，避免 Anaconda 下 httpx/brotli 冲突。"""
    last_err: Optional[Exception] = None

    # 1) urllib（不依赖 httpx/brotli，Anaconda 更稳）
    try:
        return _urllib_chat(
            api_base=api_base,
            api_key=api_key,
            model=model,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            timeout=timeout,
        )
    except LLMTimeoutError:
        raise
    except Exception as e:
        last_err = e
        err_s = str(e)
        # 明确计费/鉴权错误，不要再试 SDK 掩盖
        if "402" in err_s or "Payment Required" in err_s:
            raise RuntimeError(
                "接口返回 402 Payment Required：当前账号需要充值或没有免费额度。"
                "请换免费提供商（硅基流动 siliconflow）或给 DeepSeek 充值。"
            ) from e
        if "401" in err_s or "Unauthorized" in err_s:
            raise RuntimeError("接口返回 401：API Key 无效，请检查 llm_secrets.env") from e

    # 2) openai SDK 兜底
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=api_base.rstrip("/"), timeout=timeout, max_retries=0)
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        resp = client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        tool_calls = []
        if getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                tool_calls.append(
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments or "{}",
                    }
                )
        return {"content": (msg.content or "").strip(), "tool_calls": tool_calls}
    except Exception as e2:
        raise RuntimeError(f"LLM 调用失败。urllib: {last_err}; SDK: {e2}") from e2


def _urllib_chat(
    *,
    api_base: str,
    api_key: str,
    model: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]],
    tool_choice: str,
    temperature: float,
    timeout: float,
) -> Dict[str, Any]:
    url = api_base.rstrip("/") + "/chat/completions"
    body: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = tool_choice

    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read().decode("utf-8")
    except socket.timeout as e:
        raise LLMTimeoutError(f"连接 {api_base} 超过 {timeout}s") from e
    except urllib.error.URLError as e:
        if isinstance(e.reason, socket.timeout):
            raise LLMTimeoutError(f"连接超时: {e}") from e
        raise

    payload = json.loads(raw)
    if "error" in payload:
        raise RuntimeError(str(payload["error"]))
    msg = payload["choices"][0]["message"]
    tool_calls = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        tool_calls.append(
            {
                "id": tc.get("id", "call_0"),
                "name": fn.get("name", ""),
                "arguments": fn.get("arguments") or "{}",
            }
        )
    return {"content": (msg.get("content") or "").strip(), "tool_calls": tool_calls}
