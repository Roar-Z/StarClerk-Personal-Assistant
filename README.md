# StarClerk · Windows 轻量 Personal Agent（MVP 骨架）

本地优先的个人助理：云端大模型为主、Ollama 兜底；后台巡检、托盘提醒、本地 RAG、长期记忆、悬浮对话面板。
无外部 IM 接入、无 ComputerUse、无多 Agent、无工作流引擎。

## 目录结构

```
StarClerk/
├─ backend/
│  ├─ run.py                    # 打包/本地启动入口
│  └─ app/
│     ├─ config.py              # 配置（.env，打包后读 EXE 同目录）
│     ├─ main.py                # FastAPI 装配 + SSE + 静态托管
│     ├─ launcher.py            # 桌面编排：uvicorn + 托盘 + 快捷键 + 窗口
│     ├─ db/
│     │  ├─ sqlite.py           # 连接/WAL/建表（含 usage、errors）
│     │  └─ models.py           # 会话·消息·任务·记忆·KV·用量·异常·套餐额度
│     ├─ vector/lancedb_store.py# 文档块 + 记忆向量检索
│     ├─ llm/client.py          # 统一 OpenAI 兼容调用 + tool calling + token 统计
│     ├─ agent/
│     │  ├─ state.py            # AgentState（ReAct 状态定义）
│     │  ├─ prompts.py          # 提示词与判定词表
│     │  ├─ nodes.py            # 记忆召回 / 计划 / 工具调用 / 总结判断
│     │  ├─ graph.py            # LangGraph 装配 + run_chat / run_patrol 入口
│     │  └─ memory.py           # 记忆抽取与召回
│     ├─ tools/
│     │  ├─ registry.py         # 工具 schema + 统一执行/失败收敛
│     │  ├─ web_search.py       # Tavily / DuckDuckGo（无需额外依赖）
│     │  └─ rag_search.py       # 本地 LanceDB 检索
│     ├─ rag/ingest.py          # 切块入库（txt/md/csv/log/json）
│     ├─ tasks/
│     │  ├─ scheduler.py        # 调度子线程：轮询任务 → 跑图 → 落库/提醒
│     │  └─ patrol.py           # 任务字段 → run_patrol 适配
│     ├─ notify/notifier.py     # 托盘气泡 + SSE 推送
│     ├─ desktop/               # tray.py / hotkey.py / window.py
│     └─ api/                   # chat / task / memory / rag / stats / config
├─ frontend/                    # Vue3 + Vite + ElementPlus（440×700 悬浮面板：自绘标题栏 + 底部六页导航）
│  ├─ src/{App.vue,api.ts,store.ts,desktop.ts}
│  └─ src/{components/{TitleBar,AppIcon}.vue, views/{Chat,Tasks,Memory,Knowledge,Settings,Usage}View.vue}
├─ build/starclerk.spec         # PyInstaller 单文件 EXE
├─ data/                        # 运行时生成：starcLerk.db / lancedb / uploads
└─ .env.example
```

## 模块职责（一句话）

| 模块 | 职责 |
|---|---|
| `llm/client.py` | 一套 httpx 打通全部 OpenAI 兼容厂商，云端失败自动降级 Ollama；`complete()` 带工具与用量 |
| `agent/graph.py` | 唯一主链路：记忆召回 → 计划 → 工具调用 → 总结判断，`run_chat` / `run_patrol` 两个入口 |
| `tools/registry.py` | 仅两个工具（网页搜索、本地 RAG），schema 直接喂给 tool calling |
| `vector/lancedb_store.py` | 嵌入式向量库，`documents` / `memories` 两表 |
| `db/sqlite.py` | 只存元数据，WAL 支持多线程并发；`usage`/`errors` 也在这里 |
| `tasks/scheduler.py` | 独立子线程轮询（默认 20s），串行执行，无 Celery/无独立进程 |
| `notify/notifier.py` | 提醒单一出口（托盘气泡 + SSE 弹层），调用方无感知 |
| `desktop/*` | pystray 托盘、pynput 全局热键、pywebview 无边框面板（拖标题栏移动、最小化、关闭只隐藏） |
| `api/*` | 六个分组：chat / task / memory / rag / stats / config，业务在 agent/rag/tasks |

