#!/bin/bash
# ============================================================
# 共享数据库一次性初始化脚本
# ------------------------------------------------------------
# 功能：
#   1. MySQL：创建 claimcraft 用户 + 创建 claimcraft_test 库与用户 +
#      从 claimcraft 克隆全部数据（含法条库 api_lawarticle 2260 条）
#   2. PostgreSQL：创建 claimcraft_test 用户 + 创建 claimcraft_test_checkpoints 库 +
#      从 claimcraft_checkpoints 克隆全部数据（含 law_article_vectors 2260 条向量）
#
# 前置条件：
#   - docker-compose.db.yml 已启动且 mysql/postgres 容器 healthy
#   - .env 中 DB_PASSWORD 与 CHECKPOINTER_PG_PASSWORD 可用
#
# 用法：
#   bash scripts/init-shared-db.sh
#
# 幂等性：脚本可重复执行，已存在的用户/库会被跳过，数据会重新覆盖。
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/.."

# 加载 .env 中的密码
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

MYSQL_ROOT_PASSWORD="${DB_PASSWORD:-claimcraft_dev_2025}"
PG_PROD_PASSWORD="${CHECKPOINTER_PG_PASSWORD:-claimcraft_dev_2025}"

# 测试侧密码（可由 .env 覆盖，默认值与首次初始化脚本一致）
MYSQL_TEST_PASSWORD="${DB_PASSWORD_TEST:-claimcraft_test_2025}"
PG_TEST_PASSWORD="${CHECKPOINTER_PG_PASSWORD_TEST:-claimcraft_test_2025}"

MYSQL_CONTAINER="claimcraft-db-mysql"
PG_CONTAINER="claimcraft-db-postgres"

echo "============================================================"
echo "[1/4] MySQL：创建正式侧 claimcraft 用户"
echo "============================================================"
sudo docker exec -i "$MYSQL_CONTAINER" mysql -uroot -p"$MYSQL_ROOT_PASSWORD" <<SQL
CREATE USER IF NOT EXISTS 'claimcraft'@'%' IDENTIFIED BY '$MYSQL_ROOT_PASSWORD';
GRANT ALL PRIVILEGES ON claimcraft.* TO 'claimcraft'@'%';
FLUSH PRIVILEGES;
SQL
echo "[1/4] 完成：claimcraft 用户已就绪"

echo ""
echo "============================================================"
echo "[2/4] MySQL：创建测试侧 claimcraft_test 库与用户并克隆数据"
echo "============================================================"
# 创建测试库与用户
sudo docker exec -i "$MYSQL_CONTAINER" mysql -uroot -p"$MYSQL_ROOT_PASSWORD" <<SQL
CREATE DATABASE IF NOT EXISTS claimcraft_test
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'claimcraft_test'@'%' IDENTIFIED BY '$MYSQL_TEST_PASSWORD';
GRANT ALL PRIVILEGES ON claimcraft_test.* TO 'claimcraft_test'@'%';
FLUSH PRIVILEGES;
SQL

# 清空测试库旧表（幂等重置）
sudo docker exec "$MYSQL_CONTAINER" mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e \
  "DROP DATABASE IF EXISTS claimcraft_test; CREATE DATABASE claimcraft_test DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 从生产库克隆全部表结构与数据
echo "[2/4] 正在从 claimcraft 克隆到 claimcraft_test..."
sudo docker exec "$MYSQL_CONTAINER" sh -c \
  "exec mysqldump -uroot -p\"$MYSQL_ROOT_PASSWORD\" --single-transaction --routines --triggers --no-tablespaces claimcraft" \
  | sudo docker exec -i "$MYSQL_CONTAINER" sh -c \
    "exec mysql -uroot -p\"$MYSQL_ROOT_PASSWORD\" claimcraft_test"

# 重新授权（DROP DATABASE 会顺带清掉 db-level 权限）
sudo docker exec -i "$MYSQL_CONTAINER" mysql -uroot -p"$MYSQL_ROOT_PASSWORD" <<SQL
GRANT ALL PRIVILEGES ON claimcraft_test.* TO 'claimcraft_test'@'%';
FLUSH PRIVILEGES;
SQL

