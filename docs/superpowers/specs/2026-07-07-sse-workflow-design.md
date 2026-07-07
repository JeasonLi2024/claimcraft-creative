# SSE 工作流流式改造设计文档

**日期**：2026-07-07
**作者**：brainstorming session
**状态**：待评审
**关联**：T1_spec.md、workflow-optimization-design.md、frontend-display-design.md

---

## 1. 背景与目标

### 1.1 现状

当前 claimcraft-creative 的核心工作流基于 LangGraph 构建，包含 7 个节点：

```
START → preclassify → ocr → classify → extract → [review?] → evidence_chain → complaint → END
```

工作流通过 [backend/api/views.py](file:///d:/claimcraft-creative/backend/api/views.py) 的 `CaseWorkflowView` 触发，使用 `async_to_sync(workflow.ainvoke)(...)` **同步阻塞单次返回**全部产物。前端不直接调用工作流 API，而是通过分散的 REST 端点（`evidenceApi.list`、`timelineApi.list`、`complaintApi.get`）轮询/手动刷新已被工作流写入 DB 的结果。

### 1.2 问题

- **用户无法看到中间进度**：工作流运行数分钟（OCR 180s + extract 300s），用户只能看到"等待"
- **前端体验割裂**：需手动刷新多个页面才能看到不同节点的产物
- **无 token 流式**：complaint_node 生成长文本时无法逐字输出，体验远不如 ChatGPT
- **HITL 体验差**：review_node 中断后需手动触发 resume，无实时反馈

### 1.3 目标

引入 SSE（Server-Sent Events）流式推送，实现：

1. **完全替换**同步端点，每个节点的重要输出都能被前端消费
2. **混合事件粒度**：节点级事件 + LLM token 流（complaint 逐字输出）
3. **长连接保活 HITL**：SSE 流在 interrupt 期间保持打开，resume 后继续推送
4. **集成到 EvidencePage**：左侧步进轨道 + 主区产物流，自动折叠历史节点
5. **断连恢复**：自动重连 + 事件续传

### 1.4 非目标

- 不改造工作流节点本身的业务逻辑（7 个节点保持不变）
- 不引入 Celery/Redis 等重型依赖（保留升级路径）
- 不改造现有事后查看页面（TimelinePage/ComplaintPage 保持 REST 读取）

---

## 2. 决策汇总

| 维度 | 决策 |
|---|---|
| SSE 范围 | 完全替换同步端点 |
| 事件粒度 | 混合：节点级事件 + LLM token 流 |
| HITL 协议 | 长连接保活，POST resume 后同连接继续推送 |
| 实时视图位置 | 集成到 EvidencePage |
| 进度面板布局 | 方案 C：左侧步进轨道（120px）+ 主区产物流 |
| 产物折叠策略 | 自动折叠历史节点（当前 + 最新完成展开） |
| complaint 流式 | 方案 A：产物流区块内联流式，带光标闪烁 |
| 断连恢复 | 自动重连 + 事件续传（基于 EventDepot） |
| 事后衔接 | 原地渲染完整状态 + 链接跳转到各页面 |
| 后端技术路径 | LangGraph `astream_events(v2)` + EventDepot 保留站模式 |

---

## 3. 整体架构

### 3.1 核心架构：事件保留站模式

采用**生产者-消费者解耦**模式，而非"SSE 端点直接消费 astream_events"。工作流作为生产者在后台运行，每次产生输出立即写入 EventDepot 并通知；SSE 端点作为消费者从 EventDepot 读取事件推送给前端。

```
┌──────────────────────────────────────────────────────────────────┐
│  生产者（后台任务）                                               │
│  workflow.astream_events(v2)                                     │
│    → SSEEventMapper 过滤映射                                     │
│    → EventDepot.persist(thread_id, event)  ← 每次输出立即写入    │
│    → NotifyEmitter.notify(thread_id)       ← 通知订阅者          │
└──────────────────────────────────────────────────────────────────┘
                              │ 持久化
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  EventDepot（事件保留站，Postgres 表）                            │
│  thread_id | event_id | event_type | payload | created_at        │
│  索引: (thread_id, event_id) UNIQUE                              │
│  保留期: 24h（定时清理任务）                                      │
└──────────────────────────────────────────────────────────────────┘
                              ▲ 读取
                              │
┌──────────────────────────────────────────────────────────────────┐
│  消费者（SSE 端点）                                               │
│  CaseWorkflowStreamView (GET /api/cases/<id>/workflow/stream/)   │
│    1. 读取 Last-Event-ID header 或 query 参数                    │
│    2. 从 EventDepot 批量回放漏掉的事件 (event_id > last)         │
│    3. 订阅 NotifyEmitter(thread_id) 获取新事件通知               │
│    4. 收到通知 → 拉取新事件 → SSE 推送                           │
│    5. 每 15s 心跳                                                 │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 保留站模式的优势

| 痛点 | 直接 astream_events → SSE | 保留站模式 |
|---|---|---|
| 前端断连 | 工作流可能被取消；漏掉的事件无法补 | 工作流继续运行，事件累积在保留站；前端重连从 last_event_id 续传 |
| 多客户端 | 同一工作流只能一个 SSE 连接 | 多客户端可同时订阅同一 thread_id |
| HITL 长时间暂停 | SSE 连接需保活数分钟甚至更久 | 连接可断开，resume 后重新订阅即可拉取后续事件 |
| 事件审计 | 无 | 保留站天然是审计日志 |
| 部署复杂度 | 需 ASGI + 长连接保活 | 后台任务可同步或异步；SSE 端点只需轮询/订阅保留站 |

### 3.3 组件分层

```
┌─────────────────────────────────────────────────────────────┐
│  前端 EvidencePage                                          │
│  ├─ WorkflowStreamPanel（新增）                             │
│  │  ├─ NodeTrack（左侧步进轨道，7 节点）                    │
│  │  └─ ProductStream（主区产物流，自动折叠历史）            │
│  │     └─ ComplaintStreamBlock（token 内联流式 + 光标）     │
│  └─ case-store.workflow（新增 Zustand slice）               │
├─────────────────────────────────────────────────────────────┤
│  SSE 客户端（新增 lib/sse-client.ts）                       │
│  ├─ EventSource 封装 + 自动重连 + last_event_id            │
│  └─ 事件分发到 store                                        │
├─────────────────────────────────────────────────────────────┤
│  后端 API 层                                                │
│  ├─ CaseWorkflowStartView（新增，POST 启动后台任务）        │
│  ├─ CaseWorkflowStreamView（新增，GET SSE 流）              │
│  └─ CaseWorkflowResumeView（新增，POST HITL 校正提交）      │
├─────────────────────────────────────────────────────────────┤
│  事件基础设施（新增）                                        │
│  ├─ EventDepot（Postgres 表 + 持久化/读取）                 │
│  ├─ NotifyEmitter（Postgres LISTEN/NOTIFY 封装）            │
│  ├─ WorkflowRunner（后台任务，消费 astream_events）         │
│  └─ SSEEventMapper（astream_events → SSE 事件过滤映射）     │
├─────────────────────────────────────────────────────────────┤
│  工作流层（保持不变）                                        │
│  ├─ graph.py / nodes/* / state.py                           │
│  └─ checkpointer（复用现有 PostgresSaver）                   │
└─────────────────────────────────────────────────────────────┘
```

### 3.4 关键设计决策

1. **三端点协作**：
   - `CaseWorkflowStartView`（POST `/workflow/start/`）：启动后台任务，返回 thread_id + stream_url
   - `CaseWorkflowStreamView`（GET `/workflow/stream/`）：SSE 流，从 EventDepot 读取推送
   - `CaseWorkflowResumeView`（POST `/workflow/resume/`）：HITL 校正提交，恢复后台任务

2. **工作流本体不动**：仅切换调用方式从 `ainvoke` 到 `astream_events(version="v2")`，节点代码零改动。

3. **部署适配**：`gunicorn` WSGI → `uvicorn` ASGI，Dockerfile 修改启动命令。

4. **向后兼容**：原 `CaseWorkflowView` 同步端点标记 deprecated 保留 1 个版本，便于回滚。

---

## 4. SSE 事件协议

### 4.1 事件格式

SSE 事件统一格式：`event: <type>\ndata: <json>\n\n`。所有事件携带 `event_id`（递增序号，用于断连续传）、`thread_id`、`timestamp`。

**Last-Event-ID 传递**：由于浏览器原生 `EventSource` 不支持自定义 header，统一通过 query parameter `?last_event_id=N` 传递。后端 `CaseWorkflowStreamView` 读取 query 参数（同时兼容 `Last-Event-ID` header，供非浏览器客户端使用）。

### 4.2 生命周期事件（后端控制流）

| event | data 结构 | 触发时机 |
|---|---|---|
| `workflow.start` | `{thread_id, case_id, evidence_ids, started_at, event_id}` | 流建立后立即发送 |
| `workflow.heartbeat` | `{event_id, ts}` | 每 15s 一次，保活 |
| `workflow.resumed` | `{event_id, missed_node_completes, current_node, current_node_started_at}` | 断连重连后首事件 |
| `workflow.complete` | `{event_id, thread_id, case_id, total_duration_ms, errors:[]}` | complaint_node 完成或全部节点结束 |
| `workflow.error` | `{event_id, message, node?, recoverable}` | 不可恢复的致命错误，流终止 |

### 4.3 节点级事件（7 节点通用）

| event | data 结构 | 触发时机 |
|---|---|---|
| `node.start` | `{event_id, node, input_summary, ts}` | `on_chain_start` 命中工作流节点 |
| `node.progress` | `{event_id, node, message, progress?, ts}` | 节点内部进展（如"3/5 证据已分类"） |
| `node.complete` | `{event_id, node, products, duration_ms, ts}` | `on_chain_end`，products 为该节点产物 |
| `node.error` | `{event_id, node, message, recoverable, ts}` | Saga 降级触发，recoverable=true 表示工作流继续 |

### 4.4 节点产物结构（`node.complete` 的 `products` 字段）

每个节点的 `products` 结构直接对应 [backend/api/agents/state.py](file:///d:/claimcraft-creative/backend/api/agents/state.py) 中节点输出：

```jsonc
// preclassify_node.complete
{"evidence_preclassify_results": [
  {"evidence_id":1, "evidence_code":"EV001", "evidence_category":"invoice",
   "ocr_summary":"...", "confidence":0.92}
]}

// ocr_node.complete
{"evidence_ocr_results": [
  {"evidence_id":1, "evidence_code":"EV001", "ocr_corrected_text":"...",
   "ocr_strategy_used":"llm_vision", "ocr_status":"success", "evidence_category":"invoice"}
]}

// classify_node.complete
{"evidence_classify_results": [
  {"evidence_id":1, "evidence_code":"EV001", "evidence_category":"invoice",
   "category_label":"发票", "confidence":0.95}
]}

// extract_node.complete
{"evidence_extract_results": [
  {"evidence_id":1, "fields":[
    {"field_name":"invoice_no", "field_value":"INV2024001",
     "field_category":"invoice_basic", "confidence":0.94}
  ], "needs_human_review":false, "cache_hit":false, "source_hash":"..."}
],
"needs_human_review": false}

// evidence_chain_node.complete
{"evidence_chain": [
  {"datetime":"2024-03-15T10:00", "event":"下单购买", "category":"order",
   "evidence_codes":["EV001"], "chain_order":1}
]}

// complaint_node.complete
{"complaint_draft": {"title":"...", "content":"...", "template_type":"platform", "tone":"firm"}}
```

### 4.5 LLM Token 流事件（仅 complaint_node）

| event | data 结构 | 触发时机 |
|---|---|---|
| `complaint.token` | `{event_id, delta, accumulated_length}` | `on_chat_model_stream` 且当前节点为 complaint |
| `complaint.done` | `{event_id, final_content, title, tone}` | complaint_node `on_chain_end` |

**过滤规则**：仅当 `astream_events` 的当前节点为 complaint_node 时，才将 `on_chat_model_stream` 映射为 `complaint.token`。其他 LLM 节点（classify/extract/evidence_chain）的 token 流**不推送**，避免事件过载，仅推送节点级 `node.complete`。

### 4.6 HITL resume 协调事件

| event | data 结构 | 触发时机 |
|---|---|---|
| `review.interrupt` | `{event_id, fields_to_review:[{evidence_id, field_name, current_value, confidence}], message, resume_endpoint}` | `on_interrupt` 命中 review_node |
| `review.resumed` | `{event_id, applied_corrections, corrections_count}` | 收到 POST resume 后，推送校正应用结果 |
| `review.skipped` | `{event_id, reason}` | review_node 判断无需审核直接跳过 |

**协调流程**：
1. SSE 流推送 `review.interrupt` 后**保持打开**，继续发心跳。原 WorkflowRunner 后台任务在 `interrupt()` 处暂停（LangGraph 自动通过 checkpointer 保存状态），任务从全局注册表移除但 thread_id 保留在 Case 表
2. 前端展示校正 UI，用户提交后 POST `/api/cases/<id>/workflow/resume/` 携带 `{corrections:[...]}`
3. 后端 `CaseWorkflowResumeView` 调用 `workflow.ainvoke(Command(resume=...), config)`，**启动新的 WorkflowRunner 后台任务**（复用同一 thread_id，LangGraph 从 checkpointer 恢复中断前状态）
4. 新 WorkflowRunner 向同一 EventDepot 写入 `review.resumed` 事件 + 后续节点事件
5. SSE 端点通过 LISTEN 收到通知，继续推送 `review.resumed` → `evidence_chain.start` → `complaint.start` ...

**任务生命周期说明**：HITL 中断期间无后台任务运行（资源释放），resume 时新建任务。这避免了长时间保活空转任务。

### 4.7 断连恢复事件

前端重连时携带 `last_event_id`（query parameter，见 4.1），后端根据 `thread_id` + `last_event_id`：

- 从 EventDepot 读取 `event_id > last_event_id` 的所有事件并回放
- 推送 `workflow.resumed` 事件：`{event_id, missed_node_completes:[...], current_node, current_node_started_at}`
- 订阅 LISTEN，继续正常推送后续事件

---

## 5. 后端实现

### 5.1 EventDepot（事件保留站）

复用现有 checkpointer 的 Postgres 实例（[graph.py 第 128-135 行](file:///d:/claimcraft-creative/backend/api/agents/graph.py#L128-L135) 的连接池），新建表：

```sql
CREATE TABLE sse_event_depot (
    id BIGSERIAL PRIMARY KEY,
    thread_id VARCHAR(100) NOT NULL,
    event_id BIGINT NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(thread_id, event_id)
);
CREATE INDEX idx_depot_thread_event ON sse_event_depot(thread_id, event_id);
CREATE INDEX idx_depot_created ON sse_event_depot(created_at);
```

**event_id 分配**：每个 thread_id 维护独立计数器（从 1 开始），由生产者通过 `SELECT COALESCE(MAX(event_id),0)+1 FROM sse_event_depot WHERE thread_id=? FOR UPDATE` 分配（行锁保证并发安全）。

**Python 实现**（`backend/api/agents/sse_event_depot.py`）：

```python
class EventDepot:
    """SSE 事件保留站：持久化事件 + 支持断连续传"""

    def __init__(self, pool: ConnectionPool = None):
        self.pool = pool or get_checkpointer_pool()

    async def persist(self, thread_id: str, event_type: str, payload: dict) -> int:
        """持久化事件，返回分配的 event_id"""
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT COALESCE(MAX(event_id),0)+1 FROM sse_event_depot "
                    "WHERE thread_id=%s FOR UPDATE",
                    (thread_id,)
                )
                event_id = (await cur.fetchone())[0]
                await cur.execute(
                    "INSERT INTO sse_event_depot (thread_id, event_id, event_type, payload) "
                    "VALUES (%s, %s, %s, %s)",
                    (thread_id, event_id, event_type, Json(payload))
                )
                return event_id

    async def get_events_after(self, thread_id: str, last_event_id: int) -> list:
        """获取 event_id > last_event_id 的所有事件（断连续传）"""
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT event_id, event_type, payload, created_at "
                    "FROM sse_event_depot WHERE thread_id=%s AND event_id > %s "
                    "ORDER BY event_id ASC",
                    (thread_id, last_event_id)
                )
                return await cur.fetchall()

    async def is_workflow_completed(self, thread_id: str) -> bool:
        """检查工作流是否已完成（有 workflow.complete 或 workflow.error 事件）"""
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT 1 FROM sse_event_depot WHERE thread_id=%s "
                    "AND event_type IN ('workflow.complete','workflow.error') LIMIT 1",
                    (thread_id,)
                )
                return await cur.fetchone() is not None
```

### 5.2 NotifyEmitter（LISTEN/NOTIFY 封装）

```python
class NotifyEmitter:
    """通过 Postgres LISTEN/NOTIFY 通知 SSE 端点有新事件"""

    def __init__(self, pool: ConnectionPool = None):
        self.pool = pool or get_checkpointer_pool()

    @staticmethod
    def _channel_name(thread_id: str) -> str:
        return f"evt_{thread_id.replace('-','_')}"

    async def notify(self, thread_id: str, event_id: int):
        """通知订阅者有新事件"""
        channel = self._channel_name(thread_id)
        async with self.pool.connection() as conn:
            await conn.execute(f"NOTIFY {channel}, %s", (str(event_id),))

    async def subscribe(self, thread_id: str, callback):
        """订阅指定 thread_id 的事件通知，阻塞直到连接关闭"""
        channel = self._channel_name(thread_id)
        async with self.pool.connection() as conn:
            await conn.add_notify_listener(callback)
            await conn.execute(f"LISTEN {channel}")
            # 阻塞等待，由外部取消
            await asyncio.Event().wait()
```

### 5.3 SSEEventMapper（事件过滤映射）

```python
class SSEEventMapper:
    """将 astream_events(v2) 事件过滤映射为 SSE 协议事件"""

    NODE_NAMES = {"preclassify","ocr","classify","extract","review","evidence_chain","complaint"}
    current_node: str | None = None
    _node_start_times: dict[str, datetime] = {}  # node name → start timestamp

    async def map(self, raw_event: dict) -> list[SSEEvent]:
        """返回 0~N 个 SSE 事件（多数 1:1，token 可能聚合）"""
        event_type = raw_event.get("event")
        name = raw_event.get("name", "")
        tags = raw_event.get("tags", [])

        if event_type == "on_chain_start" and name in self.NODE_NAMES:
            self.current_node = name
            self._node_start_times[name] = datetime.utcnow()  # 记录开始时间用于计算 duration
            return [SSEEvent("node.start", {
                "node": name,
                "input_summary": self._summarize_input(raw_event.get("data", {})),
                "ts": datetime.utcnow().isoformat()
            })]

        if event_type == "on_chain_end" and name in self.NODE_NAMES:
            products = self._extract_products(name, raw_event.get("data", {}).get("output", {}))
            start_time = self._node_start_times.pop(name)  # 从 start 时记录的时间戳
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            sse_events = [SSEEvent("node.complete", {
                "node": name,
                "products": products,
                "duration_ms": duration_ms,
                "ts": datetime.utcnow().isoformat()
            })]
            if name == "complaint":
                sse_events.append(SSEEvent("complaint.done", {
                    "final_content": products.get("complaint_draft", {}).get("content", ""),
                    "title": products.get("complaint_draft", {}).get("title", ""),
                    "tone": products.get("complaint_draft", {}).get("tone", "")
                }))
            self.current_node = None
            return sse_events

        if event_type == "on_chat_model_stream" and self.current_node == "complaint":
            chunk = raw_event.get("data", {}).get("chunk")
            if chunk and chunk.content:
                # accumulated_length 由 EventDepot 在 persist 时根据已存储的 token 数计算
                return [SSEEvent("complaint.token", {
                    "delta": chunk.content
                })]
            return []

        if event_type == "on_interrupt":
            return [SSEEvent("review.interrupt", raw_event.get("data", {}))]

        if event_type == "on_chain_error" and name in self.NODE_NAMES:
            return [SSEEvent("node.error", {
                "node": name,
                "message": str(raw_event.get("data", {}).get("error", "")),
                "recoverable": True  # Saga 已处理
            })]

        return []  # 其他事件过滤掉

    def _extract_products(self, node: str, output: dict) -> dict:
        """从节点输出中提取对应 state 字段作为产物"""
        field_map = {
            "preclassify": ["evidence_preclassify_results"],
            "ocr": ["evidence_ocr_results"],
            "classify": ["evidence_classify_results"],
            "extract": ["evidence_extract_results", "needs_human_review"],
            "evidence_chain": ["evidence_chain"],
            "complaint": ["complaint_draft"]
        }
        return {k: output.get(k) for k in field_map.get(node, [])}
```

### 5.4 WorkflowRunner（后台任务）

```python
class WorkflowRunner:
    """工作流后台运行器：消费 astream_events，写入 EventDepot"""

    _task_registry: dict[str, asyncio.Task] = {}  # thread_id → Task

    async def run_and_persist(
        self, case_id: int, thread_id: str,
        initial_state: dict | None = None,
        resume: dict | None = None
    ):
        """后台任务入口，与 SSE 端点解耦"""
        depot = EventDepot()
        emitter = NotifyEmitter()

        try:
            workflow_start_time = datetime.utcnow()  # 记录工作流开始时间

            # 1. 持久化 workflow.start 事件（首次启动）
            if not resume:
                await depot.persist(thread_id, "workflow.start", {
                    "thread_id": thread_id, "case_id": case_id,
                    "evidence_ids": initial_state.get("evidence_ids", []),
                    "started_at": workflow_start_time.isoformat()
                })
                await emitter.notify(thread_id, 1)

            # 2. 消费 astream_events 并写入保留站
            config = {"configurable": {"thread_id": thread_id}}
            if resume:
                stream = workflow.astream_events(
                    Command(resume=resume), config=config, version="v2"
                )
            else:
                stream = workflow.astream_events(initial_state, config=config, version="v2")

            mapper = SSEEventMapper()
            async for raw_event in stream:
                for sse_event in await mapper.map(raw_event):
                    eid = await depot.persist(thread_id, sse_event.type, sse_event.payload)
                    await emitter.notify(thread_id, eid)
                    if sse_event.type == "workflow.complete":
                        break

            # 3. 持久化 workflow.complete 事件
            total_duration_ms = int((datetime.utcnow() - workflow_start_time).total_seconds() * 1000)
            final_eid = await depot.persist(thread_id, "workflow.complete", {
                "thread_id": thread_id, "case_id": case_id,
                "total_duration_ms": total_duration_ms, "errors": []
            })
            await emitter.notify(thread_id, final_eid)

        except Exception as e:
            error_eid = await depot.persist(thread_id, "workflow.error", {
                "message": str(e), "recoverable": False
            })
            await emitter.notify(thread_id, error_eid)
        finally:
            self._task_registry.pop(thread_id, None)

    def start_in_background(self, case_id, thread_id, initial_state=None, resume=None):
        """启动后台任务（不阻塞调用方）"""
        task = asyncio.create_task(
            self.run_and_persist(case_id, thread_id, initial_state, resume)
        )
        self._task_registry[thread_id] = task
        return task
```

### 5.5 API 端点

```python
# backend/api/views.py（新增）

class CaseWorkflowStartView(APIView):
    """启动工作流：创建后台任务，返回 thread_id"""

    def post(self, request, case_id):
        case = get_object_or_404(Case, id=case_id)
        thread_id = case.thread_id or f"case-{case.id}-{int(time.time())}"
        case.thread_id = thread_id
        case.save()

        initial_state = self._build_initial_state(case, request.data)
        runner = WorkflowRunner()
        runner.start_in_background(
            case_id=case.id, thread_id=thread_id, initial_state=initial_state
        )

        return Response({
            "thread_id": thread_id,
            "stream_url": f"/api/cases/{case.id}/workflow/stream/?thread_id={thread_id}"
        })


class CaseWorkflowStreamView(APIView):
    """SSE 流式端点：从 EventDepot 读取事件推送给前端"""

    def get(self, request, case_id):
        case = get_object_or_404(Case, id=case_id)
        thread_id = request.query_params.get("thread_id") or case.thread_id
        last_event_id = int(request.headers.get("Last-Event-ID",
                          request.query_params.get("last_event_id", 0)))

        async def event_stream():
            depot = EventDepot()
            emitter = NotifyEmitter()

            # 1. 回放漏掉的事件（断连续传）
            missed = await depot.get_events_after(thread_id, last_event_id)
            for evt in missed:
                yield format_sse(evt)
                if evt.event_type in ("workflow.complete", "workflow.error"):
                    return

            # 2. 检查工作流是否已结束
            if await depot.is_workflow_completed(thread_id):
                return

            # 3. 订阅新事件通知
            queue = asyncio.Queue()
            async def on_notify(pid, channel, payload):
                await queue.put(int(payload))
            subscribe_task = asyncio.create_task(
                emitter.subscribe(thread_id, on_notify)
            )

            # 4. 心跳 + 新事件推送循环
            current_last = missed[-1].event_id if missed else last_event_id
            try:
                while True:
                    try:
                        await asyncio.wait_for(queue.get(), timeout=15)
                        new_events = await depot.get_events_after(thread_id, current_last)
                        for evt in new_events:
                            yield format_sse(evt)
                            current_last = evt.event_id
                            if evt.event_type in ("workflow.complete", "workflow.error"):
                                return
                    except asyncio.TimeoutError:
                        yield ": heartbeat\n\n"
            finally:
                subscribe_task.cancel()

        response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


class CaseWorkflowResumeView(APIView):
    """HITL 校正提交：恢复后台工作流任务"""

    def post(self, request, case_id):
        case = get_object_or_404(Case, id=case_id)
        thread_id = case.thread_id
        corrections = request.data["corrections"]

        runner = WorkflowRunner()
        runner.start_in_background(
            case_id=case.id, thread_id=thread_id,
            resume={"corrections": corrections}
        )

        return Response({"status": "resumed", "thread_id": thread_id})
```

### 5.6 后台任务执行方式

**选项 A（推荐，轻量）**：`asyncio.create_task` + 全局任务注册表
- 适合单进程 ASGI 部署（uvicorn workers）
- 任务注册表用 `dict[thread_id, asyncio.Task]` 管理
- 进程崩溃则任务丢失，依赖 checkpointer 恢复

**选项 B（重型，预留升级路径）**：Celery + asyncio worker
- 适合多进程/多机部署
- 引入新依赖（celery + redis/rabbitmq）
- 与项目现有 Django 架构集成度高

当前采用选项 A，后续扩展再升级 B。

### 5.7 部署适配

- **ASGI 切换**：`requirements.txt` 添加 `uvicorn[standard]`，Dockerfile 后端启动改为 `uvicorn claimcraft.asgi:application --workers 4 --worker-class uvicorn.workers.UvicornWorker`
- **Nginx 配置**：SSE 路径禁用缓冲（`proxy_buffering off; proxy_cache off;`），超时设为 600s
- **Postgres 连接池**：复用 checkpointer 的 `psycopg_pool.ConnectionPool`（[graph.py 第 128-135 行](file:///d:/claimcraft-creative/backend/api/agents/graph.py#L128-L135)），LISTEN 连接单独管理

### 5.8 事件清理

新增 Django management command + cron 定时任务：

```python
# backend/api/management/commands/cleanup_sse_events.py
class Command(BaseCommand):
    def handle(self, *args, **options):
        ttl_hours = int(os.environ.get("SSE_EVENT_DEPOT_TTL_HOURS", 24))
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM sse_event_depot WHERE created_at < NOW() - INTERVAL '%s hours'",
                (ttl_hours,)
            )
        self.stdout.write(f"Cleaned up SSE events older than {ttl_hours}h")
```

cron 配置：`0 * * * * cd /app && python manage.py cleanup_sse_events`

---

## 6. 前端实现

### 6.1 Design Read

**阅读判断**：这是 B2B 内部工具的工作流实时面板，面向法律/理赔专业人员，采用 Linear/Notion 风格的极简功能性设计语言，基于 Tailwind v4 + 现有项目栈（React 19 + Zustand 5 + React Router v7）。

**Dial 配置**：
- `DESIGN_VARIANCE: 4`（功能性优先，避免装饰性不对称）
- `MOTION_INTENSITY: 3`（功能性动效：状态过渡、token 流光标，无装饰动画）
- `VISUAL_DENSITY: 5`（工作流需展示多节点产物，中等密度）

### 6.2 组件分层

```
frontend/src/
├── pages/EvidencePage.tsx                    （修改：集成 WorkflowStreamPanel）
├── components/workflow/                      （新增目录）
│   ├── WorkflowStreamPanel.tsx              （顶层容器）
│   ├── NodeTrack.tsx                        （左侧步进轨道）
│   ├── ProductStream.tsx                    （主区产物流容器）
│   ├── ProductBlock.tsx                     （通用产物区块，自动折叠）
│   ├── ComplaintStreamBlock.tsx             （complaint token 流式区块）
│   ├── ReviewInterruptPanel.tsx             （HITL 校正 UI）
│   └── NodeStatusIcon.tsx                   （节点状态图标）
├── lib/sse-client.ts                        （新增：EventSource 封装）
├── lib/workflow-events.ts                   （新增：SSE 事件类型定义 + dispatch）
├── stores/case-store.ts                     （修改：新增 workflow slice）
└── lib/api.ts                               （修改：新增 workflowApi 模块）
```

### 6.3 SSE 客户端封装

```typescript
// frontend/src/lib/sse-client.ts
export class WorkflowSSEClient {
  private eventSource: EventSource | null = null;
  private lastEventId = 0;
  private reconnectAttempts = 0;
  private readonly maxReconnect = 5;
  private readonly baseDelay = 1000;

  constructor(
    private streamUrl: string,
    private handlers: SSEHandlers,
  ) {}

  connect() {
    const url = `${this.streamUrl}&last_event_id=${this.lastEventId}`;
    this.eventSource = new EventSource(url, { withCredentials: true });

    const eventTypes = [
      'workflow.start', 'workflow.resumed', 'workflow.complete', 'workflow.error',
      'node.start', 'node.progress', 'node.complete', 'node.error',
      'complaint.token', 'complaint.done',
      'review.interrupt', 'review.resumed', 'review.skipped'
    ];
    eventTypes.forEach(type => {
      this.eventSource.addEventListener(type, (e) => this.dispatch(e));
    });
    this.eventSource.onerror = () => this.handleDisconnect();
  }

  private dispatch(e: MessageEvent) {
    const data = JSON.parse(e.data);
    this.lastEventId = Math.max(this.lastEventId, data.event_id);
    this.handlers.onEvent(data);
    if (data.event_type === 'workflow.complete' || data.event_type === 'workflow.error') {
      this.close();
    }
  }

  private handleDisconnect() {
    if (this.reconnectAttempts >= this.maxReconnect) {
      this.handlers.onFatalError('SSE 连接中断，已达最大重连次数');
      return;
    }
    const delay = this.baseDelay * Math.pow(2, this.reconnectAttempts);
    this.reconnectAttempts++;
    setTimeout(() => this.connect(), delay);
  }

  close() {
    this.eventSource?.close();
    this.eventSource = null;
  }
}
```

**Last-Event-ID 传递**：浏览器原生 `EventSource` 不支持自定义 header，改用 query parameter `?last_event_id=N`。

### 6.4 Zustand Workflow Slice

```typescript
// frontend/src/stores/case-store.ts（新增 slice）
interface WorkflowState {
  isRunning: boolean;
  threadId: string | null;
  currentNode: string | null;
  nodeStates: Record<string, NodeStatus>;
  productBlocks: ProductBlock[];
  complaintDraft: { title: string; content: string; tone: string } | null;
  reviewInterrupt: ReviewInterruptData | null;
  errors: WorkflowError[];
  connectionState: 'idle'|'connecting'|'connected'|'reconnecting'|'error';
}

interface WorkflowActions {
  startWorkflow: (caseId: number, evidenceIds: number[]) => Promise<void>;
  submitReviewCorrections: (corrections: Correction[]) => Promise<void>;
  clearWorkflow: () => void;
  applySSEEvent: (event: SSEEvent) => void;
}

interface NodeStatus {
  status: 'idle' | 'running' | 'completed' | 'error' | 'skipped';
  startedAt?: string;
  completedAt?: string;
  durationMs?: number;
  products?: any;
  error?: string;
}

interface ProductBlock {
  id: string;
  node: string;
  type: 'preclassify'|'ocr'|'classify'|'extract'|'evidence_chain'|'complaint';
  products: any;
  completedAt: string;
  collapsed: boolean;
}
```

**applySSEEvent 事件分发**：

```typescript
applySSEEvent: (event) => {
  const { event_type, ...payload } = event;
  switch (event_type) {
    case 'workflow.start':
      set({ isRunning: true, threadId: payload.thread_id, connectionState: 'connected' });
      break;
    case 'node.start':
      set((s) => ({
        currentNode: payload.node,
        nodeStates: { ...s.nodeStates, [payload.node]: { status: 'running', startedAt: payload.ts } },
      }));
      break;
    case 'node.complete': {
      const productBlock = buildProductBlock(payload.node, payload.products);
      set((s) => ({
        currentNode: null,
        nodeStates: { ...s.nodeStates, [payload.node]: {
          status: 'completed', completedAt: payload.ts,
          durationMs: payload.duration_ms, products: payload.products
        }},
        productBlocks: [
          ...s.productBlocks.map((b, i) =>
            i === s.productBlocks.length - 1 ? { ...b, collapsed: true } : b
          ),
          { ...productBlock, collapsed: false },
        ],
      }));
      break;
    }
    case 'complaint.token':
      set((s) => ({
        complaintDraft: {
          ...s.complaintDraft,
          content: (s.complaintDraft?.content || '') + payload.delta,
        },
      }));
      break;
    case 'complaint.done':
      set((s) => ({
        complaintDraft: { title: payload.title, content: payload.final_content, tone: payload.tone },
      }));
      break;
    case 'review.interrupt':
      set({ reviewInterrupt: payload });
      break;
    case 'review.resumed':
      set({ reviewInterrupt: null });
      break;
    case 'workflow.complete':
      set({ isRunning: false, currentNode: null });
      break;
    case 'workflow.error':
      set((s) => ({
        isRunning: false,
        errors: [...s.errors, { message: payload.message, node: payload.node, recoverable: payload.recoverable }],
        connectionState: 'error',
      }));
      break;
  }
}
```

### 6.5 WorkflowStreamPanel 顶层组件

```tsx
// frontend/src/components/workflow/WorkflowStreamPanel.tsx
export function WorkflowStreamPanel({ caseId }: { caseId: number }) {
  const { isRunning, connectionState, startWorkflow } = useCaseStore();
  const [showPanel, setShowPanel] = useState(false);

  if (!showPanel && !isRunning) {
    return (
      <button
        onClick={() => { setShowPanel(true); startWorkflow(caseId, []); }}
        className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700"
      >
        开始工作流分析
      </button>
    );
  }

  return (
    <div className="flex gap-4 h-[calc(100vh-200px)] min-h-[600px]">
      <NodeTrack />
      <ProductStream />
    </div>
  );
}
```

### 6.6 NodeTrack 左侧步进轨道

```tsx
// frontend/src/components/workflow/NodeTrack.tsx
const NODE_ORDER = ['preclassify','ocr','classify','extract','review','evidence_chain','complaint'];
const NODE_LABELS = { preclassify:'预分类', ocr:'OCR', classify:'分类', extract:'抽取',
                      review:'审核', evidence_chain:'证据链', complaint:'投诉书' };

export function NodeTrack() {
  const { nodeStates, currentNode, connectionState } = useCaseStore();

  return (
    <aside className="w-28 flex-shrink-0 bg-slate-900 text-slate-100 p-3 rounded-lg">
      <div className="text-xs font-semibold mb-3 text-slate-400">
        节点轨道 · {connectionState === 'connected' ? '已连接' :
                   connectionState === 'reconnecting' ? '重连中' : '断开'}
      </div>
      <ol className="relative">
        <div className="absolute left-1.5 top-2 bottom-2 w-0.5 bg-slate-700" />
        {NODE_ORDER.map((node) => (
          <NodeTrackItem
            key={node}
            node={node}
            label={NODE_LABELS[node]}
            status={nodeStates[node]?.status || 'idle'}
            isCurrent={currentNode === node}
          />
        ))}
      </ol>
    </aside>
  );
}

function NodeTrackItem({ node, label, status, isCurrent }) {
  const dotClass = {
    completed: 'bg-green-500',
    running: 'bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.6)] animate-pulse',
    error: 'bg-red-500',
    idle: 'bg-slate-700 border border-slate-600',
    skipped: 'bg-slate-600',
  }[status];

  return (
    <li className="relative pl-5 pb-3">
      <span className={`absolute left-0 top-0.5 w-3 h-3 rounded-full ${dotClass}`} />
      <div className={`text-xs ${isCurrent ? 'font-semibold text-white' : 'text-slate-300'}`}>
        {label}
      </div>
    </li>
  );
}
```

### 6.7 ProductStream 主区产物流

```tsx
// frontend/src/components/workflow/ProductStream.tsx
export function ProductStream() {
  const { productBlocks, complaintDraft, reviewInterrupt, isRunning, currentNode } = useCaseStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [productBlocks.length, complaintDraft?.content.length]);

  return (
    <div className="flex-1 overflow-y-auto pr-2 space-y-2">
      {productBlocks.map((block) => (
        block.type === 'complaint'
          ? <ComplaintStreamBlock key={block.id} block={block} draft={complaintDraft} />
          : <ProductBlock key={block.id} block={block} />
      ))}

      {reviewInterrupt && <ReviewInterruptPanel data={reviewInterrupt} />}

      {isRunning && !reviewInterrupt && (
        <div className="text-center py-2 text-sm text-slate-400">
          <span className="inline-block animate-pulse">●</span> {currentNode} 运行中...
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
```

### 6.8 ProductBlock 通用产物区块（自动折叠）

```tsx
// frontend/src/components/workflow/ProductBlock.tsx
export function ProductBlock({ block }: { block: ProductBlock }) {
  const [collapsed, setCollapsed] = useState(block.collapsed);
  const { node, products, completedAt } = block;

  return (
    <div className={`border-l-4 rounded-r-md bg-white shadow-sm ${
      collapsed ? 'border-slate-300' : 'border-green-500'
    }`}>
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-3 py-2 text-left"
      >
        <span className="text-sm font-medium text-slate-700">
          {NODE_LABELS[node]}完成 · {summarizeProducts(node, products)}
        </span>
        <ChevronIcon collapsed={collapsed} />
      </button>

      {!collapsed && (
        <div className="px-3 pb-3 text-sm">
          <NodeProductsDetail node={node} products={products} completedAt={completedAt} />
        </div>
      )}
    </div>
  );
}
```

**NodeProductsDetail** 按节点类型渲染不同详情：
- `preclassify`：表格列出 evidence_code / category / confidence
- `ocr`：可折叠的 OCR 文本预览（截断 200 字，点击展开全文）
- `classify`：表格列出 evidence_code / category_label / confidence
- `extract`：按 `field_category` 分组的字段卡片
- `evidence_chain`：垂直时间线（datetime + event + evidence_codes）

### 6.9 ComplaintStreamBlock token 流式区块

```tsx
// frontend/src/components/workflow/ComplaintStreamBlock.tsx
export function ComplaintStreamBlock({ block, draft }) {
  const [collapsed, setCollapsed] = useState(false);
  const isStreaming = useCaseStore(s => s.isRunning && s.currentNode === 'complaint');
  const contentRef = useRef<HTMLDivElement>(null);
  const contentRefStr = useRef('');

  // 性能优化：增量追加 token，避免每 token re-render
  useEffect(() => {
    if (draft?.content && contentRef.current) {
      const newPart = draft.content.slice(contentRefStr.current.length);
      if (newPart) {
        contentRef.current.appendChild(document.createTextNode(newPart));
        contentRefStr.current = draft.content;
      }
    }
  }, [draft?.content]);

  return (
    <div className="border-l-4 border-blue-500 rounded-r-md bg-blue-50 shadow-sm">
      <div className="flex items-center justify-between px-3 py-2">
        <span className="text-sm font-medium text-blue-900">
          {isStreaming ? '投诉书生成中...' : '投诉书完成'}
        </span>
        {isStreaming && (
          <span className="text-xs text-blue-600">{draft?.content.length || 0} 字</span>
        )}
      </div>

      {!collapsed && (
        <div className="px-4 pb-4">
          <div className="bg-white border border-blue-200 rounded p-4 max-h-96 overflow-y-auto">
            <h4 className="text-center font-semibold mb-2 text-slate-900">
              {draft?.title || '投诉书'}
            </h4>
            <div ref={contentRef} className="whitespace-pre-wrap text-sm text-slate-700 leading-relaxed" />
            {isStreaming && (
              <span className="inline-block w-0.5 h-4 bg-blue-500 animate-pulse ml-0.5 align-middle" />
            )}
          </div>

          {!isStreaming && draft && (
            <div className="mt-3 flex gap-2">
              <Link to={`/cases/${caseId}/complaint`} className="text-xs text-blue-600 hover:underline">
                查看完整投诉书 →
              </Link>
              <span className="text-xs text-slate-400">语气：{TONE_LABELS[draft.tone]}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

### 6.10 ReviewInterruptPanel HITL 校正 UI

```tsx
// frontend/src/components/workflow/ReviewInterruptPanel.tsx
export function ReviewInterruptPanel({ data }: { data: ReviewInterruptData }) {
  const { submitReviewCorrections } = useCaseStore();
  const [corrections, setCorrections] = useState<Correction[]>(
    data.fields_to_review.map(f => ({
      evidence_id: f.evidence_id,
      field_name: f.field_name,
      corrected_value: f.current_value,
    }))
  );

  return (
    <div className="border-2 border-amber-400 bg-amber-50 rounded-md p-4">
      <div className="flex items-center gap-2 mb-3">
        <AlertIcon className="text-amber-600" />
        <h3 className="font-semibold text-amber-900">需要人工校正</h3>
      </div>
      <p className="text-sm text-amber-800 mb-3">{data.message}</p>

      <div className="space-y-2">
        {data.fields_to_review.map((field, i) => (
          <div key={i} className="flex items-center gap-2 bg-white px-2 py-1.5 rounded">
            <span className="text-xs text-slate-500 w-24">证据#{field.evidence_id}</span>
            <span className="text-xs text-slate-700 w-32">{field.field_name}</span>
            <span className="text-xs text-red-500">置信度 {field.confidence}</span>
            <input
              value={corrections[i].corrected_value}
              onChange={(e) => updateCorrection(i, e.target.value)}
              className="flex-1 text-sm border border-slate-300 rounded px-2 py-1"
            />
          </div>
        ))}
      </div>

      <button
        onClick={() => submitReviewCorrections(corrections)}
        className="mt-3 px-4 py-2 bg-amber-600 text-white rounded text-sm font-medium hover:bg-amber-700"
      >
        提交校正并继续
      </button>
    </div>
  );
}
```

### 6.11 EvidencePage 集成

```tsx
// frontend/src/pages/EvidencePage.tsx（修改）
export default function EvidencePage() {
  const { caseId } = useParams();
  // ... 现有证据列表逻辑

  return (
    <div className="space-y-4">
      <EvidenceGrid evidence={evidence} ... />
      <WorkflowStreamPanel caseId={caseId} />
    </div>
  );
}
```

### 6.12 api.ts 新增 workflowApi

```typescript
// frontend/src/lib/api.ts
export const workflowApi = {
  start: (caseId: number, evidenceIds: number[]) =>
    apiClient.post(`/cases/${caseId}/workflow/start/`, { evidence_ids: evidenceIds }),

  streamUrl: (caseId: number, threadId: string) =>
    `/api/cases/${caseId}/workflow/stream/?thread_id=${threadId}`,

  resume: (caseId: number, corrections: Correction[]) =>
    apiClient.post(`/cases/${caseId}/workflow/resume/`, { corrections }),

  history: (caseId: number) =>
    apiClient.get(`/cases/${caseId}/workflow/history/`),
};
```

### 6.13 断连重连用户体验

- **连接状态指示器**：NodeTrack 顶部显示 `已连接` / `重连中(2/5)` / `连接失败`
- **重连成功**：自动从 `last_event_id` 续传，前端无感知，产物区块按顺序补齐
- **重连失败（5 次后）**：显示"连接中断，[手动重试]"按钮，点击重新调用 `startWorkflow` 但复用 thread_id（从 checkpointer 恢复）
- **工作流完成后的连接关闭**：收到 `workflow.complete` 后主动 `close()`，避免无意义重连

---

## 7. 数据流完整链路

### 7.1 正常流程（无 HITL）

```
前端                    后端 SSE 端点         EventDepot/NotifyEmitter      WorkflowRunner         LangGraph
 │                          │                       │                         │                      │
 │── POST /workflow/start ──────────────────────────────────────────────────▶│                      │
 │◀── {thread_id} ─────────────────────────────────────────────────────────│                      │
 │                          │                       │                         │── astream_events ──▶│
 │                          │                       │◀── persist(node.start) │◀── on_chain_start ──│
 │                          │                       │◀── notify              │                      │
 │── GET /workflow/stream ─▶│                       │                         │                      │
 │   ?last_event_id=0       │── get_events_after ─▶│                         │                      │
 │                          │◀── [node.start,...] ─│                         │                      │
 │◀── event: node.start ────│                       │                         │                      │
 │                          │── subscribe(LISTEN) ─▶│                        │                      │
 │                          │                       │◀── persist(node.complete)│◀── on_chain_end ──│
 │                          │                       │◀── notify              │                      │
 │                          │◀── NOTIFY 唤醒        │                         │                      │
 │◀── event: node.complete ─│                       │                         │                      │
 │           ... 重复 7 个节点 ...                  │                         │                      │
 │                          │                       │◀── persist(complaint.token) ×N │◀── on_chat_model_stream│
 │◀── event: complaint.token ── (每次 token 立即推送)                        │                      │
 │                          │                       │◀── persist(workflow.complete)│                │
 │◀── event: workflow.complete ── (前端关闭连接,原地渲染完整状态)            │                      │
```

### 7.2 HITL 中断流程

```
前端                    后端                     EventDepot              WorkflowRunner
 │           ... extract_node 完成触发 needs_human_review=true ...         │
 │                      │                          │                         │
 │                      │                          │◀── persist(review.interrupt)
 │◀── event: review.interrupt ── (前端展示 ReviewInterruptPanel, SSE 保持连接)
 │      (用户填写校正,POST /workflow/resume)       │                         │
 │── POST /workflow/resume ──────────────────────────────────────────────▶│
 │   {corrections:[...]}│                          │                         │
 │                      │                          │                WorkflowRunner.run_and_persist(
 │                      │                          │                  resume={corrections})
 │                      │                          │◀── persist(review.resumed)
 │◀── event: review.resumed ── (前端关闭校正面板)  │                         │
 │                      │                          │◀── persist(evidence_chain.start)
 │◀── event: evidence_chain.start ── (后续节点继续推送)
```

### 7.3 断连重连流程

```
前端                    后端                     EventDepot              WorkflowRunner
 │   (SSE 连接因网络断开,前端检测到 onerror)       │                         │
 │  reconnectAttempts=1│                          │                         │
 │  last_event_id=15   │                          │                         │
 │── GET /workflow/stream?last_event_id=15 ─▶     │                         │
 │                      │── get_events_after(15) ─▶│                        │
 │                      │◀── [event16,event17] ───│ (期间工作流继续运行)   │
 │◀── event16,node.complete (ocr)                │                         │
 │◀── event17,node.start (classify)              │                         │
 │  (前端: 补齐漏掉的产物区块,NodeTrack 更新)      │                         │
 │                      │── subscribe(LISTEN) ───▶│                         │
 │   (恢复正常推送循环)                            │                         │
```

---

## 8. 错误处理

### 8.1 后端错误分级

| 错误类型 | 处理方式 | SSE 事件 | 工作流是否继续 |
|---|---|---|---|
| 节点级降级（LLM 超时/OCR 失败） | Saga 错误处理器已实现，节点返回 `errors` | `node.error` (recoverable=true) | 继续 |
| 工作流致命错误（checkpointer 不可用、state 损坏） | WorkflowRunner 捕获，写入 `workflow.error` | `workflow.error` (recoverable=false) + `workflow.complete` | 终止 |
| EventDepot 写入失败 | WorkflowRunner 重试 3 次，仍失败则推送 `workflow.error` | `workflow.error` | 终止（无法保证事件完整性） |
| SSE 端点异常 | 端点捕获，推送 `workflow.error` 后关闭连接 | `workflow.error` | 继续（后台任务独立运行） |
| HITL resume 失败（校正数据格式错误） | ResumeView 返回 400，前端展示错误提示 | 无（HTTP 错误） | 暂停（等待重新提交） |

### 8.2 前端错误处理

| 错误类型 | 处理方式 | 用户感知 |
|---|---|---|
| SSE 连接中断 | 自动重连 5 次，指数退避 | 顶部状态指示器显示"重连中(N/5)" |
| 重连失败 | 显示"连接中断"卡片 + [手动重试]按钮 | 用户点击重试，复用 thread_id |
| 节点错误事件 | ProductBlock 标红 + 错误消息展示 | 节点轨道对应节点标红，产物流插入错误卡片 |
| 工作流致命错误 | 全屏错误提示 + [重试]按钮 | 用户可重新启动工作流（新 thread_id） |
| HITL 提交失败 | 校正面板内联错误提示 | 用户修正后重新提交 |

### 8.3 资源清理

- **客户端断连**：SSE 端点检测到流关闭，取消 LISTEN 订阅，释放 Postgres 连接
- **工作流完成**：WorkflowRunner 写入 `workflow.complete` 后退出，任务从全局注册表移除
- **EventDepot 清理**：定时任务每小时清理 24h 前的事件
- **进程崩溃恢复**：启动时扫描 EventDepot 中未完成的 thread_id（有 `workflow.start` 无 `workflow.complete`），通过 checkpointer 恢复 state，标记为 `workflow.error`（recoverable=true），前端可手动重试

---

## 9. 性能考量

| 维度 | 目标 | 措施 |
|---|---|---|
| 首事件延迟 | < 500ms | 工作流启动后立即 persist `workflow.start` |
| token 流延迟 | < 100ms（token 到达前端） | token 事件立即 persist + notify，SSE 端点立即推送 |
| EventDepot 写入 | 不阻塞工作流 | persist 异步，WorkflowRunner 不等待 persist 完成即处理下一事件（fire-and-forget，但有重试） |
| Postgres 连接 | 不耗尽 | SSE 端点共享 checkpointer 连接池；LISTEN 连接单独管理，每个订阅一个连接 |
| 前端渲染 | 60fps（token 流期间） | complaint content 用 `useRef` 直接操作 DOM 追加，避免每 token 触发 React re-render |
| 产物区块数量 | < 20 个 DOM 节点 | 自动折叠历史区块（collapsed 状态仅渲染摘要行） |

---

## 10. 测试策略

### 10.1 后端测试

| 测试类型 | 测试内容 | 工具 |
|---|---|---|
| EventDepot 单元测试 | persist/get_events_after/is_workflow_completed/并发 event_id 分配 | pytest + pytest-asyncio + psycopg_pool |
| SSEEventMapper 单元测试 | 各类 astream_events 原始事件 → SSE 事件映射，过滤逻辑 | pytest（mock raw events） |
| WorkflowRunner 集成测试 | 完整工作流运行，验证 EventDepot 中事件序列正确 | pytest + 真实 LangGraph（mock LLM） |
| SSE 端点测试 | 正常流、断连重连、HITL 中断、heartbeat、多客户端订阅 | pytest + httpx.AsyncClient |
| 并发测试 | 同一 thread_id 多客户端订阅、不同 thread_id 并发运行 | pytest-asyncio + asyncio.gather |
| HITL 测试 | interrupt → resume → 后续节点推送链路 | pytest + 真实 review_node |

**关键测试用例**：

```python
# backend/api/tests/test_sse_workflow.py
@pytest.mark.asyncio
async def test_full_workflow_event_sequence(db, mock_llm):
    """验证完整工作流产生正确的事件序列"""
    runner = WorkflowRunner()
    await runner.run_and_persist(case_id=1, thread_id="test-1", initial_state={...})
    events = await EventDepot().get_all_events("test-1")
    event_types = [e.event_type for e in events]
    assert event_types[0] == "workflow.start"
    assert "node.start:preclassify" in event_types
    assert event_types[-1] == "workflow.complete"

@pytest.mark.asyncio
async def test_sse_reconnect_resumes_from_last_event_id(db, mock_llm):
    """验证断连重连从 last_event_id 续传"""
    ...

@pytest.mark.asyncio
async def test_hitl_interrupt_and_resume(db, mock_llm):
    """验证 HITL 中断 → resume → 后续节点推送"""
    ...

@pytest.mark.asyncio
async def test_complaint_token_streaming(db, mock_llm):
    """验证 complaint_node 产生 complaint.token 事件序列"""
    ...
```

### 10.2 前端测试

| 测试类型 | 测试内容 | 工具 |
|---|---|---|
| Zustand reducer 测试 | applySSEEvent 对各事件类型的 state 变更 | vitest + @testing-library/react |
| SSE 客户端测试 | 连接、断连重连、事件分发、关闭 | vitest + EventSource mock |
| 组件渲染测试 | NodeTrack/ProductBlock/ComplaintStreamBlock/ReviewInterruptPanel | @testing-library/react |
| 集成测试 | EvidencePage 完整工作流交互 | @testing-library/react + MSW（mock SSE） |

### 10.3 端到端测试

| 场景 | 验证点 |
|---|---|
| 完整工作流运行 | 7 节点全部完成，产物正确展示，投诉书 token 流式 |
| HITL 中断恢复 | 中断时 SSE 保持连接，resume 后后续节点继续推送 |
| 断连重连 | 手动断开网络，前端自动重连，产物补齐 |
| 多客户端订阅 | 两个浏览器标签同时订阅同一 thread_id，均能收到事件 |
| 节点降级 | OCR 节点失败，显示错误卡片，工作流继续 |

---

## 11. 向后兼容与迁移

- **原 `CaseWorkflowView`**：标记 `@deprecated`，保留 1 个版本。新前端默认走 SSE，旧调用方仍可走同步端点
- **数据库迁移**：新增 `sse_event_depot` 表，不影响现有表
- **配置迁移**：`.env.example` 新增 `SSE_EVENT_DEPOT_TTL_HOURS=24`、`SSE_HEARTBEAT_INTERVAL=15`
- **部署迁移**：`gunicorn` → `uvicorn`，Dockerfile 修改启动命令，docker-compose.yml 无需改动

---

## 12. 文件清单

### 后端新增（6 个文件）

- `backend/api/agents/sse_event_depot.py` - EventDepot 类
- `backend/api/agents/notify_emitter.py` - NotifyEmitter（LISTEN/NOTIFY 封装）
- `backend/api/agents/workflow_runner.py` - WorkflowRunner 后台任务
- `backend/api/agents/sse_event_mapper.py` - SSEEventMapper（事件过滤映射）
- `backend/api/migrations/00XX_sse_event_depot.py` - sse_event_depot 表迁移
- `backend/api/management/commands/cleanup_sse_events.py` - 事件清理命令

### 后端修改（4 个文件）

- `backend/api/views.py` - 新增 3 个 View，原 CaseWorkflowView 标记 deprecated
- `backend/api/urls.py` - 新增 3 条路由
- `backend/api/agents/__init__.py` - 导出 WorkflowRunner
- `requirements.txt` - 添加 `uvicorn[standard]`

### 前端新增（9 个文件）

- `frontend/src/lib/sse-client.ts` - EventSource 封装
- `frontend/src/lib/workflow-events.ts` - SSE 事件类型定义 + dispatch
- `frontend/src/components/workflow/WorkflowStreamPanel.tsx` - 顶层容器
- `frontend/src/components/workflow/NodeTrack.tsx` - 左侧步进轨道
- `frontend/src/components/workflow/ProductStream.tsx` - 主区产物流
- `frontend/src/components/workflow/ProductBlock.tsx` - 通用产物区块
- `frontend/src/components/workflow/ComplaintStreamBlock.tsx` - complaint token 流式区块
- `frontend/src/components/workflow/ReviewInterruptPanel.tsx` - HITL 校正 UI
- `frontend/src/components/workflow/NodeStatusIcon.tsx` - 节点状态图标

### 前端修改（3 个文件）

- `frontend/src/pages/EvidencePage.tsx` - 集成 WorkflowStreamPanel
- `frontend/src/stores/case-store.ts` - 新增 workflow slice
- `frontend/src/lib/api.ts` - 新增 workflowApi 模块

---

## 13. API 路由汇总

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/cases/<id>/workflow/start/` | 启动工作流，返回 thread_id + stream_url |
| GET | `/api/cases/<id>/workflow/stream/?thread_id=X&last_event_id=N` | SSE 流式端点 |
| POST | `/api/cases/<id>/workflow/resume/` | HITL 校正提交，恢复工作流 |
| GET | `/api/cases/<id>/workflow/history/` | （保留）工作流历史 |

---

## 14. 环境变量新增

```env
# SSE 工作流配置
SSE_EVENT_DEPOT_TTL_HOURS=24
SSE_HEARTBEAT_INTERVAL=15
SSE_MAX_RECONNECT_ATTEMPTS=5
SSE_RECONNECT_BASE_DELAY_MS=1000
```

---

## 15. 未决事项

- **多进程部署下的 LISTEN/NOTIFY**：当前方案在单进程 ASGI 下有效，多 worker 时 LISTEN 需要每个 worker 独立订阅。若升级到多进程部署，需评估是否引入 Redis Pub/Sub 替代 Postgres LISTEN/NOTIFY。
- **EventDepot 写入性能**：complaint_node token 流可能每秒产生数十个事件，需压测 Postgres 写入性能。若瓶颈明显，可引入批量写入（buffer 100ms 后批量 persist）。
- **HITL 长时间暂停的资源占用**：用户长时间不提交校正时，SSE 连接保持打开会占用 Postgres LISTEN 连接。可设置超时（如 30 分钟无 resume 自动关闭连接，工作流保持中断状态，用户重新访问时重新订阅）。
