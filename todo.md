# TODO — VQA Web 可视化改造任务拆解

> 依据 spec.md v1.0 拆解。状态标记：`[ ]` 待办 / `[~]` 进行中 / `[x]` 完成 / `[!]` ⚠️ 阻塞
> 执行规则（详见 CLAUDE.md「工作流」）：
> 1. 动工前先读本文件，按阶段顺序执行，不跳阶段
> 2. 每完成一步子任务：先跑该阶段的「验证清单」→ 全部通过 → 勾选 `[x]` → 再读下一步
> 3. 验证不通过：修好再继续，不允许跳过验证勾选
> 4. 失败处理：同一问题最多重试 3 次且每次换思路；3 次仍失败标记 `[!]` 阻塞，先做同阶段不依赖它的任务；阻塞整个阶段则停下来向用户报告（卡在哪/试过什么/建议方案）
> 5. 并行任务用 git worktree 隔离（见 CLAUDE.md「开发流程」）
> 更新日期：2026-07-29 ｜ 全部阶段已完成（含 T0.3 GitHub 推送）

---

## 阶段 0：环境准备

- [x] T0.1 `pip install fastapi uvicorn python-multipart requests` 并写入 `requirements.txt`（连同原有 dashscope/opencv-python/pandas/openpyxl/tqdm）
- [x] T0.2 创建 `server/` 与 `web/` 目录结构；`.gitignore` 增加 `server/settings.json`、`web/node_modules`、`web/dist`、`venv/`、`__pycache__/`、`.DS_Store`
- [x] T0.3 配置 GitHub 远程仓库（shadow11206/Automatic-Construction-of-Evaluation-Data），完成首次推送（2026-07-30）

**✅ 阶段 0 验证清单**
- [x] `venv/bin/python -c "import fastapi, uvicorn, multipart"` 无报错
- [x] `git check-ignore server/settings.json web/node_modules` 命中
- [x] `git remote -v` 显示 GitHub 地址且 `git push` 成功

---

## 阶段 1：后端 — 数据层（server/store.py）

- [x] T1.1 类目配置读写：`load_categories()` / `save_categories(rows)`（pandas 读写 category_config.xlsx，固定列名 一级类目/二级类目/数量，校验数量为正整数）
- [x] T1.2 难度权重读写：持久化到 server/settings.json
- [x] T1.3 视频清单读写：读 video_list.xlsx；保存勾选清单写回 xlsx
- [x] T1.4 视频目录扫描：遍历 videos/，调用 `video_utils.get_video_info` 返回 {name, duration, size, in_list}
- [x] T1.5 结果读写：load/save results.json 与 final.json（保存时同步刷新对应 CSV，复用 generate_vqa.save_both / validate.save_both）
- [x] T1.6 设置读写：`load_settings()` / `save_settings()`；多平台 profile 结构（active_provider + providers{}，各平台独立 api_key/base_url/model，切换不丢内容）；API Key 掩码函数 `mask_key()`

**✅ 阶段 1 验证清单**
- [x] 单元自测脚本跑通：读 xlsx → 改一行 → 写回 → 用原 `prepare_tasks.py` 命令行重跑确认仍正常（CLI 兼容未破坏）
- [x] `mask_key("sk-abcdef1234")` 输出不含完整密钥
- [x] 写回后的 xlsx 用 Excel/Numbers 打开列名、中文无乱码
- [x] settings.json 多平台结构读写往返一致；切换 active_provider 后各 profile 内容保持

---

## 阶段 2：后端 — 任务执行器（server/jobs.py）

