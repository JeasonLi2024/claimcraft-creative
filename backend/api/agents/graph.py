# -*- coding: utf-8 -*-
"""案件工作流主图（多证据聚合版）：StateGraph + PostgresSaver checkpointer + PostgresStore。

重构说明（多证据工作流）：
- 新增 classify 节点（证据分类）和 evidence_chain 节点（证据链构造）
- timeline 节点被 evidence_chain 替代
- 条件边路由目标从 timeline 改为 evidence_chain

新工作流：
    START → ocr → classify → extract → [review?] → evidence_chain → complaint → END

基于 langgraph-fundamentals + langgraph-persistence + langgraph-human-in-the-loop skills：
- StateGraph 定义节点和边
- PostgresSaver（ConnectionPool 模式）编译时启用 checkpointer（生产就绪，非 InMemorySaver）
- PostgresStore 跨 thread 长期记忆（用户偏好/模板风格）
- thread_id 在 invoke 时通过 config 传入（案件级状态隔离）
- 条件边：extract → review（needs_human_review=True）或 extract → evidence_chain（默认）
- review_node 使用 interrupt() 暂停，Command(resume=...) 恢复

调用方式：
    workflow = build_case_workflow()
    config = {"configurable": {"thread_id": case.thread_id}}
    result = async_to_sync(workflow.ainvoke)(initial_state, config)
    # HITL 恢复：
    result = async_to_sync(workflow.ainvoke)(Command(resume=value), config)

PostgresSaver 部署规范（对齐 langgraph-persistence skill，Task 0.5）：
- 使用 PostgresSaver（非 InMemorySaver），生产就绪
- `setup()` 通过 `_checkpointer_lock`（线程级双重检查锁）+ `pg_advisory_lock`（数据库级锁）
  双重保护，每个进程仅执行一次；新部署时数据库已包含 schema，无需重复 setup
- `setup()` 内部使用 `IF NOT EXISTS` 语义，幂等可重复执行
- `CHECKPOINTER_DB_URL` 必须指向专用 checkpoints 数据库（与业务 MySQL 分离）
- 连接池调优环境变量：`CHECKPOINTER_POOL_SIZE / CHECKPOINTER_POOL_MIN_SIZE /
  CHECKPOINTER_POOL_TIMEOUT / CHECKPOINTER_POOL_MAX_IDLE`
- thread_id 规范：每个 `WorkflowRun` 使用独立 `thread_id`，格式 `case-{case_id}-run-{run_id}`
  （由 WorkflowRunner.start_in_background 在 `config = {"configurable": {"thread_id": thread_id}}`
  中传入，详见 workflow_runner.py）

错误处理 4 层策略（对齐 langgraph-fundamentals skill）：
1. RetryPolicy（瞬时错误：网络、限流 429、超时）— 在 add_node 配置，自动重试 3 次
2. error_handler（节点级 Saga 降级）— 返回 {"errors": [...]} 不中断图
3. interrupt()（用户可修复错误）— 在 review_node / stage_gate_node 中调用
4. raise（未预期错误）— 向上抛出，由 WorkflowRunner 捕获并 fail_processing

工程化要点（v7 修正）：
- sync PostgresSaver + ConnectionPool（与 Django WSGI sync 部署一致）
- 注：AsyncPostgresSaver.__init__ 调用 asyncio.get_running_loop()，必须在 async 上下文构造，
  无法在 sync Django（gunicorn WSGI / manage.py shell）中桥接；故回退到 sync 版本。
- 节点本身仍为 async def，invoke 时用 async_to_sync(workflow.ainvoke) 桥接（asgiref 兼容）
- PostgresStore 跨案件长期记忆（namespace=(user_id, "preferences")）
- atexit 注册关闭连接池（sync ConnectionPool.close 直接调用）
- 单例化编译后的图，避免每次请求重新编译

子图 checkpointer 作用域策略（Task 3.4.3，对齐 spec.md Requirement:
LangGraph Subgraph Checkpointer Scoping + langgraph-persistence skill）：
========================

当前 `build_case_workflow` 构建的是**扁平 StateGraph**，未使用
`StateGraph.add_node(subgraph_instance)` 子图模式；所有 8 个业务节点 +
stage_gate 节点直接添加到主图。故本文件**不引入子图编译代码**，
仅文档化未来添加子图时必须遵循的 checkpointer 作用域规则：

| 子图类型            | checkpointer 作用域 | 理由                                              |
|---------------------|---------------------|---------------------------------------------------|
| 文书生成子图        | `None`（默认）      | 需 `interrupt()` 但无跨调用记忆；resume 时父子重执行，副作用须幂等 |
| RAG 检索子图        | `False`             | 无 `interrupt`、无记忆需求，最简                  |
| 其它（任何场景）    | 禁止 `True`         | 避免与父图 thread_id namespace 冲突、避免并行调用状态污染 |

强制约束（新增子图时必须遵守）：
1. 子图编译时显式传 `checkpointer=` 参数，禁止省略（默认 `None` 也应显式标注）。
2. 子图通过 `StateGraph.add_node(subgraph.compile(checkpointer=...))` 注册为节点。
3. 文书生成子图若含 `interrupt()`，节点内副作用必须幂等（`update_or_create`），
   因 resume 时父节点与子图节点都会从头重新执行。
4. RAG 检索子图编译为 `subgraph.compile(checkpointer=False)`，确保无 checkpoint 写入。
5. 不使用 `checkpointer=True`（继承父图 checkpointer），避免并行多证据处理时
   namespace 冲突与状态污染。

示例（未来引入子图时参考，当前未使用）：
    # 文书生成子图（需 interrupt，无跨调用记忆）
    doc_subgraph = doc_builder.compile(checkpointer=None)
    g.add_node("complaint", doc_subgraph, ...)

    # RAG 检索子图（无 interrupt，无记忆）
    rag_subgraph = rag_builder.compile(checkpointer=False)
    g.add_node("rag_retrieve", rag_subgraph, ...)
"""
import atexit
import logging
import os
import threading
from typing import Literal

