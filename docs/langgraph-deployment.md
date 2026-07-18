# LangGraph 部署指南

> 本文档对应 Task 0.5（PostgresSaver 配置规范化），对齐 `langgraph-persistence` skill。
> 主图实现：`backend/api/agents/graph.py`

## 概述

ClaimCraft Creative 工作流基于 LangGraph 1.2+，使用 **PostgresSaver**（生产就绪）作为 checkpointer，
**PostgresStore** 作为跨运行长期记忆 store。本指南说明部署执行时机、连接池调优、thread_id 规范。

---

## 1. 首次部署

### 1.1 启动顺序

`docker-compose up` 启动以下服务：

1. **mysql**（业务数据库，存储 Case / Evidence / ComplaintTemplate 等业务表）
2. **postgres-checkpointer**（专用 PostgreSQL，存储 LangGraph checkpoints + Store + 法律向量库）
   - 镜像：`pgvector/pgvector:pg16`（含 pgvector 扩展，支持法律向量检索）
   - 数据库：`claimcraft_checkpoints`
3. **backend**（Django + DRF + LangGraph）
4. **frontend**（Nginx 静态资源 + 反向代理）

### 1.2 PostgresSaver schema 自动初始化

应用首次启动时，`_get_checkpointer()` 被首次调用（懒加载）：

```python
# backend/api/agents/graph.py
def _get_checkpointer() -> PostgresSaver:
    """获取线程安全、已完成 schema 初始化的 PostgresSaver 单例。"""
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer
    with _checkpointer_lock:                              # 线程级双重检查锁
        if _checkpointer is not None:
            return _checkpointer
        _setup_postgres_component(                        # 数据库级锁 + setup()
            PostgresSaver, "claimcraft_postgres_saver_setup"
        )
        sync_saver = PostgresSaver(conn=_get_connection_pool())
        _checkpointer = _AsyncCompatibleSyncCheckpointer(sync_saver)
        return _checkpointer
```

`_setup_postgres_component` 内部使用 `pg_advisory_lock` 防止多进程/多线程并发 setup：

```python
def _setup_postgres_component(component_cls, lock_name: str) -> None:
    """使用独立 autocommit 连接执行 LangGraph schema 迁移。"""
    with connect(_get_db_url(), autocommit=True, ...) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(hashtext(%s))", (lock_name,))
        try:
            component_cls(conn=conn).setup()               # 创建 schema（IF NOT EXISTS）
        finally:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(hashtext(%s))", (lock_name,))
```

**双重保护机制**：
- `_checkpointer_lock`（threading.Lock）：进程内线程级双重检查锁，避免同一进程内多线程并发 setup
- `pg_advisory_lock`（PostgreSQL advisory lock）：数据库级锁，避免多进程（gunicorn workers）并发 setup

### 1.3 PostgresStore schema 初始化

`_get_store()` 同样使用 `_store_lock` + `pg_advisory_lock("claimcraft_postgres_store_setup")`
保护 PostgresStore 的 schema 初始化。

---

## 2. 升级部署

### 2.1 setup() 是幂等的

LangGraph `PostgresSaver.setup()` 和 `PostgresStore.setup()` 内部使用 `CREATE TABLE IF NOT EXISTS`
等幂等 DDL，可重复执行而不报错。

### 2.2 升级流程

1. 拉取新镜像：`docker-compose pull`
2. 重启服务：`docker-compose up -d`
3. 应用启动时 `_get_checkpointer()` / `_get_store()` 会再次执行 `setup()`：
   - schema 已存在 → `IF NOT EXISTS` 跳过创建
   - 多进程并发 → `pg_advisory_lock` 串行化
4. **无需手动执行迁移 SQL**

### 2.3 LangGraph 版本升级注意事项

若 `langgraph` 主版本升级（如 1.x → 2.x），schema 可能不兼容。需：
1. 备份 `claimcraft_checkpoints` 数据库
2. 停止 backend 服务
3. 删除旧 schema（`DROP TABLE checkpoint_*`、`DROP TABLE store_*`）
4. 启动 backend，让新版本 `setup()` 重建 schema
5. 历史 checkpoints / store 数据将丢失（按设计接受）

---

## 3. 生产环境配置

### 3.1 CHECKPOINTER_DB_URL（必须）

生产环境必须通过环境变量 `CHECKPOINTER_DB_URL` 指向专用 PostgreSQL checkpoints 数据库：

```bash
# docker-compose.yml 已配置
CHECKPOINTER_DB_URL=postgresql://claimcraft:${CHECKPOINTER_PG_PASSWORD}@postgres-checkpointer:5432/claimcraft_checkpoints
```

