"""
视频处理工具模块
从 QWEN_think.py 提炼出的可复用函数：
- 视频帧信息提取
- Qwen VL API 调用
"""

import os
import logging
import cv2
from dashscope import MultiModalConversation

logger = logging.getLogger(__name__)


def get_video_info(video_path: str) -> dict:
    """
    获取视频基本信息：总帧数、帧率、时长

    返回:
        {"total_frames": int, "fps": float, "duration_seconds": float, "duration_str": str}
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"无法打开视频文件: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()

    if fps > 0:
        duration_seconds = total_frames / fps
    else:
        duration_seconds = 0

    # 格式化为 HH:MM:SS
    h = int(duration_seconds // 3600)
    m = int((duration_seconds % 3600) // 60)
    s = int(duration_seconds % 60)
    duration_str = f"{h:02d}:{m:02d}:{s:02d}"

    return {
        "total_frames": total_frames,
        "fps": round(fps, 2),
        "duration_seconds": round(duration_seconds, 2),
        "duration_str": duration_str
    }


def calculate_frame_interval(total_frames: int, max_frames: int = 64) -> tuple:
    """
    计算均匀抽帧的间隔和实际抽取帧数

    返回:
        (interval, actual_frames)
    """
    if total_frames <= max_frames:
        return 1, total_frames
    else:
        interval = total_frames // max_frames
        return interval, max_frames


def call_qwen_vl(video_path: str,
                 prompt_text: str,
                 api_key: str,
                 model: str = "qwen3.5-35b-a3b",
                 max_frames: int = 64,
                 vl_high_resolution: bool = True) -> dict:
    """
    调用 Qwen VL 模型分析视频

    参数:
        video_path: 视频文件绝对路径
        prompt_text: 发给模型的文本提示
        api_key: DashScope API 密钥
        model: 模型名称
        max_frames: 最大抽取帧数
        vl_high_resolution: 是否启用高分辨率图像处理

    返回:
        {"success": bool, "answer": str, "status_code": int, "error": str|None}
    """
    try:
        # 检查文件
        if not os.path.exists(video_path):
            return {"success": False, "answer": "", "status_code": 0,
                    "error": f"视频文件不存在: {video_path}"}

        # 计算抽帧间隔
        info = get_video_info(video_path)
        interval, actual_frames = calculate_frame_interval(
            info["total_frames"], max_frames
        )
        logger.info(f"视频: {os.path.basename(video_path)}, "
                     f"总帧={info['total_frames']}, 抽帧={actual_frames}, 间隔={interval}")

        # 构建消息
        video_url = f"file://{video_path}"
        messages = [{
            "role": "user",
            "content": [
                {"video": video_url, "frame_interval": interval},
                {"text": prompt_text}
            ]
        }]

        # 调用 API
        response = MultiModalConversation.call(
            api_key=api_key,
            model=model,
            messages=messages,
            vl_high_resolution_images=vl_high_resolution
        )

        if response.status_code == 200 and "output" in response:
            answer = response["output"]["choices"][0]["message"].content[0]["text"]
            return {"success": True, "answer": answer, "status_code": 200, "error": None}
        else:
            error_msg = response.get("message", "未知错误")
            return {"success": False, "answer": "", "status_code": response.status_code,
                    "error": f"API 调用失败: {error_msg}"}

    except Exception as e:
        return {"success": False, "answer": "", "status_code": -1,
                "error": f"异常: {str(e)}"}
