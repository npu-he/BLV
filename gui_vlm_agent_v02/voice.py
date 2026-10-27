"""
盲人友好语音播报
1) edge-tts（免费，需联网）
2) 失败则 Windows SAPI / pyttsx3（本地，免费）
在 Gradio 中用独立线程跑 asyncio，避免 event loop 冲突。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import tempfile
from pathlib import Path
from typing import Optional

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"


def _edge_tts_async(text: str, out_path: str, voice: str, rate: str) -> None:
    import edge_tts

    async def _run():
        communicate = edge_tts.Communicate(text, voice=voice, rate=rate)
        await asyncio.wait_for(communicate.save(out_path), timeout=12.0)

    asyncio.run(_run())


def _sapi_wav(text: str, out_path: str) -> bool:
    """Windows 自带语音，不依赖外网。"""
    try:
        import pyttsx3

        engine = pyttsx3.init()
        # 尽量选中文 voice
        for v in engine.getProperty("voices"):
            name = (v.name or "") + (v.id or "")
            if "Chinese" in name or "zh" in name.lower() or " Huihui" in name or "Xiaoxiao" in name:
                engine.setProperty("voice", v.id)
                break
        engine.setProperty("rate", 180)
        # pyttsx3 存文件
        engine.save_to_file(text, out_path)
        engine.runAndWait()
        return Path(out_path).exists() and Path(out_path).stat().st_size > 0
    except Exception as e:
        print(f"[voice] SAPI/pyttsx3 失败: {e}")
        return False


def synthesize_to_file(
    text: str,
    out_path: Optional[str] = None,
    voice: str = DEFAULT_VOICE,
    rate: str = "+8%",
) -> Optional[str]:
    text = (text or "").strip()
    if not text:
        return None
    if len(text) > 400:
        text = text[:400] + "……"

    if out_path is None:
        # 优先 mp3；SAPI 用 wav
        fd, out_path = tempfile.mkstemp(suffix=".mp3", prefix="blv_tts_")
        import os

        os.close(fd)

    # 1) edge-tts 在独立线程（避免 Gradio 已有事件循环）
    err1 = None
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_edge_tts_async, text, out_path, voice, rate)
            fut.result(timeout=15)
        if Path(out_path).exists() and Path(out_path).stat().st_size > 0:
            return out_path
    except Exception as e:
        err1 = e
        print(f"[voice] edge-tts 失败: {type(e).__name__}: {e}")

    # 2) 本地 SAPI
    wav_path = str(Path(out_path).with_suffix(".wav"))
    if _sapi_wav(text, wav_path):
        return wav_path

    print(f"[voice] 全部 TTS 失败（edge: {err1}）")
    return None
