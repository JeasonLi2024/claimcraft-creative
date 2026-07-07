# Linux 服务器知识库构建指南

> 本文档描述将 ClaimCraft 维权材料工坊项目迁移到 Linux 服务器后，构建法律知识库（LawArticle + PlatformRule + pgvector 向量索引）的完整流程。
>
> 确保使用与 Windows 开发环境完全相同的法律材料（17 部法律 + 3 个平台规则，共 1646 条法条 + 182 条平台规则条文）。

---

## 一、前置条件

### 1.1 服务依赖

| 服务 | 版本要求 | 用途 |
|------|---------|------|
| MySQL | 8.0+ | 业务数据库（LawArticle、PlatformRule 表） |
| PostgreSQL | 14+ | 向量库（pgvector 扩展，law_article_vectors 表） |
| Python | 3.10+ | Django 后端运行环境 |

### 1.2 PostgreSQL pgvector 扩展安装

```bash
# Debian/Ubuntu
apt install postgresql-16-pgvector

# CentOS/RHEL (需 EPEL)
yum install pgvector_16

# 或从源码编译
cd /tmp
git clone https://github.com/pgvector/pgvector.git
cd pgvector
make && make install
```

### 1.3 Python 依赖

```bash
cd /opt/claimcraft/backend
pip install -r requirements.txt
# 关键依赖：psycopg[binary]、langchain-openai、django、pymysql、python-dotenv
```

---

## 二、数据库初始化

### 2.1 MySQL 业务库

```sql
CREATE DATABASE claimcraft CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'claimcraft'@'%' IDENTIFIED BY '<your_password>';
GRANT ALL PRIVILEGES ON claimcraft.* TO 'claimcraft'@'%';
FLUSH PRIVILEGES;
```

### 2.2 PostgreSQL 向量库

```bash
# 创建专用数据库（与 checkpointer 复用同一 PG 实例，不同库）
sudo -u postgres psql -c "CREATE DATABASE claimcraft_checkpoints;"
sudo -u postgres psql -c "CREATE USER claimcraft WITH PASSWORD 'claimcraft_dev_2025';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE claimcraft_checkpoints TO claimcraft;"
sudo -u postgres psql -d claimcraft_checkpoints -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 2.3 Django Migrations

```bash
cd /opt/claimcraft/backend
python manage.py migrate
```

---

## 三、.env 配置（Linux 环境）

修改项目根目录 `.env` 文件，关键配置项如下：

```ini
# ===== MySQL 业务库 =====
DB_ENGINE=django.db.backends.mysql
DB_NAME=claimcraft
DB_USER=claimcraft
DB_PASSWORD=<your_password>
DB_HOST=127.0.0.1
DB_PORT=3306

# ===== PostgreSQL 向量库（Linux 使用专用用户）=====
CHECKPOINTER_DB_URL=postgresql://claimcraft:claimcraft_dev_2025@127.0.0.1:5432/claimcraft_checkpoints
LAW_VECTOR_DB_URL=postgresql://claimcraft:claimcraft_dev_2025@127.0.0.1:5432/claimcraft_checkpoints

# Docker 部署时使用容器名：
# CHECKPOINTER_DB_URL=postgresql://claimcraft:claimcraft_dev_2025@postgres-checkpointer:5432/claimcraft_checkpoints
# LAW_VECTOR_DB_URL=postgresql://claimcraft:claimcraft_dev_2025@postgres-checkpointer:5432/claimcraft_checkpoints

