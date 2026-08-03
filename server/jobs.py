"""
后台任务执行器（jobs）
- prepare / validate：秒级任务，同步执行
- generate：长耗时任务，后台 threading.Thread 执行，前端轮询 JobState

复用策略（原 5 个 CLI 文件零改动）：
- prepare → prepare_tasks.assign_tasks
- validate → validate.validate_record / save_both
- generate → generate_vqa.process_single_task（通过模块属性注入配置与适配器）
"""

import sys
import json
import hashlib
import random
import threading
from collections import Counter, deque
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import prepare_tasks  # noqa: E402
import generate_vqa  # noqa: E402
import validate as validate_mod  # noqa: E402

from server import store  # noqa: E402
from server.vl_adapter import make_generate_adapter  # noqa: E402


class JobRunningError(Exception):
    """已有任务在运行中时抛出（API 层转为 409）"""
    pass


# ============================================================
# 任务状态（内存，前端轮询）
# ============================================================

class JobState:
    def __init__(self):
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None
        self.reset()

    def reset(self):
        self._stop_event.clear()  # 重置时必须清除停止标志，否则下一次启动会被立即停止
        with self._lock:
            self.step = "idle"          # idle / prepare / generate / validate
            self.status = "idle"        # idle / running / done / error / stopped
            self.total = 0
            self.done = 0
            self.skipped = 0
            self.error_count = 0
            self.current_item = ""
            self.logs = deque(maxlen=200)
            self.error = None
            self.started_at = None
            self.finished_at = None
            self.summary = None         # 各步骤完成后的摘要

    def log(self, msg: str, level: str = "info"):
        with self._lock:
            ts = datetime.now().strftime("%H:%M:%S")
            self.logs.append({"time": ts, "level": level, "msg": msg})

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "step": self.step,
                "status": self.status,
                "total": self.total,
                "done": self.done,
                "skipped": self.skipped,
                "error_count": self.error_count,
                "current_item": self.current_item,
                "logs": list(self.logs),
                "error": self.error,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "summary": self.summary,
            }

    def request_stop(self):
        self._stop_event.set()
        self.log("收到停止请求，将在当前条目完成后停止…", "warn")

    @property
    def stop_requested(self) -> bool:
        return self._stop_event.is_set()


state = JobState()


def _stable_data_id(video: str, cat1: str, cat2: str, salt: str = "", seen: set | None = None) -> str:
    """基于 视频+类目 生成稳定 data_id（VQA_xxxxx，5 位数字）

    同一视频+类目永远得到同一 data_id，换视频/类目则 ID 变化。
    这样 generate 才能区分「重跑旧任务」与「新任务」，避免新视频占用旧
    序号 ID 后覆盖旧结果。与已有 ID（含历史 results）冲突时自动加盐。
    """
    seen = seen if seen is not None else set()
    n = 0
    while True:
        seed = f"{video}|{cat1}|{cat2}{salt}#{n}"
        did = f"VQA_{int(hashlib.md5(seed.encode('utf-8')).hexdigest()[:8], 16) % 100000:05d}"
        if did not in seen:
            seen.add(did)
            return did
        n += 1


# ============================================================
# 步骤① 准备任务清单（同步）
# ============================================================

