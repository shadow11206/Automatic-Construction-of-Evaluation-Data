# VQA 评测数据工具 Web 可视化改造 — 需求规格说明书

> 版本：v1.0 ｜ 日期：2026-07-29 ｜ 状态：已确认

---

## 1. 背景与问题

本项目是一个基于 Qwen VL 多模态大模型的 VQA（Video Question Answering）评测数据批量构建工具。当前为纯 CLI 三步工作流：

1. `python prepare_tasks.py` — 读取类目配置 + 视频列表 → 生成 `tasks.json`
2. `python generate_vqa.py` — 逐视频调 Qwen VL 生成问答 → 输出 `results.json/csv`
3. `python validate.py` — 自动校验 → 输出 `final.json/csv`

**现存痛点**：

| # | 痛点 | 影响 |
|---|------|------|
| P1 | 类目配置、视频清单需手动编辑 Excel 并另存为 xlsx | 操作繁琐、易出错（列名、格式、大小写） |
| P2 | 三个步骤需在终端依次手动执行 | 流程割裂，新人上手成本高 |
| P3 | 生成过程只有终端进度条，无法直观查看进度与日志 | 长任务（几十分钟）期间无法掌握状态 |
| P4 | 校验结果要打开 CSV 用 Excel 筛选复核，无法对照视频看问答 | 复核效率低，无法边播视频边审 |
| P5 | 修改 prompt/答案、标记重跑需手动编辑 JSON/CSV | 容易破坏文件格式，操作危险 |
| P6 | API Key、模型等参数需改代码或设环境变量 | 不友好，密钥有泄露风险 |

## 2. 目标

将 CLI 工作流升级为 **Web 可视化工作台**，覆盖「配置 → 视频管理 → 执行 → 监控 → 审核 → 重跑」全流程。

### 2.1 核心原则（约束）

- **C1 不破坏现有 CLI**：`prepare_tasks.py` / `generate_vqa.py` / `validate.py` 保持可独立命令行运行，后端通过 import 复用其函数，不重写核心逻辑
- **C2 数据格式兼容**：`tasks.json` / `results.json` / `final.json/csv` / `category_config.xlsx` / `video_list.xlsx` 的格式与字段完全不变，CLI 与 Web 可混用
- **C3 单命令启动**：前端构建产物由 FastAPI 托管，用户只需 `python server/main.py` 后打开浏览器
- **C4 API Key 安全**：密钥存本地 `server/settings.json`（gitignore），不写进代码、不随接口完整回显

## 3. 技术选型（已确认）

| 层 | 选型 | 理由 |
|----|------|------|
| 后端 | FastAPI + uvicorn | Python 原生，直接 import 复用现有模块 |
| 前端 | React 18 + Vite + Ant Design 5 | 表格编辑/上传/进度组件成熟，适合数据工具 |
| 任务执行 | threading 后台线程 + 内存 JobState | 避免引入 Celery/Redis 等重依赖 |
| 进度推送 | 前端 1s 轮询 `GET /api/pipeline/status` | 简单可靠，够用 |
| 视频预览 | FastAPI FileResponse（支持 Range） | 原生支持拖动播放 |

环境基线：Node v22 / npm 10 / Python 3.14 venv（已有 dashscope、pandas、opencv；需补 fastapi、uvicorn、python-multipart）。

## 4. 功能需求

### F1 工作台（Dashboard）

- F1.1 三步流程 Stepper 可视化展示：准备 → 生成 → 校验，标注每步状态（未开始/进行中/完成/失败）
- F1.2 每步提供一键执行按钮；步骤②为长任务，执行时展示：
  - 进度条（done/total + 百分比）
  - 当前正在处理的条目（data_id + 视频名）
  - 滚动日志区（最近 N 条）
  - 停止按钮（协作式中断，已生成进度不丢失）
- F1.3 统计卡片：总任务数、已完成、正常、需复核、校验通过率；类目分布与难度分布图（饼图/条形图）
- F1.4 断点续跑提示：检测到 results.json 已有正常条目时，显示"将跳过 N 条已完成"

### F2 类目配置

- F2.1 可编辑表格：一级类目 / 二级类目 / 数量，支持行新增、删除、编辑
- F2.2 一级类目输入时提示 `prompt_templates.py` 中已内置引导语的 5 个类目（动作识别/场景理解/时序推理/属性识别/事件理解）
- F2.3 难度权重配置（简单/中等/困难三个数值，和为 1.0，校验合法性）
- F2.4 保存写回 `category_config.xlsx`（列名固定：一级类目/二级类目/数量），保存前校验数量为正整数
- F2.5 实时显示总任务数（各数量求和）

### F3 视频管理

- F3.1 展示 `videos/` 目录下所有视频：文件名、时长（调用 `get_video_info`）、文件大小、是否在当前清单中
- F3.2 拖拽上传视频（Upload.Dragger，多文件），流式写盘，支持 mp4/avi/mov/mkv/webm 等
- F3.3 在线预览播放（视频流，支持拖动）
- F3.4 勾选哪些视频参与评测 → 保存写回 `video_list.xlsx`
- F3.5 删除视频（二次确认；若视频已被 tasks/results 引用则警告）

### F4 结果审核

