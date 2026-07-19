#!/bin/bash
# ============================================================
# PostgreSQL 初始化脚本（仅在空卷首次启动时执行）
# ------------------------------------------------------------
# 创建测试侧用户 claimcraft_test 与测试库 claimcraft_test_checkpoints。
# 法条向量等数据由 init-shared-db.sh 通过 pg_dump | psql 克隆。
#
# 注意：复用已有生产卷时此脚本不会执行，需手动运行 scripts/init-shared-db.sh。
# 脚本设计为幂等：可重复执行而不报错。
# ============================================================
set -e

# 创建测试侧用户（如果不存在）
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'claimcraft_test') THEN
            CREATE ROLE claimcraft_test LOGIN PASSWORD 'claimcraft_test_2025';
        END IF;
    END
    \$\$;

    -- 创建测试库（如果不存在），owner 设为 claimcraft_test
    SELECT 'CREATE DATABASE claimcraft_test_checkpoints OWNER claimcraft_test'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'claimcraft_test_checkpoints')\gexec

    -- 在测试库中启用 pgvector 扩展（需 superuser 权限，由 claimcraft 拥有者执行）
    \c claimcraft_test_checkpoints
    CREATE EXTENSION IF NOT EXISTS vector;
EOSQL
