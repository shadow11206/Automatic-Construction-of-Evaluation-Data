"""
多平台 VL 模型调用适配层
统一入口 call_vl_model()，按 provider 路由：
- dashscope：委托 video_utils.call_qwen_vl（原生视频理解，原样复用，零改动）
- 其他平台（openai / openrouter / zhipu / custom）：OpenCV 抽帧 → base64 图片
  → OpenAI 兼容 Chat Completions HTTP 接口（requests，不引入各家 SDK）

返回结构与 video_utils.call_qwen_vl 完全一致：
    {"success": bool, "answer": str, "status_code": int, "error": str|None}
"""

import os
import sys
import base64
import logging
from pathlib import Path

import cv2
import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from video_utils import call_qwen_vl, get_video_info, calculate_frame_interval  # noqa: E402

logger = logging.getLogger(__name__)

# OpenAI 兼容接口的默认超时（秒）
HTTP_TIMEOUT = 300
# 抽帧 JPEG 质量（平衡清晰度与请求体积）
JPEG_QUALITY = 85
# 非 dashscope 平台的抽帧上限（图片方式体积大，避免超出模型上下文）
MAX_IMAGES = 32


# ============================================================
# 抽帧工具（OpenAI 兼容平台用）
# ============================================================

def extract_frames_base64(video_path: str, max_frames: int = MAX_IMAGES) -> list:
    """
    从视频中均匀抽取帧并编码为 base64 JPEG

    返回:
        [base64_str, ...]
    """
    info = get_video_info(video_path)
    interval, actual_frames = calculate_frame_interval(info["total_frames"], max_frames)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"无法打开视频文件: {video_path}")

    frames = []
    idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx % interval == 0:
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if ok:
                frames.append(base64.b64encode(buf.tobytes()).decode("ascii"))
        idx += 1
        if len(frames) >= actual_frames:
            break
    cap.release()

    logger.info(f"抽帧完成: {os.path.basename(video_path)}, {len(frames)} 帧, 间隔 {interval}")
    return frames


# ============================================================
# OpenAI 兼容接口调用
# ============================================================

def _call_openai_compatible(video_path: str, prompt_text: str, profile: dict) -> dict:
    """
    通过 OpenAI 兼容 Chat Completions 接口调用多模态模型（抽帧+图片方式）

    profile: {"base_url": str, "api_key": str, "model": str, "max_frames": int}
    """
    base_url = (profile.get("base_url") or "").rstrip("/")
    api_key = profile.get("api_key") or ""
    model = profile.get("model") or ""

    if not base_url:
        return {"success": False, "answer": "", "status_code": 0,
                "error": "未配置 Base URL，请先在设置页填写"}
    if not api_key:
        return {"success": False, "answer": "", "status_code": 0,
                "error": "未配置 API Key，请先在设置页填写"}
    if not model:
        return {"success": False, "answer": "", "status_code": 0,
                "error": "未配置模型名称，请先在设置页填写"}
    if not os.path.exists(video_path):
        return {"success": False, "answer": "", "status_code": 0,
                "error": f"视频文件不存在: {video_path}"}

    try:
        max_frames = min(int(profile.get("max_frames", MAX_IMAGES)), MAX_IMAGES)
        frames = extract_frames_base64(video_path, max_frames)
        if not frames:
            return {"success": False, "answer": "", "status_code": 0,
                    "error": "视频抽帧失败，未提取到任何画面"}

        # 构建 OpenAI 多模态消息：图片序列 + 文本指令
        content = [
            {"type": "text", "text": f"以下是按时间顺序从视频中均匀抽取的 {len(frames)} 帧画面，请将它们作为一个完整视频来理解。"}
        ]
        for b64 in frames:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
            })
        content.append({"type": "text", "text": prompt_text})

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        resp = requests.post(f"{base_url}/chat/completions",
                             json=payload, headers=headers, timeout=HTTP_TIMEOUT)

        if resp.status_code == 200:
            data = resp.json()
            answer = data["choices"][0]["message"]["content"]
            # 部分平台 content 为数组结构
            if isinstance(answer, list):
                answer = "".join(seg.get("text", "") for seg in answer if isinstance(seg, dict))
            return {"success": True, "answer": answer, "status_code": 200, "error": None}

        # 非 200：提取平台错误信息
        try:
            err_msg = resp.json().get("error", {}).get("message", resp.text[:300])
        except ValueError:
            err_msg = resp.text[:300]
        return {"success": False, "answer": "", "status_code": resp.status_code,
                "error": f"API 调用失败({resp.status_code}): {err_msg}"}

    except requests.exceptions.Timeout:
        return {"success": False, "answer": "", "status_code": -1,
                "error": f"请求超时（>{HTTP_TIMEOUT}s）"}
    except Exception as e:
        return {"success": False, "answer": "", "status_code": -1,
                "error": f"异常: {str(e)}"}


