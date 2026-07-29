"""
数据读写层（store）
统一封装所有文件读写：xlsx 配置、json 结果、settings.json 设置。
路由层不允许直接碰 pandas / 文件路径，必须走本模块，防止格式不一致。

注意：
- 写 xlsx 必须 index=False（否则多出 Unnamed: 0 列，CLI 读入会报错）
- 所有路径以项目根目录（本文件上一级）为基准
"""

import os
import sys
import json
import threading
from pathlib import Path

import pandas as pd

# 项目根目录加入 sys.path，以便复用原 CLI 模块
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from video_utils import get_video_info  # noqa: E402

# ============================================================
# 路径常量
# ============================================================

CATEGORY_XLSX = ROOT / "category_config.xlsx"
VIDEO_XLSX = ROOT / "video_list.xlsx"
VIDEO_FOLDER = ROOT / "videos"
TASKS_JSON = ROOT / "tasks.json"
RESULTS_JSON = ROOT / "results.json"
RESULTS_CSV = ROOT / "results.csv"
FINAL_JSON = ROOT / "final.json"
FINAL_CSV = ROOT / "final.csv"
SETTINGS_JSON = Path(__file__).resolve().parent / "settings.json"

VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv"}

# 文件写锁（generate 线程与 API 线程可能同时读写）
_lock = threading.Lock()


# ============================================================
# 设置（多平台 profile）
# ============================================================

DEFAULT_SETTINGS = {
    "active_provider": "dashscope",
    "providers": {
        "dashscope":  {"api_key": "", "base_url": "", "model": "qwen3.6-plus"},
        "openai":     {"api_key": "", "base_url": "https://api.openai.com/v1", "model": "gpt-4o"},
        "openrouter": {"api_key": "", "base_url": "https://openrouter.ai/api/v1", "model": ""},
        "zhipu":      {"api_key": "", "base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4v-plus"},
        "custom":     {"api_key": "", "base_url": "", "model": ""},
    },
    "max_frames": 64,
    "max_retries": 2,
    "keyword_check": True,
    "difficulty_weights": {"简单": 0.3, "中等": 0.4, "困难": 0.3},
}


def mask_key(key: str) -> str:
    """API Key 掩码：sk-abc...xyz 形式，绝不返回完整密钥"""
    if not key:
        return ""
    if len(key) <= 8:
        return key[:2] + "****"
    return f"{key[:6]}****{key[-4:]}"