- [x] T2.1 JobState：step/status/total/done/skipped/current_item/logs（deque 上限 200）/error + threading.Lock
- [x] T2.2 prepare 执行函数：复用 prepare_tasks 逻辑，注入当前难度权重，写 tasks.json，返回分配摘要
- [x] T2.3 validate 执行函数：读 results.json → validate_record 逐条校验 → save_both 写 final，返回统计
- [x] T2.4 generate 后台线程：启动前注入 settings 到 generate_vqa 模块（API_KEY/MODEL/MAX_FRAMES）；沿用 fingerprint 断点续跑；每条更新 JobState；每 5 条落盘
- [x] T2.5 协作式停止：stop_flag，每条处理前检查；停止后落盘并置 status=stopped
- [x] T2.6 防重入：status==running 时拒绝再次启动（返回 409）
- [x] T2.7 多平台适配层 `server/vl_adapter.py`：统一入口 `call_vl_model()`；dashscope 委托 `video_utils.call_qwen_vl`；其余平台 OpenCV 抽帧 → base64 → OpenAI 兼容 HTTP（requests）；generate 线程改走适配层

**✅ 阶段 2 验证清单**
- [x] python 内直接调用 run_prepare() → tasks.json 生成且摘要与 CLI 输出一致
- [x] python 内直接调用 run_validate() → final.json/csv 与 CLI 产物 diff 无结构差异
- [x] 模拟启动两次 generate：第二次被 409 拒绝
- [x] stop_flag 置位后：线程在当前条结束后退出，results.json 已落盘、status=stopped
- [x] vl_adapter：dashscope 路径真实调通 1 条；OpenAI 兼容路径用 mock server 验证请求体格式（messages 含 base64 图片数组）

---

## 阶段 3：后端 — API（server/main.py）

- [x] T3.1 FastAPI app 骨架：CORS（localhost）、全局异常处理（结构化 {detail}）
- [x] T3.2 配置路由：GET/PUT `/api/config/categories`、`GET/PUT /api/config/difficulty`
- [x] T3.3 视频路由：GET `/api/videos`、POST `/api/videos/upload`（流式写盘）、DELETE `/api/videos/{name}`（引用检查警告）、PUT `/api/videos/list`
- [x] T3.4 视频流：GET `/videos/{name}`（FileResponse，Range 支持，文件名防路径穿越）
- [x] T3.5 流水线路由：POST prepare / generate / validate / stop，GET `/api/pipeline/status`
- [x] T3.6 结果路由：GET `/api/results`（筛选）、PUT `/api/results/{data_id}`、POST `/api/results/rerun`
- [x] T3.7 设置路由：GET/PUT `/api/settings`（GET 掩码所有平台 Key）；POST `/api/settings/test` 连通性测试
- [x] T3.8 静态托管：web/dist 存在时挂载 `/`，SPA fallback
- [x] T3.9 入口：`python server/main.py` 直接启动（uvicorn :8000）

**✅ 阶段 3 验证清单**
- [x] `python server/main.py` 启动无报错，`curl localhost:8000/api/pipeline/status` 返回 JobState JSON
- [x] curl 全接口冒烟：categories 读写 / videos 列表 / settings（确认响应中 Key 已掩码）
- [x] 上传一个小视频再 GET /videos/{name}，curl `-H "Range: bytes=0-1023"` 返回 206
- [x] `curl /videos/../etc/passwd` 之类路径穿越请求被拒绝

---

## 阶段 4：后端链路自测

- [x] T4.1 curl 链路：prepare → status → validate（不调模型部分）
- [x] T4.2 curl 链路：generate 启动 / 进度轮询 / 停止 / 断点续跑（小批量 1~2 条真实调用）

**✅ 阶段 4 验证清单**
- [x] prepare 后 tasks.json 任务数与类目配置合计一致
- [x] generate 跑 1 条成功写入 results.json；重复启动时该条被跳过（断点续跑生效）
- [x] 中途 stop 后 results.json 内容完整可解析

---

## 阶段 5：前端 — 设计原型与骨架（web/）

