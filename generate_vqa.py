"""
步骤②：批量生成 VQA 数据
读取 tasks.json → 逐视频调用 Qwen VL → 生成 prompt+答案+难度 → 输出 results.json + results.csv

用法：
    python generate_vqa.py

特性：
    - 断点续跑：已有 results.json 且状态为"正常"的条目自动跳过
    - CSV + JSON 双格式同步输出
    - 每处理 5 条自动保存进度
    - JSON 解析失败自动重试（最多2次）
"""

import os
import json
import re
import logging
import pandas as pd
from datetime import datetime
from tqdm import tqdm

from video_utils import call_qwen_vl, get_video_info
from prompt_templates import build_vqa_prompt

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ============================================================
# 配置区 —— 用户按需修改
# ============================================================

# DashScope API 密钥（建议用环境变量 DASHSCOPE_API_KEY）
API_KEY = os.environ.get("DASHSCOPE_API_KEY", "***REMOVED***")

# 模型名称
MODEL = "qwen3.6-plus"

# 视频文件存放目录
VIDEO_FOLDER = "./videos"

# 最大抽帧数
MAX_FRAMES = 64

# 输入/输出文件
INPUT_JSON = "tasks.json"
OUTPUT_JSON = "results.json"
OUTPUT_CSV = "results.csv"

# 最大重试次数（JSON 解析失败时）
MAX_RETRIES = 2


# ============================================================
# 工具函数
# ============================================================