# ===== Embedding 服务 =====
# SiliconFlow API Key（https://cloud.siliconflow.cn 申请）
EMBEDDING_API_KEY=sk-<your_siliconflow_api_key>
EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING_MODEL=BAAI/bge-m3
# 0=不传 dimensions 参数（bge-m3 原生 1024 维，无需降维）
EMBEDDING_DIMENSIONS=0
# 向量库表维度（必须与模型实际返回维度一致，bge-m3=1024）
EMBEDDING_VECTOR_DIM=1024
```

---

## 四、知识库数据导入

### 4.1 法律材料文件结构

法律原文文件位于 `backend/api/services/law_data_raw/`：

```
law_data_raw/
├── cat0_消费者权益保护法.txt          # 消费者权益保护法（63条）
├── cat0_电子商务法.txt               # 电子商务法（89条）
├── cat0_民法典合同编.txt              # 民法典合同编（526条）
├── cat0_食品安全法.txt               # 食品安全法（154条）
├── cat0_产品质量法.txt               # 产品质量法（74条）
├── cat1_反不正当竞争法.txt            # 反不正当竞争法（41条，2025修订版）
├── cat1_价格法.txt                   # 价格法（48条）
├── cat1_广告法.txt                   # 广告法（74条）
├── cat2_民法典侵权责任编.txt           # 民法典侵权责任编（95条）
├── cat2_合同行政监督管理办法.txt       # 合同行政监督管理办法（23条）
├── cat3_个人信息保护法.txt            # 个人信息保护法（74条）
├── cat3_药品管理法.txt               # 药品管理法（155条）
├── cat3_农产品质量安全法.txt          # 农产品质量安全法（81条）
├── cat3_反食品浪费法.txt              # 反食品浪费法（32条）
├── cat4_网络交易监督管理办法.txt       # 网络交易监督管理办法（56条）
├── cat4_网络购买商品七日无理由退货暂行办法.txt  # 七日无理由退货暂行办法（38条）
├── cat4_网络零售第三方平台交易规则制定程序规定.txt  # 平台交易规则规定（23条）
├── cat4_京东规则1.txt                # 京东开放平台交易纠纷处理总则（57条）
├── cat4_京东规则2.txt                # 京东开放平台商品类问题纠纷处理标准（31条）
├── cat4_淘宝规则.txt                 # 淘宝平台争议处理规则（94条）
├── parse_law_data.py                # 结构化解析脚本
└── output/                          # 解析后的 JSON 输出
    ├── law_articles_parsed.json     # 1646条法律条文（结构化）
    ├── platform_rules_parsed.json   # 182条平台规则条文（结构化）
    └── parse_stats.json             # 解析统计信息
