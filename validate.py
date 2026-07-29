"""
步骤③：校验生成结果
读取 results.json → 字段完整性检查 + 类目相关性检测 + 质量评估 → 输出 final.json + final.csv

用法：
    python validate.py

校验项目：
    1. 字段完整性：prompt、参考答案是否为空
    2. 类目相关性：prompt 是否与分配的一级类目关键词匹配
    3. 质量检测：prompt 是否过于简单/主观
    4. 难度分布统计
"""

import os
import json
import pandas as pd
from collections import Counter

from prompt_templates import (
    check_prompt_category_match,
    check_prompt_quality,
    get_category_guide,
    CATEGORY_GUIDES,
)


# ============================================================
# 配置区
# ============================================================

INPUT_JSON = "results.json"
OUTPUT_JSON = "final.json"
OUTPUT_CSV = "final.csv"

# 类目关键词匹配开关：设为 False 则跳过关键词检查（适用于类目未在 CATEGORY_GUIDES 中定义时）
ENABLE_KEYWORD_CHECK = True


# ============================================================
# 校验函数
# ============================================================

def validate_record(record: dict) -> dict:
    """
    对单条记录执行全部校验，返回带校验结果的记录

    校验结果存在 record["校验结果"] 中：
        "通过" — 全部校验通过
        "需复核" — 存在需要人工检查的问题
        "需重生成" — 存在严重问题，建议重新生成
    """
    issues = []
    prompt = str(record.get("prompt", "")).strip()
    answer = str(record.get("参考答案", "")).strip()
    cat1 = str(record.get("一级类目", "")).strip()
    difficulty = str(record.get("难度", "")).strip()

    # ---- 1. 字段完整性检查 ----
    if not prompt:
        issues.append("[严重] prompt 为空")
    if not answer:
        issues.append("[严重] 参考答案为空")
    if difficulty not in ("简单", "中等", "困难"):
        issues.append(f"[轻微] 难度值异常: '{difficulty}'")

    # ---- 2. 类目相关性检查 ----
    if ENABLE_KEYWORD_CHECK and prompt:
        is_match, matched, total = check_prompt_category_match(prompt, cat1)
        if not is_match and total > 0:
            guide = get_category_guide(cat1)
            kw_examples = guide.get("关键词", [])[:5]
            issues.append(
                f"[需复核] prompt 与类目'{cat1}'关键词无交集 "
                f"(类目关键词示例: {', '.join(kw_examples)})"
            )

    # ---- 3. Prompt 质量检查 ----
    if prompt:
        quality_issues = check_prompt_quality(prompt)
        for qi in quality_issues:
            issues.append(f"[需复核] {qi}")

    # ---- 4. 判断结果 ----
    has_severe = any("严重" in i for i in issues)
    has_minor = any("需复核" in i for i in issues)

    if has_severe:
        verdict = "需重生成"
    elif has_minor:
        verdict = "需复核"
    else:
        verdict = "通过"

    record["校验结果"] = verdict
    record["问题详情"] = "\n".join(issues) if issues else ""
    return record


def print_statistics(records: list):
    """打印校验统计"""
    total = len(records)
    verdicts = Counter(r.get("校验结果", "未校验") for r in records)

    print(f"\n========== 校验统计 ==========")
    print(f"总记录数: {total}")
    for v in ["通过", "需复核", "需重生成"]:
        cnt = verdicts.get(v, 0)
        pct = cnt / total * 100 if total > 0 else 0
        print(f"  {v}: {cnt} 条 ({pct:.1f}%)")

    # 难度分布
    diffs = Counter(r.get("难度", "未知") for r in records)
    print(f"\n难度分布:")
    for d in ["简单", "中等", "困难"]:
        cnt = diffs.get(d, 0)
        pct = cnt / total * 100 if total > 0 else 0
        print(f"  {d}: {cnt} 条 ({pct:.1f}%)")

    # 类目分布
    cats = Counter(f"{r.get('一级类目','?')}/{r.get('二级类目','?')}" for r in records)
    print(f"\n类目分布:")
    for cat, cnt in cats.most_common():
        print(f"  {cat}: {cnt} 条")

    # 问题汇总
    all_issues = []
    for r in records:
        if r.get("问题详情"):
            all_issues.extend(r["问题详情"].split("\n"))
    issue_counts = Counter(all_issues)
    if issue_counts:
        print(f"\n常见问题 Top 10:")
        for issue, cnt in issue_counts.most_common(10):
            print(f"  [{cnt}次] {issue}")

    print(f"===============================\n")


def save_both(data: list, json_path: str, csv_path: str):
    """同时保存 JSON 和 CSV"""
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    df = pd.DataFrame(data)
    column_order = ["data_id", "一级类目", "二级类目", "视频url", "视频时长",
                    "prompt", "参考答案", "难度", "校验结果", "问题详情"]
    existing_cols = [c for c in column_order if c in df.columns]
    other_cols = [c for c in df.columns if c not in column_order]
    df = df[existing_cols + other_cols]
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")


def main():
    # 检查输入
    if not os.path.exists(INPUT_JSON):
        raise FileNotFoundError(
            f"结果文件不存在: {INPUT_JSON}\n"
            f"请先运行 generate_vqa.py 生成结果"
        )

    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        records = json.load(f)

    print(f"读取到 {len(records)} 条记录，开始校验...")

    # 逐条校验
    for record in records:
        validate_record(record)

    # 打印统计
    print_statistics(records)

    # 保存
    save_both(records, OUTPUT_JSON, OUTPUT_CSV)
    print(f"校验结果已保存: {OUTPUT_JSON} / {OUTPUT_CSV}")

    # 给出建议
    review_count = sum(1 for r in records if r.get("校验结果") != "通过")
    if review_count > 0:
        print(f"\n💡 建议: {review_count} 条未通过的记录请人工复核。")
        print(f"   在 CSV 文件中筛选「校验结果」列即可快速定位。"
              f"   修正后可直接使用 final.csv 作为最终评测数据集。")


if __name__ == "__main__":
    main()