def load_settings() -> dict:
    """读取 settings.json，缺字段用默认值补齐（保证结构完整）"""
    settings = json.loads(json.dumps(DEFAULT_SETTINGS))  # 深拷贝默认值
    if SETTINGS_JSON.exists():
        try:
            with open(SETTINGS_JSON, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for k, v in saved.items():
                if k == "providers" and isinstance(v, dict):
                    for pname, prof in v.items():
                        settings["providers"].setdefault(pname, {}).update(prof)
                else:
                    settings[k] = v
        except (json.JSONDecodeError, OSError):
            pass  # 文件损坏时回退默认值
    return settings


def save_settings(settings: dict) -> dict:
    """保存 settings.json（含权限收紧 600）"""
    with _lock:
        with open(SETTINGS_JSON, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        os.chmod(SETTINGS_JSON, 0o600)
    return settings


def get_masked_settings() -> dict:
    """返回掩码后的设置（供 GET 接口使用，所有平台 Key 均掩码）"""
    s = load_settings()
    masked = json.loads(json.dumps(s))
    for pname, prof in masked.get("providers", {}).items():
        prof["api_key"] = mask_key(prof.get("api_key", ""))
        prof["has_key"] = bool(s["providers"].get(pname, {}).get("api_key"))
    return masked


def get_active_profile() -> dict:
    """返回当前激活平台的完整 profile（含明文 Key，仅服务端内部使用）"""
    s = load_settings()
    name = s.get("active_provider", "dashscope")
    prof = dict(s.get("providers", {}).get(name, {}))
    prof["provider"] = name
    prof["max_frames"] = s.get("max_frames", 64)
    prof["max_retries"] = s.get("max_retries", 2)
    return prof


# ============================================================
# 类目配置（category_config.xlsx）
# ============================================================

CATEGORY_COLUMNS = ["一级类目", "二级类目", "数量"]


def load_categories() -> list:
    """读取类目配置，返回 [{一级类目, 二级类目, 数量}, ...]"""
    if not CATEGORY_XLSX.exists():
        return []
    df = pd.read_excel(CATEGORY_XLSX)
    # 沿用 CLI 的列名自动识别逻辑
    col_map = {}
    for col in df.columns:
        c = str(col).strip().lower()
        if "一级" in c or "1级" in c or "大类" in c:
            col_map["一级类目"] = col
        elif "二级" in c or "2级" in c or "小类" in c:
            col_map["二级类目"] = col
        elif "数量" in c or "count" in c or "num" in c:
            col_map["数量"] = col
    if len(col_map) < 3:
        return []

    rows = []
    for _, row in df.iterrows():
        cat1 = str(row[col_map["一级类目"]]).strip() if pd.notna(row[col_map["一级类目"]]) else ""
        cat2 = str(row[col_map["二级类目"]]).strip() if pd.notna(row[col_map["二级类目"]]) else ""
        try:
            count = int(row[col_map["数量"]])
        except (ValueError, TypeError):
            continue
        if cat1 and cat2 and count > 0:
            rows.append({"一级类目": cat1, "二级类目": cat2, "数量": count})
    return rows


def save_categories(rows: list) -> list:
    """保存类目配置（校验数量为正整数；写 xlsx 必须 index=False）"""
    cleaned = []
    for i, r in enumerate(rows):
        cat1 = str(r.get("一级类目", "")).strip()
        cat2 = str(r.get("二级类目", "")).strip()
        try:
            count = int(r.get("数量", 0))
        except (ValueError, TypeError):
            raise ValueError(f"第 {i+1} 行：数量必须是正整数")
        if not cat1 or not cat2:
            raise ValueError(f"第 {i+1} 行：一级类目和二级类目不能为空")
        if count <= 0:
            raise ValueError(f"第 {i+1} 行：数量必须大于 0")
        cleaned.append({"一级类目": cat1, "二级类目": cat2, "数量": count})
    if not cleaned:
        raise ValueError("类目配置不能为空")
    df = pd.DataFrame(cleaned, columns=CATEGORY_COLUMNS)
    with _lock:
        df.to_excel(CATEGORY_XLSX, index=False)
    return cleaned


# ============================================================
# 视频清单与目录（video_list.xlsx / videos/）
# ============================================================

def load_video_list() -> list:
    """读取参与评测的视频文件名清单"""
    if not VIDEO_XLSX.exists():
        return []
    df = pd.read_excel(VIDEO_XLSX)
    col = df.columns[0]
    videos = df[col].dropna().astype(str).str.strip().tolist()
    return [v for v in videos if v]


def save_video_list(names: list) -> list:
    """保存参与评测的视频清单（校验文件必须存在于 videos/）"""
    cleaned = []
    for n in names:
        n = str(n).strip()
        if not n:
            continue
        if not (VIDEO_FOLDER / n).exists():
            raise ValueError(f"视频文件不存在: {n}")
        if n not in cleaned:
            cleaned.append(n)
    if not cleaned:
        raise ValueError("视频清单不能为空")
    df = pd.DataFrame({"视频文件名": cleaned})
    with _lock:
        df.to_excel(VIDEO_XLSX, index=False)
    return cleaned


def scan_videos() -> list:
    """
    扫描 videos/ 目录，返回每个视频的元数据：
    [{name, duration, duration_seconds, size_mb, in_list, used_by}]
    used_by: 该视频在 results.json 中被引用的次数（用于删除前警告）
    """
    in_list = set(load_video_list())
    used_count = {}
    for r in load_results("results"):
        v = r.get("视频url", "")
        if v:
            used_count[v] = used_count.get(v, 0) + 1

    items = []
    if VIDEO_FOLDER.exists():
        for f in sorted(VIDEO_FOLDER.iterdir()):
            if f.suffix.lower() not in VIDEO_EXTS or f.name.startswith("."):
                continue
            item = {
                "name": f.name,
                "size_mb": round(f.stat().st_size / 1024 / 1024, 1),
                "in_list": f.name in in_list,
                "used_by": used_count.get(f.name, 0),
                "duration": "未知",
                "duration_seconds": 0,
            }
            try:
                info = get_video_info(str(f))
                item["duration"] = info["duration_str"]
                item["duration_seconds"] = info["duration_seconds"]
            except Exception:
                pass  # 无法读取时保留"未知"，不阻塞列表
            items.append(item)
    return items


def save_uploaded_video(filename: str, fileobj) -> str:
    """流式保存上传的视频（不整读内存），返回文件名"""
    # 文件名安全处理：只保留 basename
    safe_name = os.path.basename(filename).strip()
    if not safe_name:
        raise ValueError("文件名不能为空")
    if Path(safe_name).suffix.lower() not in VIDEO_EXTS:
        raise ValueError(f"不支持的视频格式: {safe_name}")
    VIDEO_FOLDER.mkdir(exist_ok=True)
    dest = VIDEO_FOLDER / safe_name
    with _lock:
        with open(dest, "wb") as out:
            while True:
                chunk = fileobj.read(1024 * 1024)  # 1MB 分块
                if not chunk:
                    break
                out.write(chunk)
    return safe_name


def delete_video(name: str) -> dict:
    """删除视频文件；若被 results 引用则返回警告信息（仍允许删除）"""
    safe_name = os.path.basename(name)
    target = VIDEO_FOLDER / safe_name
    if not target.exists():
        raise FileNotFoundError(f"视频不存在: {safe_name}")
    used_by = sum(1 for r in load_results("results") if r.get("视频url") == safe_name)
    with _lock:
        target.unlink()
    # 同步从清单中移除
    current = load_video_list()
    if safe_name in current:
        current.remove(safe_name)
        df = pd.DataFrame({"视频文件名": current})
        with _lock:
            df.to_excel(VIDEO_XLSX, index=False)
    return {"deleted": safe_name, "was_used_by": used_by}


# ============================================================
# 结果数据（results.json / final.json）
# ============================================================

def load_results(source: str = "results") -> list:
    """读取 results 或 final 数据"""
    path = RESULTS_JSON if source == "results" else FINAL_JSON
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_results(data: list, source: str = "results"):
    """保存结果，JSON + CSV 双写（列顺序与原 CLI 产物一致）"""
    json_path = RESULTS_JSON if source == "results" else FINAL_JSON
    csv_path = RESULTS_CSV if source == "results" else FINAL_CSV
    if source == "results":
        column_order = ["data_id", "一级类目", "二级类目", "视频url", "视频时长",
                        "prompt", "参考答案", "难度", "状态", "备注"]
    else:
        column_order = ["data_id", "一级类目", "二级类目", "视频url", "视频时长",
                        "prompt", "参考答案", "难度", "校验结果", "问题详情"]
    with _lock:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        df = pd.DataFrame(data)
        existing = [c for c in column_order if c in df.columns]
        others = [c for c in df.columns if c not in column_order]
        if not df.empty:
            df = df[existing + others]
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")


def update_result_item(data_id: str, updates: dict, source: str = "results") -> dict:
    """编辑单条结果（prompt/参考答案/难度），返回更新后的记录"""
    allowed = {"prompt", "参考答案", "难度", "一级类目", "二级类目"}
    data = load_results(source)
    for r in data:
        if r.get("data_id") == data_id:
            for k, v in updates.items():
                if k in allowed:
                    r[k] = v
            save_results(data, source)
            return r
    raise KeyError(f"记录不存在: {data_id}")


def remove_result_items(data_ids: list, source: str = "results") -> int:
    """删除指定 data_id 的记录（用于标记重跑/删除），返回删除数量"""
    data = load_results(source)
    id_set = set(data_ids)
    kept = [r for r in data if r.get("data_id") not in id_set]
    removed = len(data) - len(kept)
    if removed > 0:
        save_results(kept, source)
    return removed


# ============================================================
# 任务清单（tasks.json）
# ============================================================

def load_tasks() -> list:
    if not TASKS_JSON.exists():
        return []
    try:
        with open(TASKS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
