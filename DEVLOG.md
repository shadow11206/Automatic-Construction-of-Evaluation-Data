# DEVLOG — 开发状态日志

> 本文件是项目的**开发状态记录**：做了什么、踩了什么坑、怎么解决的、当前卡在哪。
> 规则：倒序记录（最新在上）；每完成一个阶段必须更新；示例见文末。

---

## 2026-07-29 ｜ 立项与规划

### 状态
- 当前阶段：阶段 0（环境准备）未开始
- 下一阶段里程碑：HTML 原型风格确认 → 阶段 0 环境准备
- 阻塞：无

### 完成
- 调研现有 CLI 三步流水线代码（prepare_tasks / generate_vqa / validate / prompt_templates / video_utils），梳理痛点 6 项（见 spec.md 第 1 节）
- 与用户确认技术选型：**FastAPI + React(Ant Design) 前后端分离**、**全流程覆盖**（配置编辑 + 视频管理 + 三步执行 + 实时进度 + 结果查看/编辑/重跑）
- 确认环境基线：Node v22.22.0 / npm 10.9.4 / Python 3.14.5（venv 已有 dashscope 1.25.20、pandas 3.0.3、opencv；缺 fastapi/uvicorn/python-multipart）
- 确认 videos/ 现有 5 个视频（video_1~5.mp4，最大 43MB）
- 产出方案 plan.md（已获用户批准）+ 文档四件套：spec.md / todo.md / CLAUDE.md / DEVLOG.md
- 初始化 git 仓库（main 分支，首次提交 473a629）；GitHub 远程待配置（需用户提供 repo 地址）
- 应用户要求补充流程规范：todo.md 每阶段增加验证清单、失败重试与降级规则、worktree 并行隔离、阶段完成固定动作（DEVLOG → neat-freak → 推送 GitHub）
- 产出 HTML 静态原型 `design/mockup.html`（Ant Design 风格，含五个页面），待用户确认风格

### 关键决策
| 决策点 | 结论 | 原因 |
|--------|------|------|
| 长任务方案 | threading + 内存 JobState | 避免 Celery/Redis 重依赖，单机工具够用 |
| 进度推送 | 前端 1s 轮询 | 比 WebSocket 简单，满足需求 |
| 前端语言 | JS（不引 TS） | 降低复杂度 |
| 对原 CLI | 零业务逻辑改动，import 复用 | 保证可回退、数据格式兼容 |
| 配置存储 | xlsx 仍为唯一事实源，settings 存 server/settings.json | CLI/Web 混用兼容 |
| 设计风格 | Ant Design 风格（左侧导航 + 卡片式 + #1677ff 主色） | 数据工具标准形态，后续 React 直接用 antd 实现零偏差 |
| 并行开发 | git worktree，每页面一个分支 | 互不干扰，合并即清理 |

### 风险备忘
- generate_vqa.py 的配置是模块级常量，Web 端须在 job 启动前显式赋值，注意别让 CLI 默认值被污染
- 视频上传可能较大（现有最大 43MB），必须流式写盘
- pandas 3.0.3 是较新版本，读写 xlsx 时验证与 CLI 行为一致
- 项目刚 init git，GitHub 远程未配置，阶段 0 的 T0.3 依赖用户提供 repo

---

## 示例（格式参考，非真实记录）

## 2026-07-30 ｜ 【示例】阶段 1：后端数据层完成

### 状态
- 当前阶段：阶段 1 ✅ 完成 → 进入阶段 2
- 阻塞：无

### 完成
- T1.1~T1.6 全部完成，store.py 约 200 行
- 阶段 1 验证清单 3 项全部通过：CLI 兼容未破坏、掩码正确、xlsx 中文无乱码

### 踩坑记录
| 坑 | 现象 | 解决 |
|----|------|------|
| pandas 3.0 写 xlsx 默认索引列 | 写回的 xlsx 多出一列 `Unnamed: 0`，CLI 读入后列名识别报错 | `to_excel(..., index=False)`；已把"写 xlsx 必须 index=False"记入 CLAUDE.md 风格约定 |
| openpyxl 读空单元格返回 None | `int(None)` 抛 TypeError | 统一 `pd.notna()` 过滤 + strip，与原脚本行为对齐 |

### 关键决策
- 读写 xlsx 统一封装在 store.py，不允许路由层直接碰 pandas（防止散落的格式不一致 bug）

### 下一步
- 阶段 2 T2.1 JobState 与线程模型

### 同步动作
- [x] DEVLOG 已更新 ｜ [x] neat-freak 已运行 ｜ [x] 已推送 GitHub（commit a1b2c3d）

---

<!-- 新记录模板：
## YYYY-MM-DD ｜ 标题
### 状态（当前阶段 / 阻塞）
### 完成
### 踩坑记录（坑 / 现象 / 解决）
### 关键决策
### 下一步
### 同步动作（DEVLOG / neat-freak / push）
-->