# ============================================================
# 统一入口
# ============================================================

def call_vl_model(video_path: str, prompt_text: str, profile: dict) -> dict:
    """
    按 profile["provider"] 路由到对应调用方式

    profile 字段: provider / api_key / base_url / model / max_frames
    返回结构与 video_utils.call_qwen_vl 一致
    """
    provider = profile.get("provider", "dashscope")

    if provider == "dashscope":
        return call_qwen_vl(
            video_path=video_path,
            prompt_text=prompt_text,
            api_key=profile.get("api_key", ""),
            model=profile.get("model", "qwen3.6-plus"),
            max_frames=int(profile.get("max_frames", 64)),
        )
    return _call_openai_compatible(video_path, prompt_text, profile)


def make_generate_adapter(profile: dict):
    """
    生成与 video_utils.call_qwen_vl 同签名的适配函数，
    用于注入 generate_vqa 模块（运行时替换其 call_qwen_vl 引用，不改源文件）
    """
    def _adapter(video_path, prompt_text, api_key=None, model=None,
                 max_frames=64, vl_high_resolution=True):
        merged = dict(profile)
        # 允许 generate_vqa 注入的模型级配置覆盖
        merged["max_frames"] = max_frames
        return call_vl_model(video_path, prompt_text, merged)
    return _adapter


# ============================================================
# 连通性测试
# ============================================================

def test_profile(profile: dict) -> dict:
    """
    用当前平台 profile 发一条最小请求验证配置可用

    返回: {"success": bool, "message": str}
    """
    provider = profile.get("provider", "dashscope")
    api_key = profile.get("api_key", "")
    if not api_key:
        return {"success": False, "message": "API Key 未填写"}

    if provider == "dashscope":
        try:
            from dashscope import MultiModalConversation
            resp = MultiModalConversation.call(
                api_key=api_key,
                model=profile.get("model", "qwen3.6-plus"),
                messages=[{"role": "user", "content": [{"text": "ping，只回复 ok"}]}],
            )
            if resp.status_code == 200:
                return {"success": True, "message": f"DashScope 连通正常（模型: {profile.get('model')}）"}
            return {"success": False, "message": f"DashScope 返回错误: {resp.get('message', resp.status_code)}"}
        except Exception as e:
            return {"success": False, "message": f"DashScope 异常: {e}"}

    # OpenAI 兼容平台：请求 /models 列表验证 Key
    base_url = (profile.get("base_url") or "").rstrip("/")
    if not base_url:
        return {"success": False, "message": "Base URL 未填写"}
    try:
        resp = requests.get(f"{base_url}/models",
                            headers={"Authorization": f"Bearer {api_key}"},
                            timeout=15)
        if resp.status_code == 200:
            return {"success": True, "message": f"接口连通正常（{base_url}）"}
        return {"success": False, "message": f"接口返回 {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"success": False, "message": f"连接失败: {e}"}