def run_prepare() -> dict:
    """复用 prepare_tasks 的分配逻辑，难度权重取自 settings"""
    settings = store.load_settings()
    weights = settings.get("difficulty_weights", {"简单": 0.3, "中等": 0.4, "困难": 0.3})
    total_w = sum(weights.values())
    if abs(total_w - 1.0) > 0.01:
        raise ValueError(f"难度权重之和必须为 1.0，当前为 {total_w:.2f}，请先在设置页调整")

    categories = store.load_categories()
    if not categories:
        raise ValueError("类目配置为空，请先在「类目配置」页填写")
    videos = store.load_video_list()
    if not videos:
        raise ValueError("视频清单为空，请先在「视频管理」页勾选参与的视频")

    # 固定随机种子（seed = 配置哈希）：同配置 → 同任务分配（视频-类目配对、难度均稳定），
    # 改配置自动重新随机。否则 assign_tasks 内部每次 shuffle 会让配对漂移，
    # 已生成的「视频+类目」被判定为新任务重复生成
    seed_src = "|".join(f"{c['一级类目']}/{c['二级类目']}x{c['数量']}" for c in categories) + "||" + "|".join(videos)
    random.seed(int(hashlib.md5(seed_src.encode("utf-8")).hexdigest()[:8], 16))
    tasks = prepare_tasks.assign_tasks(categories, videos, weights)

    # data_id 绑定 视频+类目（稳定 ID）：同一视频+类目永远同一 ID。
    # 旧逻辑按任务序号编号，换视频/改配置后新任务会占用旧 data_id，
    # generate 写回时按 data_id 覆盖 → 旧结果被新视频静默替换（已修复）
    results = store.load_results("results")
    new_combos = {(t["视频文件名"], t["一级类目"], t["二级类目"]) for t in tasks}
    # 只把「新任务不涉及」的历史 id 视为冲突（同配对的历史记录应复用/迁移，而不是加盐换 id）
    seen = {r.get("data_id") for r in results
            if r.get("data_id")
            and (r.get("视频url", ""), r.get("一级类目", ""), r.get("二级类目", "")) not in new_combos}
    combo_counts = Counter((t["视频文件名"], t["一级类目"], t["二级类目"]) for t in tasks)
    for t in tasks:
        combo = (t["视频文件名"], t["一级类目"], t["二级类目"])
        # 同一视频+类目被分配多条任务时用目标难度区分（保持稳定）
        salt = f"|{t['目标难度']}" if combo_counts[combo] > 1 else ""
        t["data_id"] = _stable_data_id(*combo, salt, seen)

    # 迁移历史结果：results 中「视频+类目」与新任务一致但 data_id 不同的记录，
    # 改为新 data_id，避免历史序号 ID 与新任务撞车或换视频后重复生成
    task_by_combo = {(t["视频文件名"], t["一级类目"], t["二级类目"]): t["data_id"] for t in tasks}
    migrated = 0
    for r in results:
        combo = (r.get("视频url", ""), r.get("一级类目", ""), r.get("二级类目", ""))
        if combo in task_by_combo and r.get("data_id") != task_by_combo[combo]:
            r["data_id"] = task_by_combo[combo]
            migrated += 1
    if migrated:
        store.save_results(results, "results")
        state.log(f"历史结果 data_id 已与新任务对齐：{migrated} 条")

    with open(store.TASKS_JSON, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)

    # 统计摘要
    cat_counts, diff_counts = {}, {}
    for t in tasks:
        key = f"{t['一级类目']}/{t['二级类目']}"
        cat_counts[key] = cat_counts.get(key, 0) + 1
        diff_counts[t["目标难度"]] = diff_counts.get(t["目标难度"], 0) + 1

    summary = {
        "total": len(tasks),
        "unique_videos": len(set(t["视频文件名"] for t in tasks)),
        "category_dist": cat_counts,
        "difficulty_dist": diff_counts,
    }
    state.log(f"任务清单已生成：{len(tasks)} 条任务，使用 {summary['unique_videos']} 个视频")
    return summary


# ============================================================
# 步骤③ 校验（同步）
# ============================================================

def run_validate() -> dict:
    """复用 validate 模块的校验逻辑，关键词开关取自 settings"""
    records = store.load_results("results")
    if not records:
        raise ValueError("结果文件为空，请先运行步骤②生成数据")

    settings = store.load_settings()
    validate_mod.ENABLE_KEYWORD_CHECK = settings.get("keyword_check", True)

    for record in records:
        validate_mod.validate_record(record)

    validate_mod.save_both(records, str(store.FINAL_JSON), str(store.FINAL_CSV))

    total = len(records)
    verdicts = {}
    for r in records:
        v = r.get("校验结果", "未校验")
        verdicts[v] = verdicts.get(v, 0) + 1

    summary = {
        "total": total,
        "verdicts": verdicts,
        "pass_rate": round(verdicts.get("通过", 0) / total * 100, 1) if total else 0,
    }
    state.log(f"校验完成：通过 {verdicts.get('通过', 0)} / {total}（{summary['pass_rate']}%）")
    return summary


# ============================================================
# 步骤② 批量生成（后台线程）
# ============================================================

def _build_profile() -> dict:
    """构建生成用 profile；dashscope 平台未填 Key 时回退到环境变量/CLI 默认值"""
    profile = store.get_active_profile()
    if profile["provider"] == "dashscope" and not profile.get("api_key"):
        profile["api_key"] = generate_vqa.API_KEY  # env DASHSCOPE_API_KEY 或 CLI 默认值
    return profile