from asgiref.sync import async_to_sync, sync_to_async
from psycopg import connect
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.errors import NodeError, NodeTimeoutError
from langgraph.graph import StateGraph, START, END
from langgraph.runtime import Runtime
from langgraph.store.postgres import PostgresStore
# RetryPolicy：LangGraph 1.2+ 在 langgraph.types 模块（NamedTuple）
# 任务约束：先尝试 langgraph.errors → langgraph.pregel → fallback；
# 实际 1.2.2 安装版本中 langgraph.types.RetryPolicy 是官方入口（对齐 langgraph-fundamentals skill）
from langgraph.types import RetryPolicy

from api.agents.state import CaseWorkflowState
from api.agents.nodes.preclassify_node import preclassify_node
from api.agents.nodes.ocr_node import ocr_node
from api.agents.nodes.classify_node import classify_node
from api.agents.nodes.extract_node import extract_node
from api.agents.nodes.review_node import review_node
from api.agents.nodes.evidence_chain_node import evidence_chain_node
from api.agents.nodes.complaint_node import complaint_node
from api.agents.nodes.respond_complaint_node import respond_complaint_node
from api.agents.nodes.stage_gate_node import make_stage_gate

logger = logging.getLogger(__name__)


# ============================================================================
# 错误处理 4 层策略（对齐 langgraph-fundamentals skill，Task 0.4.4）
# ============================================================================
# 1. RetryPolicy（瞬时错误：网络、限流 429、超时）— 在 add_node 配置，自动重试 3 次
# 2. error_handler（节点级 Saga 降级）— 返回 {"errors": [...]} 不中断图
# 3. interrupt()（用户可修复错误）— 在 review_node / stage_gate_node 中调用
# 4. raise（未预期错误）— 向上抛出，由 WorkflowRunner 捕获并 fail_processing
#
# 节点分类（Task 0.4.1 审计结果）：
# - LLM 调用节点：preclassify / classify / extract / evidence_chain / complaint /
#   respond_complaint（调用 captioner / text LLM / langextract / chat_with_retry）
# - OCR 调用节点：ocr（调用 ocr_image_with_strategy 多策略 OCR pipeline）
# - 无外部 API 调用节点：review（仅 interrupt + DB）/ stage_gate（仅 interrupt + DB）
#
# RetryPolicy 仅配置给调用外部 API 的节点（LLM / OCR）。
# review / stage_gate 是 HITL 节点，不应自动重试 — 应让用户介入（对齐 Task 0.4.2 约束）。
# RetryPolicy 默认 retry_on=default_retry_on：对 ConnectionError / httpx 5xx / requests 5xx
# 自动重试；对 ValueError / TypeError / RuntimeError / OSError 等不重试。
# ============================================================================
# 节点 API 调用重试策略（对齐 langgraph-fundamentals skill）：
# - max_attempts=3：最多重试 3 次（含首次）
# - initial_interval=1.0：首次重试等待 1 秒
# - backoff_factor=2.0：指数退避（1s → 2s → 4s）
# - max_interval=10.0：单次等待上限 10 秒
# ============================================================================
_API_NODE_RETRY_POLICY = RetryPolicy(
    max_attempts=3,
    initial_interval=1.0,
    backoff_factor=2.0,
    max_interval=10.0,
)


