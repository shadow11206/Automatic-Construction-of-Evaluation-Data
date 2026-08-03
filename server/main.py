"""
FastAPI 后端入口
启动方式：
    python server/main.py        # 开发/生产同入口，端口 8000
    # 或 uvicorn server.main:app --reload

提供：
- /api/*  REST 接口（配置、视频、流水线、结果、设置）
- /videos/{name}  视频流（Range 支持，前端播放器用）
- /       静态托管 web/dist（前端 build 产物，SPA fallback）
"""

import os
import sys
from pathlib import Path

# 支持 `python server/main.py` 直接运行（此时 sys.path[0] 是 server/）
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from server import store, jobs  # noqa: E402
from server.vl_adapter import test_profile  # noqa: E402
from prompt_templates import (  # noqa: E402
    CATEGORY_GUIDES, ABILITY_PATTERNS, USER_TO_INTERNAL, HUMAN_TONE_TEMPLATES,
)

app = FastAPI(title="VQA 评测数据工作台", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 全局异常处理：统一返回 {detail: "..."}
# ============================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    status = 500
    if isinstance(exc, (ValueError, KeyError)):
        status = 400
    elif isinstance(exc, FileNotFoundError):
        status = 404
    return JSONResponse(status_code=status, content={"detail": str(exc)})


# ============================================================
# 请求模型
# ============================================================

class CategoriesPayload(BaseModel):
    rows: list


class DifficultyPayload(BaseModel):
    weights: dict


class VideoListPayload(BaseModel):
    names: list


class ResultUpdatePayload(BaseModel):
    updates: dict


class RerunPayload(BaseModel):
    data_ids: list
    source: str = "results"


class SettingsPayload(BaseModel):
    settings: dict


# ============================================================
# 配置路由
# ============================================================

@app.get("/api/config/categories")
def get_categories():
    # 内置类目 = 新版 6 个能力维度（USER_TO_INTERNAL 的 key）+ 旧版 CATEGORY_GUIDES 的 5 个（向后兼容）
    builtin = list(USER_TO_INTERNAL.keys()) + list(CATEGORY_GUIDES.keys())
    return {
        "rows": store.load_categories(),
        "builtin_categories": builtin,
        "total": sum(c["数量"] for c in store.load_categories()),
    }


@app.put("/api/config/categories")
def put_categories(payload: CategoriesPayload):
    rows = store.save_categories(payload.rows)
    return {"saved": len(rows), "total": sum(r["数量"] for r in rows)}


@app.get("/api/config/difficulty")
def get_difficulty():
    return {"weights": store.load_settings().get("difficulty_weights")}


@app.get("/api/config/patterns")
def get_patterns():
    """返回 37 个题型范式 + 7 个人味模板，供前端类目配置页下拉选择

    返回结构：
        {
          "abilities": [
            {"name": "视觉基础能力", "internal": "感知层", "categories": ["动作识别", ...]},
            {"name": "时序能力", "internal": "时序层", "categories": [...]},
            ...
          ],
          "tone_templates": {"A-场景化追问": {"说明":..., "范例":...}, ...}
        }
    """
    # 按 USER_TO_INTERNAL 的顺序输出（用户命名优先）
    abilities = []
    seen_internal = set()
    for user_name, internal in USER_TO_INTERNAL.items():
        if internal in seen_internal:
            continue
        seen_internal.add(internal)
        categories = list(ABILITY_PATTERNS.get(internal, {}).keys())
        abilities.append({
            "name": user_name,
            "internal": internal,
            "categories": categories,
        })
    return {
        "abilities": abilities,
        "tone_templates": HUMAN_TONE_TEMPLATES,
    }


@app.put("/api/config/difficulty")
def put_difficulty(payload: DifficultyPayload):
    weights = payload.weights
    total = sum(float(v) for v in weights.values())
    if abs(total - 1.0) > 0.01:
        raise ValueError(f"难度权重之和必须为 1.0，当前为 {total:.2f}")
    for k in weights:
        if k not in ("简单", "中等", "困难"):
            raise ValueError(f"未知的难度等级: {k}")
    settings = store.load_settings()
    settings["difficulty_weights"] = {k: float(v) for k, v in weights.items()}
    store.save_settings(settings)
    return {"saved": True}


# ============================================================
# 视频路由
# ============================================================

@app.get("/api/videos")
def get_videos():
    return {"videos": store.scan_videos()}


@app.post("/api/videos/upload")
async def upload_video(file: UploadFile = File(...)):
    name = store.save_uploaded_video(file.filename, file.file)
    return {"uploaded": name}


@app.delete("/api/videos/{name}")
def delete_video(name: str):
    if jobs.get_status()["status"] == "running":
        raise HTTPException(409, "生成任务运行中，禁止删除视频")
    return store.delete_video(name)


@app.put("/api/videos/list")
def put_video_list(payload: VideoListPayload):
    names = store.save_video_list(payload.names)
    return {"saved": len(names)}


@app.post("/api/videos/batch-delete")
def batch_delete_videos(payload: VideoListPayload):
    """批量删除视频（复用单删逻辑，逐个返回结果；被引用的返回警告计数）"""
    if not payload.names:
        raise ValueError("未选择要删除的视频")
    if jobs.get_status()["status"] == "running":
        raise HTTPException(409, "生成任务运行中，禁止删除视频")
    deleted, failed = [], []
    for name in payload.names:
        try:
            deleted.append(store.delete_video(name))
        except Exception as e:
            failed.append({"name": name, "error": str(e)})
    return {"deleted": deleted, "failed": failed}


@app.post("/api/config/categories/import")
async def import_categories(file: UploadFile = File(...)):
    """解析上传的类目配置（xlsx/xls/csv），仅解析不落库，由前端预览后走保存接口"""
    rows = store.parse_categories_upload(file.file, file.filename)
    return {"rows": rows, "total": sum(r["数量"] for r in rows)}


@app.get("/videos/{name}")
def stream_video(name: str, request: Request):
    """视频流：FileResponse 自动支持 Range 请求（拖动播放）"""
    safe_name = os.path.basename(name)  # 防路径穿越
    path = store.VIDEO_FOLDER / safe_name
    if not path.exists() or path.suffix.lower() not in store.VIDEO_EXTS:
        raise HTTPException(404, f"视频不存在: {safe_name}")
    return FileResponse(path)


# ============================================================
# 流水线路由
# ============================================================

@app.post("/api/pipeline/prepare")
def api_prepare():
    return jobs.run_prepare()


@app.post("/api/pipeline/generate")
def api_generate():
    try:
        return jobs.start_generate()
    except jobs.JobRunningError as e:
        raise HTTPException(409, str(e))


@app.post("/api/pipeline/validate")
def api_validate():
    return jobs.run_validate()


@app.get("/api/pipeline/status")
def api_status():
    status = jobs.get_status()
    # 附加流水线整体状态（供顶部状态条）
    status["pipeline"] = {
        "tasks_count": len(store.load_tasks()),
        "results_count": len(store.load_results("results")),
        "results_normal": sum(1 for r in store.load_results("results") if r.get("状态") == "正常"),
        "final_exists": store.FINAL_JSON.exists(),
    }
    return status


@app.get("/api/pipeline/preview")
def api_preview():
    """预览下次生成会跑多少新任务、跳过多少旧任务（供按钮文案展示）"""
    return jobs.preview_generate()


@app.post("/api/pipeline/stop")
def api_stop():
    return jobs.stop_generate()


# ============================================================
# 结果路由
# ============================================================

@app.get("/api/results")
def get_results(
    source: str = Query("results", pattern="^(results|final)$"),
    cat: str = "",
    difficulty: str = "",
    verdict: str = "",
    q: str = "",
    exported: str = Query("", pattern="^(|yes|no)$"),
):
    data = _filter_results(source, cat, difficulty, verdict, q, exported)

    # 统计信息（筛选前的全集统计，供页面卡片）
    full = store.load_results(source)
    stat_field = "校验结果" if source == "final" else "状态"
    stats = {}
    for r in full:
        v = r.get(stat_field, "未知")
        stats[v] = stats.get(v, 0) + 1
    return {
        "items": data,
        "total": len(full),
        "stats": stats,
        "exported_ids": store.load_export_state().get("exported_ids", []),
    }


def _filter_results(source: str, cat: str, difficulty: str, verdict: str, q: str,
                    exported: str = "") -> list:
    """结果筛选（GET /api/results 与 /api/results/export 共用）
    exported: "" 全部 / "yes" 仅已导出 / "no" 仅未导出
    """
    data = store.load_results(source)
    if cat:
        data = [r for r in data if r.get("一级类目") == cat]
    if difficulty:
        data = [r for r in data if r.get("难度") == difficulty]
    if verdict:
        field = "校验结果" if source == "final" else "状态"
        data = [r for r in data if r.get(field) == verdict]
    if q:
        data = [r for r in data if q in str(r.get("prompt", "")) or q in str(r.get("参考答案", ""))]
    if exported in ("yes", "no"):
        exported_ids = set(store.load_export_state().get("exported_ids", []))
        if exported == "yes":
            data = [r for r in data if r.get("data_id") in exported_ids]
        else:
            data = [r for r in data if r.get("data_id") not in exported_ids]
    return data


@app.get("/api/results/export")
def export_results(
    source: str = Query("results", pattern="^(results|final)$"),
    cat: str = "",
    difficulty: str = "",
    verdict: str = "",
    q: str = "",
    exported: str = Query("", pattern="^(|yes|no)$"),
):
    """导出当前筛选视图为 xlsx，并记录导出状态（用于视频页已导出/未导出分辨）"""
    import io
    from datetime import datetime as _dt
    import pandas as pd

    data = _filter_results(source, cat, difficulty, verdict, q, exported)
    if not data:
        raise ValueError("当前筛选条件下没有可导出的数据")

    df = pd.DataFrame(data)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="VQA数据")
    buf.seek(0)

    filename = f"VQA_{source}_{_dt.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    ids = [r.get("data_id") for r in data if r.get("data_id")]
    mark_res = store.mark_exported(ids, source, filename)

    from urllib.parse import quote
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "X-Export-Count": str(len(ids)),
            "X-Export-New": str(mark_res["new_exported"]),
        },
    )