- [x] T5.0 HTML 静态原型 `design/mockup.html`：确认设计风格与五个页面布局（单文件、无构建，浏览器直接打开预览）— 2026-07-29 完成
- [x] T5.1 Vite + React 脚手架；依赖：antd、react-router-dom、axios、dayjs、@ant-design/plots（按 T5.0 确认的风格实现）
- [x] T5.2 vite.config.js：proxy `/api` 与 `/videos` → http://localhost:8000
- [x] T5.3 api.js：axios 实例 + 全部接口封装 + 统一错误 message
- [x] T5.4 App 布局：左侧菜单 + 顶部流水线状态条 + react-router

**✅ 阶段 5 验证清单**
- [x] T5.0 原型经用户确认风格后再动 T5.1
- [x] `npm run dev` 启动，访问 :5173 页面渲染无控制台报错
- [x] dev 环境下 `/api/pipeline/status` 经 proxy 成功返回

---

## 阶段 6：前端 — 五个页面（可并行，用 git worktree 隔离）

> 并行策略：T5 骨架合并回 main 后，为每个页面建 worktree 分支（如 `feat/page-dashboard`），各自开发、各自验证，合并一个删一个 worktree。T6.1 与 T6.4 依赖 api.js 的接口约定，先于其他页面定稿接口封装。

- [x] T6.1 Dashboard（F1）：Stepper + 每步执行按钮 + 进度条/当前条目/滚动日志（running 时 1s 轮询）+ 停止按钮 + 统计卡片与分布图
- [x] T6.2 类目配置页（F2）：可编辑表格（增删改）+ 内置类目下拉提示 + 总任务数实时合计 + 难度权重（校验和=1）+ 保存
- [x] T6.3 视频管理页（F3）：Dragger 多文件上传 + 表格（预览/时长/大小/参与勾选/删除）+ 播放器 Modal + 保存清单
- [x] T6.4 结果审核页（F4）：筛选栏 + 表格 + 行内编辑 + Drawer 视频并排审核 + 批量标记重跑/删除 + results/final 切换
- [x] T6.5 设置页（F5）：平台选择器（DashScope/OpenAI/OpenRouter/智谱/自定义）+ 各平台 profile 表单（Key 密码框/Base URL 自动填充可改/模型名）+ MAX_FRAMES/重试次数/关键词开关 + 保存 + 连通性测试；按 mockup 原型实现

**✅ 阶段 6 验证清单（每个页面合并前各自过一遍）**
- [x] 页面在 dev 环境对接真实后端，所有按钮/表单/筛选实际操作成功
- [x] 接口报错时页面有 message 提示，不白屏不卡死
- [x] 浏览器控制台无 error 级别报错
- [x] 合并回 main 后 `npm run build` 通过、worktree 已清理

---

## 阶段 7：联调与交付

- [x] T7.1 `npm run build` → FastAPI 托管 dist，单命令 `python server/main.py` 端到端验证
- [x] T7.2 端到端走查 spec.md 第 8 节验收标准 1~5，小批量真实生成一轮
- [x] T7.3 README 增加「Web 界面」章节
- [x] T7.4 修复联调问题，更新 DEVLOG.md

**✅ 阶段 7 验证清单（= 项目总验收）**
- [x] 全新终端单命令启动，浏览器完成：改配置 → 传视频 → 三步执行 → 看进度 → 审核改 prompt → 标记重跑 → 只重跑被标记条目
- [x] final.csv 与纯 CLI 流程产物格式一致（字段、编码 utf-8-sig）
- [x] `git diff` 确认原 5 个 Python 文件业务逻辑零改动
- [x] 任何接口响应中无完整 API Key
- [x] main 分支推送 GitHub，worktree 全部清理

---

## 每阶段完成后的固定动作

1. 勾选本阶段全部任务与验证清单
2. 更新 `DEVLOG.md`（做了什么/踩坑/决策/下一步）
3. 运行 neat-freak 同步文档和记忆
4. commit 并推送 GitHub

## 依赖关系

```
T0 → T1 → T2 → T3 → T4 → T5.0(原型确认) → T5.1~5.4(骨架) → T6(页面, worktree 并行) → T7(联调)
```
