"""
步骤①：准备任务清单
读取类目配置 Excel + 视频列表 Excel → 按数量分配类目和难度 → 输出 tasks.json

用法：
    python prepare_tasks.py

配置修改区（在 main 函数中）：
    - CATEGORY_EXCEL_PATH: 类目配置文件路径
    - VIDEO_EXCEL_PATH: 视频列表文件路径
    - VIDEO_FOLDER: 视频文件存放目录
    - DIFFICULTY_WEIGHTS: 难度分布比例
"""

import os
import json
import random
import pandas as pd


# ============================================================
# 配置区 —— 用户按需修改
# ============================================================

# 类目配置 Excel: 三列 [一级类目, 二级类目, 数量]
CATEGORY_EXCEL_PATH = "category_config.xlsx"

# 视频列表 Excel: 至少包含视频文件名列（第一列）
VIDEO_EXCEL_PATH = "video_list.xlsx"

# 视频文件存放目录
VIDEO_FOLDER = "./videos"

# 难度分布（简单/中等/困难 的比例，加起来应为 1.0）
DIFFICULTY_WEIGHTS = {
    "简单": 0.3,
    "中等": 0.4,
    "困难": 0.3,
}

# 输出文件
OUTPUT_JSON = "tasks.json"


# ============================================================
# 核心逻辑
# ============================================================

def read_category_config(excel_path: str) -> list:
    """
    读取类目配置 Excel
    期望列: 一级类目, 二级类目, 数量

    返回:
        [{"一级类目": str, "二级类目": str, "数量": int}, ...]
    """
    df = pd.read_excel(excel_path)
    # 自动识别列名（兼容中英文、大小写等变体）
    col_map = {}
    for col in df.columns:
        col_lower = str(col).strip().lower()
        if "一级" in col_lower or "1级" in col_lower or "大类" in col_lower:
            col_map["一级类目"] = col
        elif "二级" in col_lower or "2级" in col_lower or "小类" in col_lower:
            col_map["二级类目"] = col
        elif "数量" in col_lower or "count" in col_lower or "num" in col_lower:
            col_map["数量"] = col

    if len(col_map) < 3:
        raise ValueError(
            f"类目配置 Excel 列名识别失败。识别到: {col_map}\n"
            f"请确保包含：一级类目、二级类目、数量 三列。\n"
            f"当前列名: {list(df.columns)}"
        )

    categories = []
    for _, row in df.iterrows():
        cat1 = str(row[col_map["一级类目"]]).strip()
        cat2 = str(row[col_map["二级类目"]]).strip()
        count = int(row[col_map["数量"]])
        if cat1 and cat2 and count > 0:
            categories.append({
                "一级类目": cat1,
                "二级类目": cat2,
                "数量": count
            })

    print(f"读取到 {len(categories)} 个类目组合，共计 {sum(c['数量'] for c in categories)} 条任务")
    return categories


def read_video_list(excel_path: str) -> list:
    """
    读取视频列表 Excel
    取第一列作为视频文件名

    返回:
        ["video1.mp4", "video2.mp4", ...]
    """
    df = pd.read_excel(excel_path)
    col = df.columns[0]
    videos = df[col].dropna().astype(str).str.strip().tolist()
    videos = [v for v in videos if v]  # 过滤空字符串
    print(f"读取到 {len(videos)} 个视频文件")
    return videos


def assign_tasks(categories: list, videos: list, difficulty_weights: dict) -> list:
    """
    将类目分配给视频

    策略：
    1. 按每个类目组合的数量，展开为任务条目
    2. 随机打乱后依次分配给视频
    3. 如果任务数 > 视频数，部分视频会被分配多个任务
    4. 如果视频数 > 任务数，只使用部分视频
    """
    # 展开任务
    task_entries = []
    for cat in categories:
        for _ in range(cat["数量"]):
            task_entries.append({
                "一级类目": cat["一级类目"],
                "二级类目": cat["二级类目"],
            })

    random.shuffle(task_entries)

    # 分配难度
    difficulties = list(difficulty_weights.keys())
    weights = list(difficulty_weights.values())

    for i, entry in enumerate(task_entries):
        entry["目标难度"] = random.choices(difficulties, weights=weights, k=1)[0]

    # 分配视频（循环使用）
    if not videos:
        raise ValueError("视频列表为空，无法分配任务")

    tasks = []
    for i, entry in enumerate(task_entries):
        video_idx = i % len(videos)
        tasks.append({
            "data_id": f"VQA_{i+1:05d}",
            "一级类目": entry["一级类目"],
            "二级类目": entry["二级类目"],
            "视频文件名": videos[video_idx],
            "目标难度": entry["目标难度"],
        })

    return tasks


def print_summary(tasks: list):
    """打印任务分配摘要"""
    # 按类目统计
    cat_counts = {}
    for t in tasks:
        key = f"{t['一级类目']}/{t['二级类目']}"
        cat_counts[key] = cat_counts.get(key, 0) + 1

    diff_counts = {}
    for t in tasks:
        d = t["目标难度"]
        diff_counts[d] = diff_counts.get(d, 0) + 1

    unique_videos = len(set(t["视频文件名"] for t in tasks))

    print(f"\n========== 任务分配摘要 ==========")
    print(f"总任务数: {len(tasks)}")
    print(f"使用视频数: {unique_videos}")
    print(f"平均每个视频: {len(tasks)/unique_videos:.1f} 条任务")
    print(f"\n类目分布:")
    for cat, cnt in sorted(cat_counts.items()):
        print(f"  {cat}: {cnt} 条")
    print(f"\n难度分布:")
    for d, cnt in sorted(diff_counts.items()):
        print(f"  {d}: {cnt} 条 ({cnt/len(tasks)*100:.1f}%)")
    print(f"==================================\n")


def main():
    # 检查输入文件
    if not os.path.exists(CATEGORY_EXCEL_PATH):
        raise FileNotFoundError(
            f"类目配置文件不存在: {CATEGORY_EXCEL_PATH}\n"
            f"请先在项目目录创建该文件，格式：一级类目 | 二级类目 | 数量"
        )
    if not os.path.exists(VIDEO_EXCEL_PATH):
        raise FileNotFoundError(
            f"视频列表文件不存在: {VIDEO_EXCEL_PATH}\n"
            f"请先在项目目录创建该文件，第一列为视频文件名"
        )

    # 读取配置
    categories = read_category_config(CATEGORY_EXCEL_PATH)
    videos = read_video_list(VIDEO_EXCEL_PATH)

    if not categories:
        raise ValueError("类目配置为空，请检查 Excel 内容")

    # 分配任务
    tasks = assign_tasks(categories, videos, DIFFICULTY_WEIGHTS)
    print_summary(tasks)

    # 保存
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)

    print(f"任务清单已保存至: {OUTPUT_JSON}")
    print(f"下一步: 运行 generate_vqa.py 开始批量生成")


if __name__ == "__main__":
    main()