# Saga 降级模式说明：
# - error_handler 返回 {"errors": [...]}，依赖 state.errors 的 Annotated[list, add] reducer
# - reducer 会自动累积，不会覆盖之前节点的 errors
# - 下游节点应检查 state["errors"] 决定降级路径（如 evidence_chain 发现 OCR 全失败则跳过）
# - 若需中断整图，error_handler 可返回 Command(goto=END) 或 raise error
# - timeout 仅 async 节点生效（v4 Phase E1 已将 6 节点改为 async def）
# - v11 BREAKING：errors 元素从 str 升级为 dict（{code, message, severity, recoverable}），
#   对齐 CaseWorkflowState.errors 的 list[dict] 类型与统一 Issue 结构
def _make_error_handler(node_name: str):
    """节点错误处理器工厂：返回错误到 state.errors 累积列表（Saga 降级）。

    LangGraph 1.2+ error_handler 签名要求：
    - 第一个位置参数是 input（节点失败时的 state）
    - error: NodeError 必须是 kwarg（类型注解 NodeError），LangGraph 从
      config[CONFIG_KEY_NODE_ERROR] 注入

    v11 BREAKING：返回的 errors 元素为 dict（非 str），结构：
        {"code": "node.error", "message": msg, "severity": "warning",
         "stage": node_name, "recoverable": True}

    Args:
        node_name: 节点中文名（用于错误消息，如 "OCR" / "字段抽取"）

    Returns:
        error_handler 函数，接收 (input, *, error: NodeError)，返回
        {"errors": [{"code", "message", "severity", "stage", "recoverable"}]}
    """
    def handler(input: dict, *, error: NodeError) -> dict:
        if isinstance(error, NodeTimeoutError):
            msg = f"[{node_name}] 节点超时（>{getattr(error, 'timeout', '?')}s），已降级"
        else:
            # NodeError 包含原始异常（error.error 是 BaseException）
            inner = getattr(error, 'error', error)
            msg = f"[{node_name}] 节点异常: {type(inner).__name__}: {str(inner)[:200]}"
        logger.error(msg, exc_info=False)
        return {
            "errors": [
                {
                    "code": "node.error",
                    "message": msg,
                    "severity": "warning",
                    "stage": node_name,
                    "recoverable": True,
                }
            ]
        }  # 利用 state.errors 的 Annotated[list, add] 累积
    return handler

# 模块级单例（懒加载，避免 import 时连接 DB）
# 使用 sync PostgresSaver + ConnectionPool（与 Django WSGI sync 部署一致）
# 注：AsyncPostgresSaver.__init__ 调用 asyncio.get_running_loop()，必须在 async 上下文构造，
# 无法在 sync Django（gunicorn WSGI / manage.py shell）中桥接；故回退到 sync 版本。
# 节点本身仍为 async def，invoke 时用 async_to_sync(workflow.ainvoke) 桥接。
_pool: ConnectionPool | None = None
_checkpointer: PostgresSaver | None = None
_store: PostgresStore | None = None
_workflow = None
_pool_lock = threading.Lock()
_checkpointer_lock = threading.Lock()
_store_lock = threading.Lock()