- F4.1 结果表格：data_id / 一级类目 / 二级类目 / 视频 / 时长 / prompt / 参考答案 / 难度 / 状态|校验结果 / 问题详情
- F4.2 多维筛选：校验结果（通过/需复核/需重生成）、类目、难度、关键词搜索
- F4.3 行内编辑 prompt 与参考答案，保存写回 JSON + CSV
- F4.4 点击行打开 Drawer：左侧视频播放器，右侧问答详情，可边看边审边改
- F4.5 批量操作：勾选条目 →「标记重跑」（从 results.json 删除，下轮 generate 自动重新生成）/「删除」
- F4.6 数据源切换：results（生成结果）/ final（校验结果）

### F5 设置

- F5.1 DashScope API Key（密码输入框，接口只回显掩码如 `sk-****4fe6`）
- F5.2 模型名（默认 `qwen3.6-plus`，可改）
- F5.3 MAX_FRAMES（默认 64）
- F5.4 关键词校验开关（对应 validate.py 的 `ENABLE_KEYWORD_CHECK`）
- F5.5 保存到 `server/settings.json`，生成任务启动时热注入，无需重启服务

## 5. 接口规格（后端 API）

| 方法 | 路由 | 说明 |
|------|------|------|
| GET/PUT | `/api/config/categories` | 类目配置读取/保存 |
| GET/PUT | `/api/config/difficulty` | 难度权重读取/保存 |
| GET | `/api/videos` | 视频列表（元数据 + 是否在清单） |
| POST | `/api/videos/upload` | 上传视频（multipart） |
| DELETE | `/api/videos/{name}` | 删除视频 |
| PUT | `/api/videos/list` | 保存参与评测的视频清单 |
| GET | `/videos/{name}` | 视频流（Range 支持） |
| POST | `/api/pipeline/prepare` | 步骤①生成任务清单（同步） |
| POST | `/api/pipeline/generate` | 步骤②启动后台生成 |
| POST | `/api/pipeline/validate` | 步骤③校验（同步） |
| GET | `/api/pipeline/status` | 任务进度轮询 |
| POST | `/api/pipeline/stop` | 停止生成 |
| GET | `/api/results?source=results\|final&cat=&difficulty=&verdict=&q=` | 结果查询 |
| PUT | `/api/results/{data_id}` | 编辑 prompt/参考答案/难度 |
| POST | `/api/results/rerun` | 批量标记重跑（删条目） |
| GET/PUT | `/api/settings` | 设置读写 |

**JobState 结构**（内存，轮询返回）：

```json
{
  "step": "generate",
  "status": "idle | running | done | error | stopped",
  "total": 150, "done": 42, "skipped": 100,
  "current_item": "VQA_00143 / video_3.mp4",
  "logs": ["..."],
  "error": null
}
```

## 6. 项目结构（改造后）

```
项目根目录/
├── prepare_tasks.py / generate_vqa.py / validate.py   # 原 CLI（不动）
├── prompt_templates.py / video_utils.py               # 原模块（不动）
├── server/                # 【新增】后端
│   ├── main.py            # FastAPI app + 全部路由 + 静态托管 web/dist
│   ├── store.py           # xlsx/json 读写层、settings 持久化
│   ├── jobs.py            # 后台任务执行器（线程 + JobState + 锁）
│   └── settings.json      # 运行时生成，gitignore
├── web/                   # 【新增】前端
│   ├── package.json / vite.config.js
│   └── src/
│       ├── main.jsx / App.jsx
│       ├── api.js         # axios 封装
│       └── pages/         # Dashboard / CategoryConfig / VideoManager / ResultReview / Settings
├── category_config.xlsx / video_list.xlsx / videos/   # 原数据（不动）
└── tasks.json / results.* / final.*                   # 原产物（不动）
```

## 7. 非功能需求

- **N1 并发安全**：results.json 只允许 generate 线程写；JobState 加锁；generate 运行期间禁止再次启动 generate（接口返回 409）
- **N2 大文件上传**：流式写盘，不整读内存
- **N3 健壮性**：后端异常返回结构化错误 `{detail: "..."}`，前端 message 提示；generate 单条失败不中断整批（沿用原有重试+标记逻辑）
- **N4 可回退**：server/ 与 web/ 为纯新增目录，删除即还原为纯 CLI 项目
- **N5 文档**：README 增加「Web 界面」章节；requirements.txt 补全依赖

## 8. 验收标准

1. `python server/main.py` 单命令启动，浏览器访问 http://localhost:8000 可用
2. 界面上完成：编辑类目配置 → 上传/勾选视频 → 点三步按钮 → 实时看到进度 → 校验通过 → 在审核页筛选"需复核"条目、边播视频边编辑 prompt → 标记重跑 → 再次生成只重跑被标记的条目
3. 生成的 `final.csv` 与纯 CLI 流程产物格式一致（可互换使用）
4. 全程不改动原 5 个 Python 文件的业务逻辑（仅允许读取/调用）
5. API Key 不以明文出现在任何接口响应中（掩码回显）

## 9. 暂不包含（Out of Scope）

- 多用户 / 登录权限
- 多任务并行、分布式队列
- 类目引导语（CATEGORY_GUIDES）的可视化编辑（本期仍改 `prompt_templates.py`）
- Docker 化部署
- 移动端适配
