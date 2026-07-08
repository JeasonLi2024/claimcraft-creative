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
- PostgresSaver（ConnectionPool 模式）编译时启用 checkpointer
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

工程化要点（v7 修正）：
- sync PostgresSaver + ConnectionPool（与 Django WSGI sync 部署一致）
- 注：AsyncPostgresSaver.__init__ 调用 asyncio.get_running_loop()，必须在 async 上下文构造，
  无法在 sync Django（gunicorn WSGI / manage.py shell）中桥接；故回退到 sync 版本。
- 节点本身仍为 async def，invoke 时用 async_to_sync(workflow.ainvoke) 桥接（asgiref 兼容）
- PostgresStore 跨案件长期记忆（namespace=(user_id, "preferences")）
- atexit 注册关闭连接池（sync ConnectionPool.close 直接调用）
- 单例化编译后的图，避免每次请求重新编译
"""
import atexit
import logging
import os
from typing import Literal

from asgiref.sync import async_to_sync, sync_to_async
from psycopg_pool import ConnectionPool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.errors import NodeError, NodeTimeoutError
from langgraph.graph import StateGraph, START, END
from langgraph.store.postgres import PostgresStore

from api.agents.state import CaseWorkflowState
from api.agents.nodes.preclassify_node import preclassify_node
from api.agents.nodes.ocr_node import ocr_node
from api.agents.nodes.classify_node import classify_node
from api.agents.nodes.extract_node import extract_node
from api.agents.nodes.review_node import review_node
from api.agents.nodes.evidence_chain_node import evidence_chain_node
from api.agents.nodes.complaint_node import complaint_node
from api.agents.nodes.respond_complaint_node import respond_complaint_node

logger = logging.getLogger(__name__)


# Saga 降级模式说明：
# - error_handler 返回 {"errors": [...]}，依赖 state.errors 的 Annotated[list, add] reducer
# - reducer 会自动累积，不会覆盖之前节点的 errors
# - 下游节点应检查 state["errors"] 决定降级路径（如 evidence_chain 发现 OCR 全失败则跳过）
# - 若需中断整图，error_handler 可返回 Command(goto=END) 或 raise error
# - timeout 仅 async 节点生效（v4 Phase E1 已将 6 节点改为 async def）
def _make_error_handler(node_name: str):
    """节点错误处理器工厂：返回错误到 state.errors 累积列表（Saga 降级）。

    LangGraph 1.2+ error_handler 签名要求：
    - 第一个位置参数是 input（节点失败时的 state）
    - error: NodeError 必须是 kwarg（类型注解 NodeError），LangGraph 从
      config[CONFIG_KEY_NODE_ERROR] 注入

    Args:
        node_name: 节点中文名（用于错误消息，如 "OCR" / "字段抽取"）

    Returns:
        error_handler 函数，接收 (input, *, error: NodeError)，返回 {"errors": [msg]}
    """
    def handler(input: dict, *, error: NodeError) -> dict:
        if isinstance(error, NodeTimeoutError):
            msg = f"[{node_name}] 节点超时（>{getattr(error, 'timeout', '?')}s），已降级"
        else:
            # NodeError 包含原始异常（error.error 是 BaseException）
            inner = getattr(error, 'error', error)
            msg = f"[{node_name}] 节点异常: {type(inner).__name__}: {str(inner)[:200]}"
        logger.error(msg, exc_info=False)
        return {"errors": [msg]}  # 利用 state.errors 的 Annotated[list, add] 累积
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


def _get_connection_pool() -> ConnectionPool:
    """获取 PostgreSQL 同步连接池单例（懒加载，生产级调优）。

    环境变量：
    - CHECKPOINTER_DB_URL：PostgreSQL 连接串
      格式：postgresql://user:password@host:5432/dbname
      默认：postgresql://claimcraft:claimcraft_dev_2025@127.0.0.1:5432/claimcraft_checkpoints
    - CHECKPOINTER_POOL_SIZE：连接池最大连接数（默认 20）
    - CHECKPOINTER_POOL_MIN_SIZE：预热连接数（默认 5，避免冷启动延迟）
    - CHECKPOINTER_POOL_TIMEOUT：获取连接等待超时秒（默认 5）
    - CHECKPOINTER_POOL_MAX_IDLE：空闲连接最大保留秒数（默认 300）

    连接池在进程退出时通过 atexit 自动关闭。
    """
    global _pool
    if _pool is None:
        db_url = os.environ.get(
            'CHECKPOINTER_DB_URL',
            'postgresql://claimcraft:claimcraft_dev_2025@127.0.0.1:5432/claimcraft_checkpoints'
        )
        pool_size = int(os.environ.get('CHECKPOINTER_POOL_SIZE', '20'))
        min_size = int(os.environ.get('CHECKPOINTER_POOL_MIN_SIZE', '5'))
        timeout = float(os.environ.get('CHECKPOINTER_POOL_TIMEOUT', '5'))
        max_idle = float(os.environ.get('CHECKPOINTER_POOL_MAX_IDLE', '300'))

        _pool = ConnectionPool(
            conninfo=db_url,
            min_size=min_size,    # 预热连接数（避免冷启动延迟）
            max_size=pool_size,   # 最大连接数
            timeout=timeout,      # 获取连接超时（秒）
            max_idle=max_idle,    # 空闲连接最大保留秒数
            open=True,  # 立即打开连接（sync 版本无 event loop 要求）
        )
        # 注册进程退出时关闭连接池（sync 版本直接 close）
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


def _get_checkpointer() -> PostgresSaver:
    """获取 PostgresSaver 单例（懒加载）。

    首次调用时执行 setup() 建表（idempotent，已存在则跳过）。
    sync 版本，与 Django WSGI 部署一致。
    """
    global _checkpointer
    if _checkpointer is None:
        pool = _get_connection_pool()
        # PostgresSaver 的 conn 参数同时接受 Connection 或 ConnectionPool
        # 传入 ConnectionPool 时，内部自动借还连接
        sync_saver = PostgresSaver(conn=pool)
        # 首次使用时建表（idempotent，已存在则跳过）
        sync_saver.setup()
        # 包装成支持 async 接口的 checkpointer
        # sync PostgresSaver 不实现 aget_tuple/aput（基类抛 NotImplementedError），
        # 本 wrapper 用 sync_to_async 桥接 sync 方法，使 ainvoke 可用（async 节点必须用 ainvoke）
        _checkpointer = _AsyncCompatibleSyncCheckpointer(sync_saver)
        # 初始化时打印一次连接池状态，便于运维定位
        _check_pool_health()
        logger.info("PostgresSaver 已初始化（含 async 包装）并完成 setup()")
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
    """获取 PostgresStore 单例（跨案件长期记忆）。

    与 checkpointer 共用 CHECKPOINTER_DB_URL + ConnectionPool（表名不冲突，可共用）。
    namespace 设计：(user_id, "preferences") / (user_id, "case_templates")

    本期范围：仅 complaint_node 读取 complaint_style 偏好；
    写入端点（前端设置偏好）本期不实现。
    """
    global _store
    if _store is None:
        # 复用 checkpointer 的 ConnectionPool（sync 版本，与 Django WSGI 一致）
        pool = _get_connection_pool()
        _store = PostgresStore(conn=pool)
        try:
            _store.setup()  # idempotent，建 store 表
        except Exception as e:
            # CREATE INDEX CONCURRENTLY 在事务中失败时，用 psql 手动执行 setup
            # 表可能已存在（idempotent），仅记录警告
            logger.warning(f"PostgresStore.setup() 失败（可能表已存在或 CONCURRENTLY 限制）: {e}")
        logger.info("PostgresStore 已初始化（复用 checkpointer 连接池）")
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

    # 添加节点（节点级 timeout + error_handler，Saga 降级）
    # timeout 仅 async invoke（ainvoke）模式下对 async 节点生效；
    # checkpointer 已用 _AsyncCompatibleSyncCheckpointer 包装支持 async 接口
    g.add_node("preclassify", preclassify_node, timeout=60, error_handler=_make_error_handler("视觉预分类"))
    g.add_node("ocr", ocr_node, timeout=180, error_handler=_make_error_handler("OCR"))
    g.add_node("classify", classify_node, timeout=60, error_handler=_make_error_handler("分类"))
    g.add_node("extract", extract_node, timeout=300, error_handler=_make_error_handler("字段抽取"))
    g.add_node("review", review_node, timeout=30, error_handler=_make_error_handler("人工校正"))
    g.add_node("evidence_chain", evidence_chain_node, timeout=120, error_handler=_make_error_handler("证据链"))
    g.add_node("complaint", complaint_node, timeout=120, error_handler=_make_error_handler("投诉生成"))
    g.add_node("respond_complaint", respond_complaint_node, timeout=120, error_handler=_make_error_handler("反证答辩生成"))

    # 添加边
    g.add_edge(START, "preclassify")
    g.add_edge("preclassify", "ocr")
    g.add_edge("ocr", "classify")
    g.add_edge("classify", "extract")
    g.add_conditional_edges(
        "extract",
        _route_after_extract,
        {"review": "review", "evidence_chain": "evidence_chain"},
    )
    g.add_edge("review", "evidence_chain")
    # v10 反向维权分支：根据 case_mode 路由到 complaint 或 respond_complaint
    g.add_conditional_edges(
        "evidence_chain",
        _route_by_case_mode,
        {"complaint": "complaint", "respond_complaint": "respond_complaint"},
    )
    g.add_edge("complaint", END)
    g.add_edge("respond_complaint", END)

    # 编译（启用 PostgresSaver checkpointer + PostgresStore 长期记忆，HITL 必须）
    compiled = g.compile(checkpointer=_get_checkpointer(), store=_get_store())
    logger.info("案件工作流 StateGraph 构建完成（PostgresSaver + PostgresStore 已启用）")
    _workflow = compiled
    return _workflow
