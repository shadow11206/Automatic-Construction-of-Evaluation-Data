# TODO — VQA Web 可视化改造任务拆解

> 依据 spec.md v1.0 拆解。状态标记：`[ ]` 待办 / `[~]` 进行中 / `[x]` 完成
> 更新日期：2026-07-29

---

## 阶段 0：环境准备

- [ ] T0.1 `pip install fastapi uvicorn python-multipart` 并写入 `requirements.txt`（连同原有 dashscope/opencv-python/pandas/openpyxl/tqdm）
- [ ] T0.2 创建 `server/` 与 `web/` 目录结构；`.gitignore` 增加 `server/settings.json`、`web/node_modules`、`web/dist`

## 阶段 1：后端 — 数据层（server/store.py）

- [ ] T1.1 类目配置读写：`load_categories()` / `save_categories(rows)`（pandas 读写 category_config.xlsx，固定列名 一级类目/二级类目/数量，校验数量为正整数）
- [ ] T1.2 难度权重读写：持久化到 server/settings.json
- [ ] T1.3 视频清单读写：读 video_list.xlsx；保存勾选清单写回 xlsx
- [ ] T1.4 视频目录扫描：遍历 videos/，调用 `video_utils.get_video_info` 返回 {name, duration, size, in_list}
- [ ] T1.5 结果读写：load/save results.json 与 final.json（保存时同步刷新对应 CSV，复用 generate_vqa.save_both / validate.save_both）
- [ ] T1.6 设置读写：`load_settings()` / `save_settings()`（API Key、模型、MAX_FRAMES、关键词校验开关）；GET 接口返回时 API Key 掩码

## 阶段 2：后端 — 任务执行器（server/jobs.py）

- [ ] T2.1 JobState 数据类：step/status/total/done/skipped/current_item/logs/deque 上限 200 条/error + threading.Lock
- [ ] T2.2 prepare 执行函数：复用 prepare_tasks 的读取/分配逻辑，注入当前难度权重，写 tasks.json，返回分配摘要
- [ ] T2.3 validate 执行函数：读 results.json → validate_record 逐条校验 → save_both 写 final，返回统计
- [ ] T2.4 generate 后台线程：启动前注入 settings 到 generate_vqa 模块（API_KEY/MODEL/MAX_FRAMES）；沿用 fingerprint 断点续跑；每条更新 JobState；每 5 条落盘
- [ ] T2.5 协作式停止：stop_flag，每条处理前检查；停止后落盘并置 status=stopped
- [ ] T2.6 防重入：status==running 时拒绝再次启动（调用方返回 409）

## 阶段 3：后端 — API（server/main.py）

- [ ] T3.1 FastAPI app 骨架：CORS（localhost）、全局异常处理（结构化 {detail}）
- [ ] T3.2 配置路由：GET/PUT `/api/config/categories`、`GET/PUT /api/config/difficulty`
- [ ] T3.3 视频路由：GET `/api/videos`、POST `/api/videos/upload`（流式写盘）、DELETE `/api/videos/{name}`（引用检查警告）、PUT `/api/videos/list`
- [ ] T3.4 视频流：GET `/videos/{name}`（FileResponse，Range 支持，文件名安全校验防路径穿越）
- [ ] T3.5 流水线路由：POST prepare / generate / validate / stop，GET `/api/pipeline/status`
- [ ] T3.6 结果路由：GET `/api/results`（source/类目/难度/校验结果/关键词筛选）、PUT `/api/results/{data_id}`、POST `/api/results/rerun`
- [ ] T3.7 设置路由：GET/PUT `/api/settings`（GET 掩码 Key）
- [ ] T3.8 静态托管：web/dist 存在时挂载 `/`，SPA fallback 到 index.html
- [ ] T3.9 入口：`python server/main.py` 可直接启动（uvicorn.run，端口 8000）

## 阶段 4：后端自测

- [ ] T4.1 curl 自测：categories 读写、videos 列表、settings 读写（确认掩码）
- [ ] T4.2 curl 自测：prepare → status → validate 全链路（不调模型的部分）
- [ ] T4.3 curl 自测：generate 启动/进度/停止/断点续跑（小批量 1~2 条真实调用验证）

## 阶段 5：前端 — 骨架（web/）

- [ ] T5.1 Vite + React 脚手架；依赖：antd、react-router-dom、axios、dayjs、@ant-design/plots
- [ ] T5.2 vite.config.js：proxy `/api` 与 `/videos` → http://localhost:8000
- [ ] T5.3 api.js：axios 实例 + 全部接口封装 + 统一错误 message 提示
- [ ] T5.4 App 布局：左侧菜单（工作台/类目配置/视频管理/结果审核/设置）+ 顶部流水线状态条 + react-router

## 阶段 6：前端 — 五个页面

- [ ] T6.1 Dashboard（F1）：Stepper + 每步执行按钮 + 进度条/当前条目/滚动日志（1s 轮询 running 时）+ 停止按钮 + 统计卡片与分布图
- [ ] T6.2 类目配置页（F2）：可编辑表格（增删改）+ 内置类目下拉提示 + 总任务数实时合计 + 难度权重（校验和=1）+ 保存
- [ ] T6.3 视频管理页（F3）：Dragger 多文件上传 + 表格（预览/时长/大小/参与勾选/删除）+ 播放器 Modal + 保存清单
- [ ] T6.4 结果审核页（F4）：筛选栏 + 表格 + 行内编辑 prompt/参考答案 + Drawer 视频并排审核 + 勾选批量标记重跑/删除 + results/final 数据源切换
- [ ] T6.5 设置页（F5）：表单（Key 密码框/模型/MAX_FRAMES/关键词开关）+ 保存

## 阶段 7：联调与交付

- [ ] T7.1 `npm run build` → FastAPI 托管 dist，单命令端到端验证
- [ ] T7.2 端到端走查验收标准 1~5（见 spec.md 第 8 节），小批量真实生成一轮
- [ ] T7.3 README 增加「Web 界面」章节（启动方式、页面说明、与 CLI 混用说明）
- [ ] T7.4 修复联调中发现的问题，DEVLOG 记录

---

## 依赖关系

```
T0 → T1 → T2 → T3 → T4 → T5(骨架) → T6(页面) → T7(联调)
T5 骨架完成后，T6 各页面可并行
```