**关键约束**：
- 与业务数据库（MySQL：`claimcraft`）**物理隔离**，避免 checkpoint 写入影响业务查询性能
- 使用 `pgvector/pgvector:pg16` 镜像（PostgreSQL 16 + pgvector 扩展），同时承载：
  - LangGraph checkpoints（`checkpoint_blobs` / `checkpoint_writes` / `checkpoints` 表）
  - LangGraph store（`store` 表，跨运行长期记忆）
  - 法律知识库向量表（`law_article_embedding`，pgvector 索引）

### 3.2 开发环境默认值

未设置环境变量时，graph.py 使用本地开发默认值：

```python
def _get_db_url() -> str:
    return os.environ.get(
        'CHECKPOINTER_DB_URL',
        'postgresql://claimcraft:claimcraft_dev_2025@127.0.0.1:5432/claimcraft_checkpoints',
    )
```

**生产部署必须显式设置 `CHECKPOINTER_DB_URL`**，不要依赖默认值。

---

## 4. 连接池配置

PostgresSaver 使用 `psycopg_pool.ConnectionPool`（同步连接池），通过以下环境变量调优：

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `CHECKPOINTER_POOL_SIZE` | `20` | 连接池最大连接数（max_size） |
| `CHECKPOINTER_POOL_MIN_SIZE` | `5` | 连接池最小空闲连接数（min_size） |
| `CHECKPOINTER_POOL_TIMEOUT` | `5` | 获取连接超时（秒） |
| `CHECKPOINTER_POOL_MAX_IDLE` | `300` | 连接最大空闲时长（秒），超时自动关闭 |

### 4.1 调优建议

- **gunicorn workers × threads** 与 `CHECKPOINTER_POOL_SIZE` 关系：
  - 每个 worker 进程有独立的连接池单例（`_pool` 模块级变量）
  - 总连接数 = workers × `CHECKPOINTER_POOL_SIZE`
  - 例如：4 workers × 20 pool_size = 80 连接，需检查 PostgreSQL `max_connections`
- **长空闲场景**：调低 `CHECKPOINTER_POOL_MAX_IDLE`（如 60s）减少空闲连接
- **高并发场景**：调高 `CHECKPOINTER_POOL_SIZE`（如 30）+ `CHECKPOINTER_POOL_MIN_SIZE`（如 10）
- **PostgreSQL `max_connections`**：默认 100，需预留连接给其他客户端（如 psql、监控）

### 4.2 连接池健康检查

`_check_pool_health()` 在 `_get_checkpointer()` 初始化时调用一次，记录 `psycopg_pool` 的
`get_stats()` 到日志（DEBUG 级别），便于运维定位连接池问题。

### 4.3 atexit 自动关闭

模块级 `atexit.register(_pool.close)` 在进程退出时自动关闭连接池，避免连接泄漏。

---

## 5. thread_id 规范

### 5.1 thread_id 传递

LangGraph 通过 `config = {"configurable": {"thread_id": thread_id}}` 识别独立的 checkpoint
序列（对话/运行隔离）。每次 `graph.ainvoke(state, config)` 会读写该 thread_id 对应的 checkpoint。

```python
# backend/api/agents/workflow_runner.py line 169
workflow = build_case_workflow()
config = {"configurable": {"thread_id": thread_id}}
# 首次启动
await workflow.ainvoke(initial_state, config)
# HITL 恢复（使用同一 thread_id，从 checkpoint 恢复中断前状态）
await workflow.ainvoke(Command(resume=resume_value), config)
```

### 5.2 thread_id 格式规范

- **目标格式**（Task 3.1 引入 `WorkflowRun` 模型后）：`case-{case_id}-run-{run_id}`
  - 每个 `WorkflowRun` 拥有独立 `thread_id`，支持同一案件的多次运行隔离
  - `run_id` 是 `WorkflowRun` 主键（自增或 UUID）
- **当前格式**（v11 之前）：`case-{case_id}-{timestamp_or_uuid}`
  - 由 `WorkflowRunner.start_in_background` 的调用方（views.py）生成
- **HITL 恢复**：复用同一 `thread_id`，LangGraph 从 checkpointer 恢复中断前状态
  （不会从头执行，对齐 `langgraph-human-in-the-loop` skill）

### 5.3 thread_id 隔离语义

- 不同 `thread_id` 的 state 完全隔离（不同案件 / 不同运行互不干扰）
- 同一 `thread_id` 的多次 invoke 会累积 state（HITL 恢复场景）
- 删除 `thread_id` 对应的 checkpoints 即可彻底清除运行历史（见
  `backend/api/management/commands/cleanup_checkpoints.py`）

---

## 6. _AsyncCompatibleSyncCheckpointer 包装说明

### 6.1 为什么需要包装

LangGraph 1.2+ 的 async 节点（`async def`）必须用 `ainvoke` 执行；但 sync `PostgresSaver`
不实现 `aget_tuple / aput / aput_writes`（基类抛 `NotImplementedError`）。