def extract_json_from_response(text: str) -> dict | None:
    """
    从模型返回的文本中提取 JSON 对象
    兼容多种可能的格式：
    1. 纯 JSON: {"prompt": "...", ...}
    2. markdown 代码块包裹: ```json {...} ```
    3. 前后有额外文字: 一些说明... {"prompt": "..."} ...其他
    """
    if not text:
        return None

    text = text.strip()

    # 方法1: 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 方法2: 提取 markdown 代码块中的 JSON
    md_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if md_match:
        try:
            return json.loads(md_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 方法3: 查找最外层 { } 包裹的 JSON
    brace_start = text.find('{')
    brace_end = text.rfind('}')
    if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
        try:
            return json.loads(text[brace_start:brace_end + 1])
        except json.JSONDecodeError:
            pass

    return None


def validate_result_fields(result: dict) -> list:
    """检查生成结果是否包含必要字段，返回缺失字段列表"""
    required = ["prompt", "参考答案"]
    missing = [f for f in required if f not in result or not str(result[f]).strip()]
    return missing


def save_both(data: list, json_path: str, csv_path: str):
    """同时保存 JSON 和 CSV 两份"""
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    df = pd.DataFrame(data)
    # 确保列顺序
    column_order = ["data_id", "一级类目", "二级类目", "视频url", "视频时长",
                    "prompt", "参考答案", "难度", "状态", "备注"]
    existing_cols = [c for c in column_order if c in df.columns]
    other_cols = [c for c in df.columns if c not in column_order]
    df = df[existing_cols + other_cols]
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")


def load_existing_results(json_path: str) -> list:
    """加载已有结果（用于断点续跑）"""
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


# ============================================================
# 核心生成逻辑
# ============================================================

def process_single_task(task: dict, retry_count: int = 0) -> dict:
    """
    处理单条任务：调 Qwen VL 生成 VQA 数据

    返回:
        {
            "data_id": str,
            "一级类目": str,
            "二级类目": str,
            "视频url": str,
            "视频时长": str,
            "prompt": str,
            "参考答案": str,
            "难度": str,
            "状态": "正常" | "需复核",
            "备注": str
        }
    """
    video_filename = task["视频文件名"]
    video_path = os.path.join(VIDEO_FOLDER, video_filename)

    result = {
        "data_id": task["data_id"],
        "一级类目": task["一级类目"],
        "二级类目": task["二级类目"],
        "视频url": video_filename,
        "视频时长": "",
        "prompt": "",
        "参考答案": "",
        "难度": task.get("目标难度", "中等"),
        "状态": "需复核",
        "备注": "",
    }

    # 获取视频时长
    try:
        info = get_video_info(video_path)
        result["视频时长"] = info["duration_str"]
    except Exception as e:
        result["备注"] = f"读取视频时长失败: {e}"
        result["视频时长"] = "未知"

    # 构建 prompt
    vqa_prompt = build_vqa_prompt(task)

    # 调用模型
    response = call_qwen_vl(
        video_path=video_path,
        prompt_text=vqa_prompt,
        api_key=API_KEY,
        model=MODEL,
        max_frames=MAX_FRAMES,
    )

    if not response["success"]:
        result["备注"] = response["error"]
        result["状态"] = "需复核"
        return result

    # 解析 JSON
    parsed = extract_json_from_response(response["answer"])

    if parsed is None:
        # JSON 解析失败，尝试重试
        if retry_count < MAX_RETRIES:
            logger.warning(f"{task['data_id']}: JSON 解析失败，第{retry_count+1}次重试...")
            return process_single_task(task, retry_count + 1)
        else:
            result["prompt"] = response["answer"][:500]  # 保留原始输出方便排查
            result["备注"] = f"JSON 解析失败（已重试{MAX_RETRIES}次），原始输出已存入 prompt 字段"
            result["状态"] = "需复核"
            return result

    # 填充字段
    result["prompt"] = parsed.get("prompt", "")
    result["参考答案"] = parsed.get("参考答案", "")
    if "难度" in parsed:
        result["难度"] = parsed["难度"]

    # 检查字段完整性
    missing = validate_result_fields(result)
    if missing:
        if retry_count < MAX_RETRIES:
            logger.warning(f"{task['data_id']}: 缺少字段 {missing}，第{retry_count+1}次重试...")
            return process_single_task(task, retry_count + 1)
        else:
            result["备注"] = f"缺少字段: {', '.join(missing)}（已重试{MAX_RETRIES}次）"
            result["状态"] = "需复核"
            return result

    # 通过基本校验
    result["状态"] = "正常"
    if not result["备注"]:
        result["备注"] = ""
    return result


def main():
    # 检查输入文件
    if not os.path.exists(INPUT_JSON):
        raise FileNotFoundError(
            f"任务文件不存在: {INPUT_JSON}\n"
            f"请先运行 prepare_tasks.py 生成任务清单"
        )

    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        tasks = json.load(f)

    # 加载已有结果（断点续跑）
    results = load_existing_results(OUTPUT_JSON)

    # 构建已完成任务的指纹集合：只有 data_id + 视频 + 类目 全部匹配才认为已完成
    # 避免换了一批视频/类目后，旧结果仍被错误跳过
    done_fingerprints = {
        (r["data_id"], r.get("视频url", ""), r.get("一级类目", ""), r.get("二级类目", ""))
        for r in results if r.get("状态") == "正常"
    }

    pending_tasks = [
        t for t in tasks
        if (t["data_id"], t["视频文件名"], t["一级类目"], t["二级类目"]) not in done_fingerprints
    ]
    skipped = len(tasks) - len(pending_tasks)

    print(f"总任务: {len(tasks)} | 已完成: {skipped} | 待处理: {len(pending_tasks)}")
    if skipped > 0:
        print(f"（断点续跑模式：跳过 {skipped} 个已完成的正常条目）")

    if not pending_tasks:
        print("所有任务已完成，无需处理。")
        return

    # 逐个处理
    processed = 0
    error_count = 0

    for i, task in enumerate(tqdm(pending_tasks, desc="生成 VQA 数据")):
        result = process_single_task(task)

        # 更新 results 列表（保持与 tasks 同顺序）
        # 找到对应位置替换或追加
        existing_idx = None
        for idx, r in enumerate(results):
            if r["data_id"] == result["data_id"]:
                existing_idx = idx
                break

        if existing_idx is not None:
            results[existing_idx] = result
        else:
            results.append(result)

        if result["状态"] != "正常":
            error_count += 1

        processed += 1

        # 每 5 条保存一次
        if processed % 5 == 0:
            save_both(results, OUTPUT_JSON, OUTPUT_CSV)
            logger.info(f"进度: {processed}/{len(pending_tasks)}，已保存")

    # 最终保存
    save_both(results, OUTPUT_JSON, OUTPUT_CSV)

    # 统计
    normal_count = sum(1 for r in results if r.get("状态") == "正常")
    review_count = sum(1 for r in results if r.get("状态") == "需复核")

    print(f"\n========== 生成完成 ==========")
    print(f"总计: {len(results)} 条")
    print(f"正常: {normal_count} 条")
    print(f"需复核: {review_count} 条")
    print(f"结果已保存: {OUTPUT_JSON} / {OUTPUT_CSV}")
    print(f"下一步: 运行 validate.py 进行深度校验")


if __name__ == "__main__":
    main()