## 启动流程

```
run.py
 └─ launcher.main()
     ├─ init_db()                       建表（WAL）
     ├─ 线程: uvicorn app.main:app      127.0.0.1:8756
     ├─ 等待 /api/health 就绪
     ├─ 线程: pystray 托盘              打开面板 / 退出
     ├─ 线程: pynput 热键               Ctrl+Alt+Space
     └─ 主线程: pywebview 窗口          关闭=隐藏到托盘
         └─ FastAPI lifespan: 启动调度子线程 → 到点跑巡查 → 落库 + notify()
```

## 本地开发

```bash
# 后端（推荐 Python 3.11/3.12，勿用 3.13+，lancedb/pyarrow 轮子不全）
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # 填 LLM_API_KEY
ollama pull bge-m3          # 向量模型（也可换云端 embedding）
python backend/run.py       # 或 uvicorn app.main:app --app-dir backend --reload

# 前端
cd frontend && npm i && npm run dev     # http://127.0.0.1:5173 ，/api 已代理
npm run build                           # 产物交给 FastAPI 托管，直接开 http://127.0.0.1:8756
```

## 悬浮面板（Step4）

440×700 无边框小窗，右上角两个按钮：最小化到任务栏、关闭收进托盘（进程不退）。
按住标题栏可拖动 —— 前端把鼠标屏幕坐标发过去，`desktop/window.py` 里的 Bridge 算出窗口新位置再 `move`，不用一路累加偏移。

底部六页，切页记在 hash 里，刷新或从托盘唤起不会跳回第一页：

| 页面 | 主要交互 |
|---|---|
| 对话 | 会话下拉切换/新建/删除，本地资料开关，回答下挂引用来源 |
| 巡检任务 | 新建、启停、立即执行、删除；右上角显示已用/上限，超额后端 409 |
| 记忆 | 手动加一条、逐条删除；对话里说“记住…”也会自动写入 |
| 资料库 | 选文件上传（txt/md/csv/log/json）、粘贴文本、按文档删除 |
| 模型 | 厂商预设、Key、embedding、断网降级、重建索引，保存写回 `.env` |
| 用量 | 7/30 天 token（按场景/模型/每天）、免费 ↔ Pro 切换 |

请求只走 `src/api.ts` 的 `req()`：非 2xx 取后端 `detail` 弹一次提示（600ms 内不重复），超时 180s 单独提示，页面里只管 loading 和列表状态。

## 打包 EXE

```bash
cd frontend && npm run build           # 产物 frontend/dist
pip install pyinstaller
pyinstaller build/starclerk.spec --noconfirm
# dist/StarClerk.exe + 同目录 .env（.env 不打进包，方便改配置）
```

## 兼容性基线（覆盖绝大多数笔记本）

- Win10 1903+ / Win11 x64，4GB 内存可用；WebView2 系统自带（无则自动退浏览器模式）
- 模型默认走云 API，仅向量化依赖本地 Ollama（可改云端 embedding 完全免装）
- 单进程 ~150MB 内存，空闲 CPU≈0；所有数据留在 `data/`，可直接整目录备份
- 快捷键冲突时改 `.env` 的 `HOTKEY`；不想用托盘/窗口可设 `TRAY_ENABLED=false`、`WINDOW_MODE=none`

## Agent 主链路（Step2）

```
START → recall ─→ plan ─┬─(有工具调用)→ act ─┬─(还有步数)→ recall
                        │                    └─(步数用尽)→ judge
                        └─(无工具调用)→ judge ─┬─(判断信息不足)→ recall
                                               └─(定稿)→ END
```