@app.put("/api/results/{data_id}")
def update_result(data_id: str, payload: ResultUpdatePayload, source: str = "results"):
    return store.update_result_item(data_id, payload.updates, source)


@app.post("/api/results/rerun")
def rerun_results(payload: RerunPayload):
    """标记重跑 = 从 results.json 删除条目，下轮 generate 自动补跑"""
    if jobs.get_status()["status"] == "running":
        raise HTTPException(409, "生成任务运行中，禁止修改结果")
    removed = store.remove_result_items(payload.data_ids, payload.source)
    return {"removed": removed, "hint": "已移除条目将在下次生成时自动重跑"}


# ============================================================
# 设置路由
# ============================================================

@app.get("/api/settings")
def get_settings():
    return store.get_masked_settings()


@app.put("/api/settings")
def put_settings(payload: SettingsPayload):
    new = payload.settings
    current = store.load_settings()

    # 数值校验
    if "max_frames" in new:
        mf = int(new["max_frames"])
        if not (1 <= mf <= 512):
            raise ValueError("max_frames 须在 1~512 之间")
        current["max_frames"] = mf
    if "max_retries" in new:
        current["max_retries"] = max(0, int(new["max_retries"]))
    if "keyword_check" in new:
        current["keyword_check"] = bool(new["keyword_check"])
    if "active_provider" in new:
        if new["active_provider"] not in current["providers"]:
            raise ValueError(f"未知平台: {new['active_provider']}")
        current["active_provider"] = new["active_provider"]
    if "providers" in new:
        for pname, prof in new["providers"].items():
            if pname not in current["providers"]:
                continue
            # 掩码回写的 Key 不覆盖（前端原样提交掩码值时忽略）
            for k in ("api_key", "base_url", "model"):
                if k in prof:
                    v = str(prof[k])
                    if k == "api_key" and "****" in v:
                        continue
                    current["providers"][pname][k] = v

    store.save_settings(current)
    return store.get_masked_settings()


@app.post("/api/settings/test")
def test_settings():
    """用当前激活平台的 profile 做连通性测试"""
    profile = store.get_active_profile()
    if profile["provider"] == "dashscope" and not profile.get("api_key"):
        import generate_vqa
        profile["api_key"] = generate_vqa.API_KEY  # 回退环境变量/CLI 默认
    return test_profile(profile)


# ============================================================
# 静态托管前端（web/dist 存在时）
# ============================================================

DIST = ROOT / "web" / "dist"


class SPAStaticFiles(StaticFiles):
    """SPA 静态托管：未知路径回退到 index.html（前端路由接管）"""

    async def get_response(self, path, scope):
        from starlette.exceptions import HTTPException as StarletteHTTPException
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as e:
            if e.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


if DIST.exists():
    app.mount("/", SPAStaticFiles(directory=str(DIST), html=True), name="spa")


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("VQA 评测数据工作台")
    print("浏览器访问: http://localhost:8000")
    if not DIST.exists():
        print("（提示: web/dist 不存在，仅提供 API；前端开发请用 cd web && npm run dev）")
    print("=" * 50)
    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=False)