def preview_generate() -> dict:
    """预览下次生成会跑多少新任务、跳过多少旧任务（不实际启动）

    供前端在点生成按钮前展示，让用户明确「继续生成」实际要跑多少。
    """
    tasks = store.load_tasks()
    results = store.load_results("results")
    done_fingerprints = {
        (r["data_id"], r.get("视频url", ""), r.get("一级类目", ""), r.get("二级类目", ""))
        for r in results if r.get("状态") == "正常"
    }
    pending = [
        t for t in tasks
        if (t["data_id"], t["视频文件名"], t["一级类目"], t["二级类目"]) not in done_fingerprints
    ]
    return {
        "total_tasks": len(tasks),
        "pending": len(pending),
        "skipped": len(tasks) - len(pending),
        "existing_results": len(results),
    }


def _generate_worker():
    """generate 线程主体：断点续跑 + 每 5 条落盘 + 协作式停止"""
    try:
        tasks = store.load_tasks()
        if not tasks:
            raise ValueError("任务清单为空，请先运行步骤①")

        results = store.load_results("results")

        # 断点续跑指纹（与 CLI 一致：data_id + 视频 + 类目 全匹配才跳过）
        done_fingerprints = {
            (r["data_id"], r.get("视频url", ""), r.get("一级类目", ""), r.get("二级类目", ""))
            for r in results if r.get("状态") == "正常"
        }
        pending = [
            t for t in tasks
            if (t["data_id"], t["视频文件名"], t["一级类目"], t["二级类目"]) not in done_fingerprints
        ]

        with state._lock:
            state.total = len(pending)
            state.skipped = len(tasks) - len(pending)
        state.log(f"总任务 {len(tasks)} | 已完成跳过 {state.skipped} | 待处理 {len(pending)}")
        if not pending:
            with state._lock:
                state.status = "done"
                state.finished_at = datetime.now().isoformat()
            state.log("所有任务已完成，无需处理")
            return

        # 注入配置到 generate_vqa 模块（仅运行时属性，不改源文件）
        profile = _build_profile()
        generate_vqa.MAX_FRAMES = profile.get("max_frames", 64)
        generate_vqa.MAX_RETRIES = profile.get("max_retries", 2)
        generate_vqa.VIDEO_FOLDER = str(store.VIDEO_FOLDER)
        generate_vqa.call_qwen_vl = make_generate_adapter(profile)
        state.log(f"使用平台: {profile['provider']} · 模型: {profile.get('model')} · 抽帧: {profile.get('max_frames')}")

        processed = 0
        for task in pending:
            if state.stop_requested:
                break

            with state._lock:
                state.current_item = f"{task['data_id']} / {task['视频文件名']} · {task['一级类目']}"

            result = generate_vqa.process_single_task(task)

            # 更新结果列表（保持与 tasks 同顺序的 upsert）
            existing_idx = next(
                (i for i, r in enumerate(results) if r["data_id"] == result["data_id"]), None
            )
            if existing_idx is not None:
                results[existing_idx] = result
            else:
                results.append(result)

            processed += 1
            with state._lock:
                state.done = processed
                if result["状态"] != "正常":
                    state.error_count += 1

            if result["状态"] == "正常":
                state.log(f"{result['data_id']} ✓ 正常 · {result['一级类目']}/{result['二级类目']}")
            else:
                state.log(f"{result['data_id']} ⚠ 需复核 · {result.get('备注', '')[:80]}", "warn")

            if processed % 5 == 0:
                store.save_results(results, "results")
                state.log(f"进度 {processed}/{len(pending)}，已自动保存")

        # 最终落盘
        store.save_results(results, "results")

        with state._lock:
            state.status = "stopped" if state.stop_requested else "done"
            state.finished_at = datetime.now().isoformat()
            normal = sum(1 for r in results if r.get("状态") == "正常")
            state.summary = {"total": len(results), "normal": normal,
                             "review": len(results) - normal}
        state.log(f"生成结束：本次处理 {processed} 条，状态={'已停止' if state.stop_requested else '完成'}")

    except Exception as e:
        with state._lock:
            state.status = "error"
            state.error = str(e)
            state.finished_at = datetime.now().isoformat()
        state.log(f"生成任务异常中断: {e}", "error")


def start_generate():
    """启动 generate 后台线程（防重入）"""
    with state._lock:
        if state.status == "running":
            raise JobRunningError("生成任务正在运行中，请勿重复启动")
    state.reset()
    with state._lock:
        state.step = "generate"
        state.status = "running"
        state.started_at = datetime.now().isoformat()
    state._stop_event.clear()
    state._thread = threading.Thread(target=_generate_worker, daemon=True)
    state._thread.start()
    return {"started": True}


def stop_generate():
    """协作式停止：当前条目处理完后退出"""
    if state.status != "running":
        return {"stopped": False, "reason": "当前没有运行中的任务"}
    state.request_stop()
    return {"stopped": True}


def get_status() -> dict:
    return state.snapshot()