`AsyncPostgresSaver.__init__` 调用 `asyncio.get_running_loop()`，必须在 async 上下文构造，
无法在 sync Django（gunicorn WSGI / `manage.py shell`）中桥接；故回退到 sync 版本。

### 6.2 包装实现

`_AsyncCompatibleSyncCheckpointer` 继承 `BaseCheckpointSaver`，用 `sync_to_async` 桥接
sync 方法，使 `ainvoke` 可用；同时保留 sync 方法供 `invoke` 兼容路径使用。

```python
class _AsyncCompatibleSyncCheckpointer(BaseCheckpointSaver):
    def __init__(self, sync_saver):
        super().__init__()
        self._sync = sync_saver

    # async 接口（ainvoke 调用）
    async def aget_tuple(self, config):
        return await sync_to_async(self._sync.get_tuple)(config)
    # ... aput / aput_writes / asetup

    # sync 接口（invoke 调用）
    def get_tuple(self, config):
        return self._sync.get_tuple(config)
    # ... put / put_writes / setup
```

**部署约束**：不要移除 `_AsyncCompatibleSyncCheckpointer` 包装，否则 async 节点无法执行。

---

## 7. 部署检查清单

部署后执行以下检查：

- [ ] `postgres-checkpointer` 容器健康（`pg_isready -U claimcraft -d claimcraft_checkpoints`）
- [ ] `CHECKPOINTER_DB_URL` 环境变量已设置，指向 `postgres-checkpointer:5432/claimcraft_checkpoints`
- [ ] backend 启动日志含 `PostgresSaver 已初始化（autocommit setup + async 包装）`
- [ ] backend 启动日志含 `PostgresStore 已初始化（autocommit setup）`
- [ ] backend 启动日志含 `PostgreSQL 同步连接池已创建: .../claimcraft_checkpoints, min_size=5, max_size=20`
- [ ] 首次启动后，`claimcraft_checkpoints` 数据库含 `checkpoints / checkpoint_blobs / checkpoint_writes / store` 表
- [ ] 触发一次工作流运行，验证 `thread_id` 出现在 `checkpoints` 表的 `thread_id` 列
- [ ] HITL 中断 + 恢复后，验证 `thread_id` 对应的 checkpoint 数量增加（恢复写入新 checkpoint）
- [ ] PostgreSQL `max_connections` 足够（≥ workers × `CHECKPOINTER_POOL_SIZE` + 监控/运维连接）

---

## 8. 故障排查

### 8.1 setup() 失败

**症状**：backend 启动时报 `psycopg.OperationalError: connection refused` 或
`relation "checkpoints" does not exist`

**排查**：
1. 检查 `postgres-checkpointer` 容器是否健康
2. 检查 `CHECKPOINTER_DB_URL` 中的 host / port / user / password / dbname
3. 手动连接验证：`psql $CHECKPOINTER_DB_URL -c '\dt'`
4. 检查 `pg_advisory_lock` 是否被持有未释放（异常退出可能导致）：
   ```sql
   SELECT * FROM pg_locks WHERE locktype = 'advisory';
   ```
   若有残留 advisory lock，可重启 PostgreSQL 或手动 `SELECT pg_advisory_unlock(...)` 释放

### 8.2 连接池耗尽

**症状**：`psycopg_pool.PoolTimeout: connection pool timeout`

**排查**：
1. 调高 `CHECKPOINTER_POOL_TIMEOUT`（如 10s）
2. 调高 `CHECKPOINTER_POOL_SIZE`（如 30）
3. 检查是否有长事务未提交（`SELECT * FROM pg_stat_activity WHERE state = 'idle in transaction'`）
4. 检查 PostgreSQL `max_connections` 是否达到上限

### 8.3 thread_id 冲突

**症状**：HITL 恢复后 state 错乱（出现其他案件的数据）

**排查**：
1. 检查 `thread_id` 是否在多次运行间被复用（应为每次运行生成唯一 `thread_id`）
2. 检查 `WorkflowRunner.start_in_background` 调用方是否传入正确的 `thread_id`
3. 使用 `cleanup_checkpoints` 管理命令清理历史 checkpoints：
   ```bash
   python manage.py cleanup_checkpoints --before 2026-01-01
   ```

---

## 参考

- LangGraph Persistence 文档：https://langchain-ai.github.io/langgraph/concepts/persistence/
- `langgraph-persistence` skill：检查点、thread_id、Store、子图 checkpointer 作用域
- `langgraph-fundamentals` skill：StateGraph、节点、边、错误处理（RetryPolicy / error_handler / interrupt）
- 主图实现：`backend/api/agents/graph.py`
- 工作流运行器：`backend/api/agents/workflow_runner.py`
- 部署编排：`docker-compose.yml`
