-- Task 1.3.1: SSE 事件信封升级 - sse_event_depot 表新增 run_id / revision / occurred_at 列
--
-- 应用场景：
--   对已部署的旧 sse_event_depot 表手工补列。EventDepot.setup() 内部已包含
--   幂等的 ADD COLUMN IF NOT EXISTS 语句，启动时会自动执行；本文件供 DBA
--   在维护窗口手工执行或纳入 CI/CD 迁移流程，避免首次启动时执行 DDL。
--
-- 兼容性：
--   - 三个新列均允许 NULL，旧数据保持 NULL，读取路径兼容（前端/SSE 端点回退到 created_at）
--   - 不删除/修改任何现有列，可安全回滚（DROP COLUMN 不必要，留空即可）
--   - PostgreSQL 9.6+ 支持 ADD COLUMN IF NOT EXISTS
--
-- 相关文件：
--   backend/api/agents/sse_event_depot.py  (EventDepot.persist / setup)
--   .trae/specs/workflow-fullstack-upgrade/spec.md  (5.1 SSE 事件保留站)
--   .trae/specs/workflow-fullstack-upgrade/tasks.md (Task 1.3 SubTask 1.3.1)

BEGIN;

ALTER TABLE sse_event_depot
    ADD COLUMN IF NOT EXISTS run_id BIGINT NULL;

ALTER TABLE sse_event_depot
    ADD COLUMN IF NOT EXISTS revision INT NULL;

ALTER TABLE sse_event_depot
    ADD COLUMN IF NOT EXISTS occurred_at TIMESTAMPTZ NULL;

-- 按 run_id 检索事件索引（部分索引，跳过 NULL 行）
CREATE INDEX IF NOT EXISTS idx_depot_run_id
    ON sse_event_depot(run_id)
    WHERE run_id IS NOT NULL;

COMMIT;

-- 验证（可选）
-- \d sse_event_depot
-- SELECT column_name, data_type, is_nullable
--   FROM information_schema.columns
--   WHERE table_name = 'sse_event_depot'
--   ORDER BY ordinal_position;