- 每轮思考前都查一次 LanceDB 记忆（迭代时用「问题 + 上一条观测」做查询）
- 每次最多 1 个工具调用，默认 3 轮封顶；"信息不足"只允许回退补检索 1 次
- 云端失败自动切 Ollama；工具异常收敛成观测，不会中断对话
- 巡检只回结论 + 提醒信号（`should_notify` / `level`），无异常时静默，避免托盘轰炸
- 网页搜索默认 DuckDuckGo，填 `TAVILY_API_KEY` 后自动改用 Tavily；`PATROL_ALLOW_WEB=false` 让后台任务不联网

## 接口层（Step3，仅 127.0.0.1）

所有接口挂在 `/api` 下，六个分组；非本机来源直接 403，CORS 也只放行 localhost。

| 分组 | 路由 | 入参 → 出参 |
|---|---|---|
| chat | `POST /api/chat` | `{session_id?, message, use_rag?, doc_scope?}` → `{session_id, answer, contexts, memories, steps, usage, should_notify}` |
| | `GET /api/chat/sessions`、`POST /api/chat/sessions` | `{title}` → 会话对象 |
| | `GET /api/chat/sessions/{sid}/messages`、`DELETE /api/chat/sessions/{sid}` | 消息数组 / `{ok}` |
| task | `GET /api/tasks`、`POST /api/tasks` | `{name, prompt, cron_minutes, doc_scope?}` → 任务；超额 409 |
| | `GET /api/tasks/quota` | → `{plan, is_pro, limit, used, remaining}` |
| | `PATCH /api/tasks/{id}`、`DELETE /api/tasks/{id}` | `{enabled}` → 任务 / `{ok}` |
| | `POST /api/tasks/{id}/run` | → `{result, should_notify, level, notice, elapsed_ms}` |
| memory | `GET /api/memory`、`POST /api/memory`、`DELETE /api/memory/{id}` | `{content, kind?}` → 记忆（向量失败仍保留文本） |
| rag | `POST /api/rag/upload`、`POST /api/rag/text` | 文件 / `{text, source}` → `{source, chunks}` |
| | `GET /api/rag/stats`、`GET /api/rag/documents`、`DELETE /api/rag/documents/{id}` | 统计 / 文档列表 |
| | `GET /api/rag/search?q=&top_k=` | 分块数组（不走模型，排查用） |
| stats | `GET /api/stats/overview` | 任务、知识库、24h 用量与异常 |
| | `GET /api/stats/usage?days=7` | `{totals, by_scope, by_model, daily}`（来自 SQLite `usage` 表） |
| | `GET /api/stats/errors?limit=30` | 最近异常（接口/调度捕获后入库） |
| config | `GET /api/config`、`PUT /api/config` | 配置（Key 掩码）；写回 `.env`，重启生效 |
| | `GET/PUT /api/config/plan` | `{plan: free\|pro}` → 额度；本地开关，无支付 |
| | `GET /api/config/providers`、`POST /api/config/test`、`POST /api/config/rebuild-vector` | 预设 / 连通性 / 重建索引 |

其它：`GET /api/health`、`GET /api/events`（SSE，推送巡检提醒）。

调度子线程要点：

- `threading.Thread(daemon=True)`，默认 20s 扫一次 `tasks`，**串行**执行，避免本地模型并发打爆
- `claim_task()` 先把 `next_run_at` 推到下一周期再执行，手动执行与定时执行不会撞车
- 结果写回 `last_result`，token 用量按 `scope=chat/patrol/memory` 落 `usage` 表
- 返回 `notice {title, body, level}`，托盘/SSE 直接消费；巡检本身失败也会 `warn` 提醒，不做静默失败

## 已知边界（MVP 有意不做）

PDF/Word 解析、多工具并行、反思子 Agent、ComputerUse、云同步、多人共享。扩展位已在 `tools/registry.py` 与 `agent/graph.py` 预留（加工具只需补 schema + handler）。
