# CLAUDE.md — 项目协作指南

> 本文件为 AI 协作者（Claude / CodeFlicker 等）提供项目上下文与开发规范。改动代码前请先读完本文件与 `spec.md`。

## 项目一句话

基于 Qwen VL 的视频 VQA 评测数据批量构建工具。原为三步 CLI（prepare → generate → validate），正在改造为 FastAPI + React(Ant Design) 的 Web 可视化工作台。需求与验收标准见 `spec.md`，任务拆解见 `todo.md`，进展记录见 `DEVLOG.md`。

## 目录结构

```
prepare_tasks.py      # 步骤①：Excel 配置 → tasks.json（不调模型）
generate_vqa.py       # 步骤②：tasks.json → 调 Qwen VL → results.json/csv（长耗时，支持断点续跑）
validate.py           # 步骤③：results.json → 校验 → final.json/csv（不调模型）
prompt_templates.py   # Prompt 模板 + CATEGORY_GUIDES 类目引导语映射（扩展类目改这里）
video_utils.py        # OpenCV 视频信息/抽帧 + DashScope API 封装
server/               # 【新增】FastAPI 后端：main.py(路由) / store.py(读写) / jobs.py(后台任务)
web/                  # 【新增】React + Vite + AntD 前端，src/pages/ 五个页面
videos/               # 视频文件
category_config.xlsx  # 类目配置（一级类目/二级类目/数量）
video_list.xlsx       # 参与评测的视频文件名清单
tasks.json / results.json|csv / final.json|csv   # 流水线产物
```

## 最重要的约束（违反 = 返工）

1. **不许改动原 5 个 Python 文件的业务逻辑**（prepare_tasks / generate_vqa / validate / prompt_templates / video_utils）。后端只 import 调用它们的函数。唯一允许的运行时干预：job 启动前给 `generate_vqa` 模块常量赋值（`API_KEY` / `MODEL` / `MAX_FRAMES`）。
2. **数据文件格式冻结**：tasks.json、results.json、final.csv、两个 xlsx 的字段名与结构不许变，CLI 和 Web 必须能混用同一份数据。
3. **API Key 安全**：只存 `server/settings.json`（已 gitignore）；任何 GET 接口不得返回完整 Key，必须掩码（如 `sk-****4fe6`）。
4. **可回退**：server/、web/ 是纯新增目录，不许向根目录散文件；删掉这两个目录项目必须恢复为纯 CLI 可用状态。

## 关键技术决策（已定，勿擅自更改）

- 长任务用 **threading 后台线程 + 内存 JobState（加锁）**，不引入 Celery/Redis
- 进度用 **前端 1s 轮询** `GET /api/pipeline/status`，不用 WebSocket
- 前端 **JS 不引 TS**；UI 库用 **Ant Design 5**；构建产物 `web/dist` 由 FastAPI 静态托管，单命令 `python server/main.py` 启动
- 断点续跑沿用 generate_vqa 的 fingerprint 机制（data_id+视频+类目 匹配才跳过）
- "标记重跑" = 从 results.json 删除对应条目，下轮 generate 自动补跑
- results.json 只有 generate 线程可写；generate 运行中接口层要防重入（409）

## 开发流程（git worktree 并行隔离）

- 项目已 init git（main 分支）；GitHub 远程在阶段 0 T0.3 配置
- **并行任务必须用 worktree 隔离**，每个独立任务一个 worktree：
  ```bash
  git worktree add ../vqa-web-feat-dashboard -b feat/page-dashboard
  # 在该目录开发、自测 → 回主目录合并：
  git merge feat/page-dashboard
  git worktree remove ../vqa-web-feat-dashboard && git branch -d feat/page-dashboard
  ```
- 开发完成合并回 main 后**立即清理 worktree 和分支**，不允许长期悬挂
- 串行任务（阶段 0~5、阶段 7）直接在 main 开发，不建 worktree

## 工作流（每次动工必须遵守）

1. **动工前先读 `todo.md`**，找到当前阶段和下一个未完成任务
2. **按 todo.md 顺序执行，不要跳阶段**；上一阶段验证清单没过完，不进入下一阶段
3. 每完成一步子任务：**先跑该阶段的「验证清单」→ 确认全部通过 → 勾选 `[x]` → 再读下一步**
4. **验证不通过：修好再继续，不允许跳过验证直接勾选**
5. 每完成一个阶段后的固定动作：
   - 更新 `DEVLOG.md`（状态/完成/踩坑/决策/下一步）
   - 运行 neat-freak 同步文档和记忆
   - commit 并推送 GitHub

## 失败处理与降级

- 同一问题**最多重试 3 次**，且**每次必须换思路**（换方案/换库/换路径），不要硬试同一个方法
- 3 次后仍失败：
  1. 该任务在 todo.md 标记 `[!]` ⚠️ 阻塞，注明原因
  2. 先做同阶段中**不依赖它**的其他任务
  3. 如果它阻塞了整个阶段（后续全依赖它），**停止并向用户报告**：卡在哪、试过哪 3 种方法、建议的解决方案，等用户决策
- 禁止：跳过失败任务假装完成、删除验证清单条目、为通过验证而改验证标准

## 常用命令

```bash
# 后端（venv 在项目根）
source venv/bin/activate
python server/main.py                 # 启动 Web（:8000，托管 web/dist）

# 前端开发
cd web && npm install
npm run dev                           # :5173，proxy /api 与 /videos 到 :8000
npm run build                         # 产出 web/dist

# 原 CLI（仍需保持可用）
python prepare_tasks.py && python generate_vqa.py && python validate.py
```

## 数据流速查

```
category_config.xlsx ─┐
                      ├→ prepare → tasks.json ─→ generate(调Qwen VL) ─→ results.json/csv ─→ validate ─→ final.json/csv
video_list.xlsx ──────┘                              ↑ 每条5~30s，每5条落盘，失败重试2次标记"需复核"
```

- generate 结果字段：`data_id, 一级类目, 二级类目, 视频url, 视频时长, prompt, 参考答案, 难度, 状态(正常/需复核), 备注`
- validate 追加字段：`校验结果(通过/需复核/需重生成), 问题详情`

## 代码风格

- Python：与原文件风格一致 —— 模块顶部中文 docstring、配置区集中、函数带中文 docstring、print 输出中文进度
- 前端：函数组件 + Hooks；接口调用统一走 `src/api.js`；错误统一 `message.error`
- 注释用中文；提交前更新 todo.md 状态并写 DEVLOG.md