def _get_db_url() -> str:
    return os.environ.get(
        'CHECKPOINTER_DB_URL',
        'postgresql://claimcraft:claimcraft_dev_2025@127.0.0.1:5432/claimcraft_checkpoints',
    )


def _get_connection_pool() -> ConnectionPool:
    """获取符合 LangGraph 契约的 PostgreSQL 运行时连接池。"""
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is not None:
            return _pool
        db_url = _get_db_url()
        pool_size = int(os.environ.get('CHECKPOINTER_POOL_SIZE', '20'))
        min_size = int(os.environ.get('CHECKPOINTER_POOL_MIN_SIZE', '5'))
        timeout = float(os.environ.get('CHECKPOINTER_POOL_TIMEOUT', '5'))
        max_idle = float(os.environ.get('CHECKPOINTER_POOL_MAX_IDLE', '300'))
        _pool = ConnectionPool(
            conninfo=db_url, min_size=min_size, max_size=pool_size,
            timeout=timeout, max_idle=max_idle,
            kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
            open=True,
        )
        atexit.register(_pool.close)
        logger.info(
            f"PostgreSQL 同步连接池已创建: {db_url.split('@')[-1]}, "
            f"min_size={min_size}, max_size={pool_size}, timeout={timeout}s"
        )
        return _pool


def _check_pool_health() -> bool:
    """检查连接池健康状态（仅用于日志/调试）。

    Returns:
        True if pool is open and has available connections

    Note:
        长时间空闲后，PG 端可能已关闭连接（max_connections 限制 / 重启）。
        本函数在 _get_checkpointer() 初始化时调用一次，便于运维定位。
    """
    if _pool is None:
        return False
    try:
        # psycopg_pool 3.1+ 提供 get_stats() 方法
        stats = _pool.get_stats()
        logger.debug(f"ConnectionPool stats: {stats}")
        return stats.get('pool_size', 0) > 0
    except Exception as e:
        logger.warning(f"连接池健康检查失败: {e}")
        return False