LAW_COUNT=$(sudo docker exec "$MYSQL_CONTAINER" mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -e \
  "SELECT COUNT(*) FROM claimcraft_test.api_lawarticle;" 2>/dev/null)
echo "[2/4] 完成：claimcraft_test 库已就绪，法条数=$LAW_COUNT"

echo ""
echo "============================================================"
echo "[3/4] PostgreSQL：创建测试侧 claimcraft_test 用户与库"
echo "============================================================"
sudo docker exec -i "$PG_CONTAINER" psql -U claimcraft -d claimcraft_checkpoints -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'claimcraft_test') THEN
        CREATE ROLE claimcraft_test LOGIN PASSWORD '$PG_TEST_PASSWORD';
    ELSE
        ALTER ROLE claimcraft_test WITH PASSWORD '$PG_TEST_PASSWORD';
    END IF;
END
\$\$;
SQL

# 删除并重建测试库（幂等重置）
sudo docker exec -i "$PG_CONTAINER" psql -U claimcraft -d postgres -v ON_ERROR_STOP=1 <<SQL
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'claimcraft_test_checkpoints';
DROP DATABASE IF EXISTS claimcraft_test_checkpoints;
CREATE DATABASE claimcraft_test_checkpoints OWNER claimcraft_test;
SQL

# 在测试库中启用 pgvector 扩展
sudo docker exec -i "$PG_CONTAINER" psql -U claimcraft -d claimcraft_test_checkpoints -v ON_ERROR_STOP=1 <<SQL
CREATE EXTENSION IF NOT EXISTS vector;
GRANT ALL ON SCHEMA public TO claimcraft_test;
SQL
echo "[3/4] 完成：claimcraft_test_checkpoints 库已就绪"

echo ""
echo "============================================================"
echo "[4/4] PostgreSQL：从生产库克隆全部数据"
echo "============================================================"
echo "[4/4] 正在从 claimcraft_checkpoints 克隆..."
# 使用 pg_dump | psql 克隆全部表（含 law_article_vectors 2260 条向量）
sudo docker exec "$PG_CONTAINER" \
  sh -c "exec pg_dump -U claimcraft -d claimcraft_checkpoints --no-owner --no-privileges" \
  | sudo docker exec -i "$PG_CONTAINER" \
    sh -c "exec psql -U claimcraft_test -d claimcraft_test_checkpoints" \
  > /tmp/pg_clone.log 2>&1 || { cat /tmp/pg_clone.log; exit 1; }

# 表已通过 pg_dump --no-owner + psql as claimcraft_test 自动归 claimcraft_test 所有
# 仅补充权限授予（默认权限用于未来新增表）
sudo docker exec -i "$PG_CONTAINER" psql -U claimcraft -d claimcraft_test_checkpoints -v ON_ERROR_STOP=1 <<SQL
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO claimcraft_test;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO claimcraft_test;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO claimcraft_test;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO claimcraft_test;
SQL

PG_LAW_COUNT=$(sudo docker exec "$PG_CONTAINER" psql -U claimcraft_test -d claimcraft_test_checkpoints -t -A -c \
  "SELECT COUNT(*) FROM law_article_vectors;" 2>/dev/null || echo "0")
PG_CKPT_COUNT=$(sudo docker exec "$PG_CONTAINER" psql -U claimcraft_test -d claimcraft_test_checkpoints -t -A -c \
  "SELECT COUNT(*) FROM checkpoints;" 2>/dev/null || echo "0")
echo "[4/4] 完成：claimcraft_test_checkpoints 库已就绪，法条向量=$PG_LAW_COUNT，checkpoint=$PG_CKPT_COUNT"

echo ""
echo "============================================================"
echo "共享数据库初始化完成"
echo "============================================================"
echo "MySQL:"
echo "  生产: claimcraft        / claimcraft    / $MYSQL_ROOT_PASSWORD"
echo "  测试: claimcraft_test   / claimcraft_test / $MYSQL_TEST_PASSWORD"
echo "PostgreSQL:"
echo "  生产: claimcraft_checkpoints        / claimcraft        / $PG_PROD_PASSWORD"
echo "  测试: claimcraft_test_checkpoints   / claimcraft_test   / $PG_TEST_PASSWORD"
