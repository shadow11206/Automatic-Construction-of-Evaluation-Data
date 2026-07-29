# DEVLOG — 开发日志

> 倒序记录（最新在上）。每次开发会话结束或关键节点更新。

---

## 2026-07-29 ｜ 立项与规划

### 完成
- 调研现有 CLI 三步流水线代码（prepare_tasks / generate_vqa / validate / prompt_templates / video_utils），梳理痛点 6 项（见 spec.md 第 1 节）
- 与用户确认技术选型：**FastAPI + React(Ant Design) 前后端分离**、**全流程覆盖**（配置编辑 + 视频管理 + 三步执行 + 实时进度 + 结果查看/编辑/重跑）
- 确认环境基线：Node v22.22.0 / npm 10.9.4 / Python 3.14.5（venv 已有 dashscope 1.25.20、pandas 3.0.3、opencv；缺 fastapi/uvicorn/python-multipart）
- 确认 videos/ 现有 5 个视频（video_1~5.mp4）
- 产出方案 plan.md（已获用户批准）
- 产出文档四件套：`spec.md`（需求规格 v1.0）、`todo.md`（任务拆解 T0~T7）、`CLAUDE.md`（协作指南）、`DEVLOG.md`（本文件）

### 关键决策
| 决策点 | 结论 | 原因 |
|--------|------|------|
| 长任务方案 | threading + 内存 JobState | 避免 Celery/Redis 重依赖，单机工具够用 |
| 进度推送 | 前端 1s 轮询 | 比 WebSocket 简单，满足需求 |
| 前端语言 | JS（不引 TS） | 降低复杂度 |
| 对原 CLI | 零业务逻辑改动，import 复用 | 保证可回退、数据格式兼容 |
| 配置存储 | xlsx 仍为唯一事实源，settings 存 server/settings.json | CLI/Web 混用兼容 |

### 下一步
- 阶段 0：环境准备（装依赖、建目录、gitignore）→ 见 todo.md T0.1/T0.2

### 风险备忘
- generate_vqa.py 的配置是模块级常量，Web 端须在 job 启动前显式赋值，注意别让 CLI 默认值被污染
- 视频上传可能较大（现有最大 43MB），必须流式写盘
- pandas 3.0.3 是较新版本，读写 xlsx 时注意与原脚本行为一致性（CLI 用同版本，理论上无差异）

---

<!-- 新记录模板：
## YYYY-MM-DD ｜ 标题
### 完成
### 关键决策
### 问题与解决
### 下一步
-->