def _setup_postgres_component(component_cls, lock_name: str) -> None:
    """使用独立 autocommit 连接执行 LangGraph schema 迁移。"""
    with connect(
        _get_db_url(), autocommit=True, row_factory=dict_row, prepare_threshold=0
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(hashtext(%s))", (lock_name,))
        try:
            component_cls(conn=conn).setup()
        finally:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(hashtext(%s))", (lock_name,))


def _get_checkpointer() -> PostgresSaver:
    """获取线程安全、已完成 schema 初始化的 PostgresSaver 单例。"""
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer
    with _checkpointer_lock:
        if _checkpointer is not None:
            return _checkpointer
        _setup_postgres_component(
            PostgresSaver, "claimcraft_postgres_saver_setup"
        )
        sync_saver = PostgresSaver(conn=_get_connection_pool())
        _checkpointer = _AsyncCompatibleSyncCheckpointer(sync_saver)
        _check_pool_health()
        logger.info("PostgresSaver 已初始化（autocommit setup + async 包装）")
        return _checkpointer


class _AsyncCompatibleSyncCheckpointer(BaseCheckpointSaver):
    """把 sync PostgresSaver 包装成支持 async 接口的 checkpointer。

    LangGraph 1.2+ 的 async 节点（async def）必须用 ainvoke 执行；
    但 sync PostgresSaver 不实现 aget_tuple/aput（基类抛 NotImplementedError）。
    本 wrapper 继承 BaseCheckpointSaver，用 sync_to_async 桥接 sync 方法，使 ainvoke 可用。

    保留 sync 方法（get_tuple/put/put_writes）供 sync invoke 兼容路径使用。
    """

    def __init__(self, sync_saver):
        super().__init__()
        self._sync = sync_saver

    # === async 接口（ainvoke 调用） ===
    async def aget_tuple(self, config):
        return await sync_to_async(self._sync.get_tuple)(config)

    async def aput(self, config, checkpoint, metadata, new_versions):
        return await sync_to_async(self._sync.put)(
            config, checkpoint, metadata, new_versions
        )

    async def aput_writes(self, config, writes, task_id):
        return await sync_to_async(self._sync.put_writes)(config, writes, task_id)

    async def asetup(self):
        return await sync_to_async(self._sync.setup)()

    # === sync 接口（invoke 调用） ===
    def get_tuple(self, config):
        return self._sync.get_tuple(config)

    def put(self, config, checkpoint, metadata, new_versions):
        return self._sync.put(config, checkpoint, metadata, new_versions)

    def put_writes(self, config, writes, task_id):
        return self._sync.put_writes(config, writes, task_id)

    def setup(self):
        return self._sync.setup()

    # === 通用属性透传 ===
    @property
    def config_specs(self):
        return self._sync.config_specs

    def get_next_version(self, current, channel):
        return self._sync.get_next_version(current, channel)


def _get_store() -> PostgresStore:
    """获取线程安全、已完成 schema 初始化的 PostgresStore 单例。"""
    global _store
    if _store is not None:
        return _store
    with _store_lock:
        if _store is not None:
            return _store
        _setup_postgres_component(
            PostgresStore, "claimcraft_postgres_store_setup"
        )
        _store = PostgresStore(conn=_get_connection_pool())
        logger.info("PostgresStore 已初始化（autocommit setup）")
        return _store


def _route_after_extract(state: CaseWorkflowState) -> Literal["review", "evidence_chain"]:
    """条件边路由：抽取后判断是否需要人工校正。"""
    if state.get("needs_human_review"):
        return "review"
    return "evidence_chain"


def _route_by_case_mode(state: CaseWorkflowState) -> Literal["complaint", "respond_complaint"]:
    """条件边路由：根据案件模式（case_mode）路由到投诉生成或反证答辩生成。

    - case_mode=complain（默认）→ complaint 节点（消费者投诉书）
    - case_mode=respond         → respond_complaint 节点（商家反证答辩书）
    """
    if state.get("case_mode") == "respond":
        return "respond_complaint"
    return "complaint"


def build_case_workflow():
    """构建案件工作流 StateGraph（单例化）。

    节点顺序（v9 新增 preclassify 节点；v10 新增 respond_complaint 反向维权分支）：
        START → preclassify → ocr → classify → extract → [review?] → evidence_chain
              → [case_mode?] → complaint | respond_complaint → END

    条件边：
        extract → review（needs_human_review=True）
        extract → evidence_chain（默认）
        review → evidence_chain
        evidence_chain → complaint（case_mode=complain，默认）
        evidence_chain → respond_complaint（case_mode=respond，反向维权）

    Returns:
        编译后的 StateGraph，已启用 PostgresSaver checkpointer + PostgresStore
    """
    global _workflow
    if _workflow is not None:
        return _workflow

    g = StateGraph(CaseWorkflowState)

    # 添加节点（节点级 timeout + error_handler + retry_policy，三者协同）：
    # - retry_policy 处理瞬时错误（网络、限流 429、超时）自动重试 3 次（仅 LLM/OCR 节点）
    # - timeout 处理节点超时（仅 async invoke 模式下对 async 节点生效）
    # - error_handler 处理 Saga 降级（返回 {"errors": [...]} 不中断图）
    # checkpointer 已用 _AsyncCompatibleSyncCheckpointer 包装支持 async 接口
    #
    # 节点 retry_policy 配置（Task 0.4.2）：
    # - LLM 节点（preclassify/classify/extract/evidence_chain/complaint/respond_complaint）
    #   + OCR 节点（ocr）：配置 _API_NODE_RETRY_POLICY（瞬时错误自动重试 3 次）
    # - HITL 节点（review / stage_gate_after_*）：不配置 retry_policy
    #   （用户介入节点不应自动重试，应让用户决定下一步）
    g.add_node(
        "preclassify",
        preclassify_node,
        timeout=60,
        retry_policy=_API_NODE_RETRY_POLICY,
        error_handler=_make_error_handler("视觉预分类"),
    )
    g.add_node(
        "ocr",
        ocr_node,
        timeout=180,
        retry_policy=_API_NODE_RETRY_POLICY,
        error_handler=_make_error_handler("OCR"),
    )
    g.add_node(
        "classify",
        classify_node,
        timeout=60,
        retry_policy=_API_NODE_RETRY_POLICY,
        error_handler=_make_error_handler("分类"),
    )
    g.add_node(
        "extract",
        extract_node,
        timeout=300,
        retry_policy=_API_NODE_RETRY_POLICY,
        error_handler=_make_error_handler("字段抽取"),
    )
    # review 是 HITL 节点（interrupt + DB），不配置 retry_policy（对齐 Task 0.4.2 约束）
    g.add_node(
        "review",
        review_node,
        timeout=30,
        error_handler=_make_error_handler("人工校正"),
    )
    g.add_node(
        "evidence_chain",
        evidence_chain_node,
        timeout=120,
        retry_policy=_API_NODE_RETRY_POLICY,
        error_handler=_make_error_handler("证据链"),
    )
    g.add_node(
        "complaint",
        complaint_node,
        timeout=120,
        retry_policy=_API_NODE_RETRY_POLICY,
        error_handler=_make_error_handler("投诉生成"),
    )
    g.add_node(
        "respond_complaint",
        respond_complaint_node,
        timeout=120,
        retry_policy=_API_NODE_RETRY_POLICY,
        error_handler=_make_error_handler("反证答辩生成"),
    )

    business_nodes = (
        "preclassify", "ocr", "classify", "extract", "review",
        "evidence_chain", "complaint", "respond_complaint",
    )
    # stage_gate 节点是 HITL 暂停门（仅 interrupt + DB），不配置 retry_policy
    # （用户介入节点不应自动重试，应让用户决定下一步，对齐 Task 0.4.2 约束）
    for node_name in business_nodes:
        g.add_node(f"stage_gate_after_{node_name}", make_stage_gate(node_name))

    # 每个业务节点完成后先经过阶段门，再路由到下一业务节点。
    g.add_edge(START, "preclassify")
    g.add_edge("preclassify", "stage_gate_after_preclassify")
    g.add_edge("stage_gate_after_preclassify", "ocr")
    g.add_edge("ocr", "stage_gate_after_ocr")
    g.add_edge("stage_gate_after_ocr", "classify")
    g.add_edge("classify", "stage_gate_after_classify")
    g.add_edge("stage_gate_after_classify", "extract")
    g.add_edge("extract", "stage_gate_after_extract")
    g.add_conditional_edges(
        "stage_gate_after_extract",
        _route_after_extract,
        {"review": "review", "evidence_chain": "evidence_chain"},
    )
    g.add_edge("review", "stage_gate_after_review")
    g.add_edge("stage_gate_after_review", "evidence_chain")
    g.add_edge("evidence_chain", "stage_gate_after_evidence_chain")
    g.add_conditional_edges(
        "stage_gate_after_evidence_chain",
        _route_by_case_mode,
        {"complaint": "complaint", "respond_complaint": "respond_complaint"},
    )
    g.add_edge("complaint", "stage_gate_after_complaint")
    g.add_edge("stage_gate_after_complaint", END)
    g.add_edge("respond_complaint", "stage_gate_after_respond_complaint")
    g.add_edge("stage_gate_after_respond_complaint", END)

    # 编译（启用 PostgresSaver checkpointer + PostgresStore 长期记忆，HITL 必须）
    compiled = g.compile(checkpointer=_get_checkpointer(), store=_get_store())
    logger.info("案件工作流 StateGraph 构建完成（PostgresSaver + PostgresStore 已启用）")
    _workflow = compiled
    # 注：initial state 中的版本常量（workflow_version / state_schema_version /
    # policy_version / prompt_bundle_version）由 WorkflowRunner.run_and_persist 在
    # 首次启动（非 resume）时合并到 initial_state dict，使用
    # WorkflowVersion.to_initial_state()（见 api/agents/version.py + workflow_runner.py）。
    # 此处不在 build_case_workflow 编译时注入版本：版本注入发生在 invoke 时的
    # initial_state dict 中，使每个 WorkflowRun 都能记录其启动时的版本快照。
    return _workflow