```

### 4.2 方式一：直接导入预解析 JSON（推荐）

如果 `output/*.json` 文件已随项目一起迁移，可直接导入：

```bash
cd /opt/claimcraft/backend

# 步骤1：导入法律条文到 MySQL LawArticle 表（1646条）
python manage.py import_law_articles \
    --file=api/services/law_data_raw/output/law_articles_parsed.json \
    --no-embed

# 步骤2：导入平台规则到 MySQL PlatformRule 表（3条，含182条条文合并）
python manage.py import_law_articles \
    --platform-file=api/services/law_data_raw/output/platform_rules_parsed.json

# 步骤3：生成 embedding 向量索引到 PostgreSQL（需 SiliconFlow API Key）
python manage.py import_law_articles \
    --file=api/services/law_data_raw/output/law_articles_parsed.json \
    --force-embed
```

### 4.3 方式二：从源文件重新解析（如 JSON 丢失）

如果 `output/*.json` 文件不存在，可从 `.txt` 源文件重新解析：

```bash
cd /opt/claimcraft/backend

# 运行解析脚本，重新生成 output/*.json
python api/services/law_data_raw/parse_law_data.py

# 然后按方式一导入
python manage.py import_law_articles \
    --file=api/services/law_data_raw/output/law_articles_parsed.json \
    --force-embed
python manage.py import_law_articles \
    --platform-file=api/services/law_data_raw/output/platform_rules_parsed.json
```

---

## 五、验证知识库

### 5.1 验证 MySQL 数据

```bash
cd /opt/claimcraft/backend
python manage.py shell -c "
from api.models import LawArticle, PlatformRule
from collections import Counter
print(f'LawArticle 总数: {LawArticle.objects.count()}')
print(f'PlatformRule 总数: {PlatformRule.objects.count()}')
print('按法律名称统计:')
c = Counter(a.law_name for a in LawArticle.objects.all())
for name, cnt in sorted(c.items(), key=lambda x: -x[1]):
    print(f'  {name}: {cnt}条')
"
```

**预期输出：**
```
LawArticle 总数: 1646
PlatformRule 总数: 3
按法律名称统计:
  中华人民共和国民法典（合同编）: 526条
  中华人民共和国食品安全法: 154条
  ...
```

### 5.2 验证 PostgreSQL 向量索引

```bash
psql -U claimcraft -d claimcraft_checkpoints -c "
SELECT COUNT(*) AS total,
       COUNT(DISTINCT law_name) AS laws
FROM law_article_vectors;
"
```

**预期输出：**
```
 total | laws
-------+------
  1646 |   17
```

### 5.3 验证 RAG 检索功能

```bash
python manage.py shell -c "
import asyncio, sys
if sys.platform == 'linux':
    loop = asyncio.new_event_loop()
else:
    import selectors
    loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
asyncio.set_event_loop(loop)

from api.services.rag_service import LawRetriever
async def test():
    r = LawRetriever()
    results = await r.search('消费者退货退款', top_k=3)
    for hit in results:
        print(f'[{hit[\"law_name\"]}] {hit[\"article_number\"]} (score={hit[\"score\"]:.4f})')
        print(f'  {hit[\"content\"][:80]}...')
loop.run_until_complete(test())
"
```

---

## 六、常见问题

### 6.1 pgvector 扩展不可用

```sql
-- 检查扩展是否可用
SELECT name, default_version FROM pg_available_extensions WHERE name = 'vector';

-- 如果返回空，需安装 pgvector（见 1.2 节）
-- 安装后在目标数据库中启用
CREATE EXTENSION IF NOT EXISTS vector;
```

### 6.2 HNSW 索引创建失败（维度 > 2000）

如果切换为维度 > 2000 的模型（如 Qwen3-VL-Embedding-8B 的 4096 维），pgvector HNSW 索引会创建失败。
代码已自动处理：维度 > 2000 时跳过 HNSW 索引，改用顺序扫描。
当前默认使用 BAAI/bge-m3（1024 维），不会触发此问题，HNSW 索引正常创建。

### 6.3 SiliconFlow API 报 403 余额不足

```bash
# 错误信息：Error code: 403 - {'code': 30001, 'message': 'Sorry, your account balance is insufficient'}
# 解决方案：
# 1. 登录 https://cloud.siliconflow.cn 充值
# 2. 或更换为其他免费 embedding 模型（需同步修改 .env 中 EMBEDDING_MODEL）
# 3. 充值后重新运行：
python manage.py import_law_articles \
    --file=api/services/law_data_raw/output/law_articles_parsed.json \
    --force-embed
```

### 6.4 Windows 开发环境事件循环兼容

Windows 下 psycopg async 需要 SelectorEventLoop（非默认的 ProactorEventLoop）。
`import_law_articles.py` 已自动处理此兼容性，Linux 下无需关注。

---

## 七、知识库数据概览

| 数据表 | 存储位置 | 记录数 | 说明 |
|--------|---------|-------|------|
| LawArticle | MySQL | 1646 | 17 部法律的结构化条文 |
| PlatformRule | MySQL | 3 | 京东(2) + 淘宝(1)，含 182 条条文合并 |
| law_article_vectors | PostgreSQL (pgvector) | 1646 | 1024 维向量索引（BAAI/bge-m3，HNSW 索引） |

### 按分类统计（LawArticle）

| 分类 | 条款数 |
|------|-------|
| contract（合同） | 644 |
| safety（食品安全） | 422 |
| other（其他） | 163 |
| platform_rule（平台规则） | 117 |
| e-commerce（电商） | 89 |
| privacy（个人信息） | 74 |
| quality（产品质量） | 74 |
| consumer_protection（消费者保护） | 63 |
