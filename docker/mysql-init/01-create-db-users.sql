-- ============================================================
-- MySQL 初始化脚本（仅在空卷首次启动时执行）
-- ------------------------------------------------------------
-- 创建正式侧专用用户 claimcraft 与测试侧专用用户 claimcraft_test，
-- 并创建测试库 claimcraft_test（结构与数据由 init-shared-db.sh 克隆）。
--
-- 注意：复用已有生产卷时此脚本不会执行，需手动运行 scripts/init-shared-db.sh。
-- 脚本设计为幂等：可重复执行而不报错。
-- ============================================================

-- ---------- 正式侧用户 ----------
-- 创建 claimcraft 用户（仅授权 claimcraft 库）
CREATE USER IF NOT EXISTS 'claimcraft'@'%' IDENTIFIED BY 'claimcraft_dev_2025';
GRANT ALL PRIVILEGES ON claimcraft.* TO 'claimcraft'@'%';

-- ---------- 测试侧用户与库 ----------
-- 创建测试库（如果不存在）
CREATE DATABASE IF NOT EXISTS claimcraft_test
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- 创建测试侧用户
CREATE USER IF NOT EXISTS 'claimcraft_test'@'%' IDENTIFIED BY 'claimcraft_test_2025';
GRANT ALL PRIVILEGES ON claimcraft_test.* TO 'claimcraft_test'@'%';

FLUSH PRIVILEGES;
