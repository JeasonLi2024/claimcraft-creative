# -*- coding: utf-8 -*-
"""法条原文结构化解析脚本。

将 law_data_raw/ 目录下的所有 .txt 法律原文文件解析为结构化 JSON 数据，
供 import_law_articles 命令批量导入使用。

解析逻辑：
1. 读取文件头部元信息（法律名称/数据源URL/施行日期/条款数）
2. 提取正文部分（==== 正文开始 ==== 与 ==== 正文结束 ==== 之间）
3. 跳过目录部分
4. 逐行解析章节标题、节标题、条文
5. 合并多行条文（一条法条可能跨多行，含括号项）
6. 为每条法条生成结构化数据（law_name/article_number/chapter/content/category 等）

输出：
- law_articles_parsed.json：法律条文结构化数据
- platform_rules_parsed.json：平台规则结构化数据
- 控制台输出统计信息
"""
import json
import re
from pathlib import Path

# ============================================================
# 文件 → 法律分类 映射
# ============================================================
FILE_CATEGORY_MAP = {
    # 已收录5部法律（扩展核心章节）
    'cat0_消费者权益保护法.txt': ('consumer_protection', '中华人民共和国消费者权益保护法'),
    'cat0_电子商务法.txt': ('e-commerce', '中华人民共和国电子商务法'),
    'cat0_民法典合同编.txt': ('contract', '中华人民共和国民法典（合同编）'),
    'cat0_食品安全法.txt': ('safety', '中华人民共和国食品安全法'),
    'cat0_产品质量法.txt': ('quality', '中华人民共和国产品质量法'),
    # 类别一：消费者维权核心法
    'cat1_反不正当竞争法.txt': ('other', '中华人民共和国反不正当竞争法'),
    'cat1_价格法.txt': ('other', '中华人民共和国价格法'),
    'cat1_广告法.txt': ('other', '中华人民共和国广告法'),
    # 类别二：合同与质量法
    'cat2_民法典侵权责任编.txt': ('contract', '中华人民共和国民法典（侵权责任编）'),
    'cat2_合同行政监督管理办法.txt': ('contract', '合同行政监督管理办法'),
    # 类别三：专项维权法
    'cat3_个人信息保护法.txt': ('privacy', '中华人民共和国个人信息保护法'),
    'cat3_药品管理法.txt': ('safety', '中华人民共和国药品管理法'),
    'cat3_农产品质量安全法.txt': ('safety', '中华人民共和国农产品质量安全法'),
    'cat3_反食品浪费法.txt': ('safety', '中华人民共和国反食品浪费法'),
    # 类别四：平台规则（部门规章 + 平台规则）
    'cat4_网络交易监督管理办法.txt': ('platform_rule', '网络交易监督管理办法'),
    'cat4_网络购买商品七日无理由退货暂行办法.txt': ('platform_rule', '网络购买商品七日无理由退货暂行办法'),
    'cat4_网络零售第三方平台交易规则制定程序规定.txt': ('platform_rule', '网络零售第三方平台交易规则制定程序规定（试行）'),
}

# 平台规则文件（存入 PlatformRule 表）
PLATFORM_RULE_FILES = {
    'cat4_京东规则1.txt': ('京东', '京东开放平台交易纠纷处理总则'),
    'cat4_京东规则2.txt': ('京东', '京东开放平台商品类问题纠纷处理标准'),
    'cat4_淘宝规则.txt': ('淘宝', '淘宝平台争议处理规则'),
}

# ============================================================
# 关键词与适用场景自动标注（基于法律名称和章节）
# ============================================================
LAW_KEYWORDS_MAP = {
    '中华人民共和国消费者权益保护法': {
        'keywords': ['消费者', '经营者', '退一赔三', '欺诈', '七日退货', '三包'],
        'scenarios': ['虚假宣传', '欺诈', '退货退款', '产品质量', '售后服务'],
    },
    '中华人民共和国电子商务法': {
        'keywords': ['电商平台', '平台责任', '订单成立', '商家义务'],
        'scenarios': ['电商平台责任', '订单纠纷', '虚假宣传', '延迟发货'],
    },
    '中华人民共和国民法典（合同编）': {
        'keywords': ['合同', '违约', '履行', '解除', '赔偿'],
        'scenarios': ['合同纠纷', '违约责任', '合同解除'],
    },
    '中华人民共和国民法典（侵权责任编）': {
        'keywords': ['侵权', '产品责任', '损害赔偿'],
        'scenarios': ['产品责任', '侵权损害', '人身伤害'],
    },
    '中华人民共和国食品安全法': {
        'keywords': ['食品安全', '十倍赔偿', '保质期', '食品添加剂'],
        'scenarios': ['食品过期', '食品变质', '异物', '食品安全'],
    },
    '中华人民共和国产品质量法': {
        'keywords': ['产品质量', '三包', '瑕疵', '缺陷'],
        'scenarios': ['质量问题', '产品缺陷', '三包责任'],
    },
    '中华人民共和国反不正当竞争法': {
        'keywords': ['不正当竞争', '虚假宣传', '商业诋毁', '混淆'],
        'scenarios': ['虚假宣传', '商业诋毁', '不正当竞争'],
    },
    '中华人民共和国价格法': {
        'keywords': ['价格', '价格欺诈', '明码标价', '政府定价'],
        'scenarios': ['价格欺诈', '虚构原价', '虚假折扣'],
    },
    '中华人民共和国广告法': {
        'keywords': ['广告', '虚假广告', '极限用语', '代言'],
        'scenarios': ['虚假广告', '极限用语', '误导宣传'],
    },
    '合同行政监督管理办法': {
        'keywords': ['格式条款', '霸王条款', '合同监管'],
        'scenarios': ['格式条款', '霸王条款', '合同纠纷'],
    },
    '中华人民共和国个人信息保护法': {
        'keywords': ['个人信息', '数据泄露', '隐私', '信息处理'],
        'scenarios': ['信息泄露', '隐私侵权', '数据合规'],
    },
    '中华人民共和国药品管理法': {
        'keywords': ['药品', '假药', '劣药', '药品质量'],
        'scenarios': ['药品安全', '假药劣药', '药品质量'],
    },
    '中华人民共和国农产品质量安全法': {
        'keywords': ['农产品', '农残', '质量安全'],
        'scenarios': ['农产品质量', '农残超标'],
    },
    '中华人民共和国反食品浪费法': {
        'keywords': ['食品浪费', '餐饮服务', '光盘行动'],
        'scenarios': ['食品浪费', '餐饮服务'],
    },
    '网络交易监督管理办法': {
        'keywords': ['网络交易', '平台责任', '商家义务'],
        'scenarios': ['网络交易', '平台责任', '商家违规'],
    },
    '网络购买商品七日无理由退货暂行办法': {
        'keywords': ['七日无理由', '退货', '商品完好'],
        'scenarios': ['七日退货', '退货被拒', '商品完好标准'],
    },
    '网络零售第三方平台交易规则制定程序规定（试行）': {
        'keywords': ['平台规则', '交易规则', '备案'],
        'scenarios': ['平台规则制定', '交易规则备案'],
    },
}

# ============================================================
# 正则表达式
# ============================================================
# 章节标题：第一章 总则 / 第一章　总则 / 　　第一章　总则（行首可能有全角空格）
RE_CHAPTER = re.compile(r'^[\s\u3000]*第[一二三四五六七八九十百千零]+章[\s\u3000]+(.+?)\s*$')
# 节标题：第一节 概述
RE_SECTION = re.compile(r'^[\s\u3000]*第[一二三四五六七八九十百千零]+节[\s\u3000]+(.+?)\s*$')
# 条文起始：第一条 ... / 第一条　... / 第一千一百六十四条 ...（支持千位中文数字）
RE_ARTICLE = re.compile(r'^[\s\u3000]*第([一二三四五六七八九十百千零]+)条[\s\u3000]*(.*)$')
# 目录标记
RE_TOC = re.compile(r'^目\s*录\s*$')
# 正文开始/结束标记
RE_BODY_START = re.compile(r'====\s*正文开始\s*====')
RE_BODY_END = re.compile(r'====\s*正文结束\s*====')
# 头部元信息
RE_META = re.compile(r'【([^】]+)】(.*)')


def parse_meta_header(lines: list[str]) -> dict:
    """解析文件头部元信息。"""
    meta = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if RE_BODY_START.search(line):
            break
        m = RE_META.match(line)
        if m:
            key = m.group(1).strip()
            value = m.group(2).strip()
            meta[key] = value
    return meta


def extract_body(lines: list[str]) -> list[str]:
    """提取正文部分（==== 正文开始 ==== 与 ==== 正文结束 ==== 之间）。"""
    in_body = False
    body = []
    for line in lines:
        if RE_BODY_START.search(line):
            in_body = True
            continue
        if RE_BODY_END.search(line):
            break
        if in_body:
            body.append(line)
    return body


def skip_toc(body_lines: list[str]) -> list[str]:
    """跳过目录部分（从'目 录'到第一个章节标题之间）。"""
    result = []
    in_toc = False
    toc_ended = False
    for line in body_lines:
        stripped = line.strip()
        if RE_TOC.match(stripped):
            in_toc = True
            continue
        if in_toc and not toc_ended:
            # 目录中的章节标题格式：　　第一章　总则（前面有缩进）
            if RE_CHAPTER.match(stripped) and not stripped.startswith('　　'):
                toc_ended = True
                result.append(line)
                continue
            # 跳过目录行
            continue
        result.append(line)
    return result


def parse_articles(body_lines: list[str], law_name: str, category: str,
                   source_url: str, effective_date: str) -> list[dict]:
    """解析正文，提取条文列表。"""
    articles = []
    current_chapter = ''
    current_section = ''
    current_article = None
    current_article_num = 0

    # 中文数字转阿拉伯数字（用于排序）
    cn_num_map = {'零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
                  '六': 6, '七': 7, '八': 8, '九': 9, '十': 10, '百': 100, '千': 1000}

    def cn_to_int(cn: str) -> int:
        """中文数字转整数（支持1-9999，如 一千一百六十四 → 1164）。"""
        if not cn:
            return 0
        result = 0
        temp = 0
        for ch in cn:
            if ch not in cn_num_map:
                continue
            val = cn_num_map[ch]
            if val >= 10:
                if temp == 0:
                    temp = 1
                result += temp * val
                temp = 0
            else:
                temp = val
        result += temp
        return result

    for line in body_lines:
        stripped = line.strip()
        if not stripped:
            if current_article:
                current_article['content'] += '\n'
            continue

        # 章节标题
        m = RE_CHAPTER.match(stripped)
        if m:
            current_chapter = stripped.replace('\u3000', ' ').replace('  ', ' ')
            current_section = ''
            continue

        # 节标题
        m = RE_SECTION.match(stripped)
        if m:
            current_section = stripped.replace('\u3000', ' ').replace('  ', ' ')
            continue

        # 条文起始
        m = RE_ARTICLE.match(stripped)
        if m:
            # 保存上一条
            if current_article:
                current_article['content'] = current_article['content'].strip()
                articles.append(current_article)

            article_cn = m.group(1)
            article_content = m.group(2)
            current_article_num = cn_to_int(article_cn)

            current_article = {
                'law_name': law_name,
                'article_number': f'第{article_cn}条',
                'article_number_int': current_article_num,
                'chapter': current_chapter,
                'section': current_section,
                'content': article_content,
                'category': category,
                'source_url': source_url,
                'effective_date': effective_date,
            }
        else:
            # 条文续行（含括号项、多段内容）
            if current_article:
                if current_article['content'].endswith('\n'):
                    current_article['content'] += stripped
                else:
                    current_article['content'] += stripped
                current_article['content'] += '\n'

    # 保存最后一条
    if current_article:
        current_article['content'] = current_article['content'].strip()
        articles.append(current_article)

    return articles


def add_keywords_and_scenarios(articles: list[dict], law_name: str):
    """为每条法条添加 keywords 和 applicable_scenarios。"""
    kw_info = LAW_KEYWORDS_MAP.get(law_name, {
        'keywords': [],
        'scenarios': [],
    })
    for article in articles:
        article['keywords'] = kw_info['keywords']
        article['applicable_scenarios'] = kw_info['scenarios']
        # 生成 summary：取内容前80字
        content = article['content'].replace('\n', ' ').strip()
        if len(content) > 80:
            article['summary'] = content[:77] + '...'
        else:
            article['summary'] = content


def parse_law_file(file_path: Path) -> tuple[list[dict], dict]:
    """解析单个法律文件。"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    lines = content.split('\n')

    # 解析头部元信息
    meta = parse_meta_header(lines)

    # 提取正文
    body = extract_body(lines)

    # 跳过目录
    body = skip_toc(body)

    # 获取法律分类和标准名称
    filename = file_path.name
    category, law_name = FILE_CATEGORY_MAP.get(filename, ('other', meta.get('法律名称', filename)))

    # 获取元信息
    source_url = meta.get('数据源URL', '')
    effective_date_str = meta.get('施行日期', '')

    # 解析条文
    articles = parse_articles(body, law_name, category, source_url, effective_date_str)

    # 添加关键词和适用场景
    add_keywords_and_scenarios(articles, law_name)

    # 解析预期条款数（去掉非数字字符，如"41条" → 41）
    expected_str = meta.get('条款数', '')
    expected_digits = re.sub(r'[^\d]', '', expected_str)
    expected_count = int(expected_digits) if expected_digits else 0

    # 统计信息
    stats = {
        'filename': filename,
        'law_name': law_name,
        'category': category,
        'source_url': source_url,
        'effective_date': effective_date_str,
        'expected_count': expected_count,
        'actual_count': len(articles),
    }

    return articles, stats


def parse_platform_rule_file(file_path: Path) -> tuple[list[dict], dict]:
    """解析平台规则文件。"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    lines = content.split('\n')

    meta = parse_meta_header(lines)
    body = extract_body(lines)
    body = skip_toc(body)

    filename = file_path.name
    platform, rule_name = PLATFORM_RULE_FILES.get(filename, ('未知平台', meta.get('规则名称', filename)))

    source_url = meta.get('数据源URL', '')
    effective_date_str = meta.get('施行日期', '')

    # 平台规则的条文格式与法律相同
    articles = parse_articles(body, rule_name, 'platform_rule', source_url, effective_date_str)

    # 为平台规则添加平台名称
    for article in articles:
        article['platform'] = platform
        article['rule_name'] = rule_name

    add_keywords_and_scenarios(articles, rule_name)

    # 解析预期条款数（去掉非数字字符）
    expected_str = meta.get('条款数', '')
    expected_digits = re.sub(r'[^\d]', '', expected_str)
    expected_count = int(expected_digits) if expected_digits else 0

    stats = {
        'filename': filename,
        'platform': platform,
        'rule_name': rule_name,
        'source_url': source_url,
        'effective_date': effective_date_str,
        'expected_count': expected_count,
        'actual_count': len(articles),
    }

    return articles, stats


def main():
    """主函数：解析所有法律文件并输出 JSON。"""
    base_dir = Path(__file__).parent
    output_dir = base_dir / 'output'
    output_dir.mkdir(exist_ok=True)

    all_law_articles = []
    all_platform_rules = []
    all_stats = []

    # 解析法律文件
    for filename, (category, law_name) in FILE_CATEGORY_MAP.items():
        file_path = base_dir / filename
        if not file_path.exists():
            print(f'[SKIP] 文件不存在: {filename}')
            continue

        articles, stats = parse_law_file(file_path)
        all_law_articles.extend(articles)
        all_stats.append(stats)

        match = '✓' if stats['expected_count'] == stats['actual_count'] else '⚠'
        print(f'{match} {filename}: 预期 {stats["expected_count"]} 条, 实际 {stats["actual_count"]} 条')

    # 解析平台规则文件
    print('\n--- 平台规则 ---')
    for filename, (platform, rule_name) in PLATFORM_RULE_FILES.items():
        file_path = base_dir / filename
        if not file_path.exists():
            print(f'[SKIP] 文件不存在: {filename}')
            continue

        articles, stats = parse_platform_rule_file(file_path)
        all_platform_rules.extend(articles)
        all_stats.append(stats)

        match = '✓' if stats['expected_count'] == stats['actual_count'] else '⚠'
        print(f'{match} {filename} ({platform}): 预期 {stats["expected_count"]} 条, 实际 {stats["actual_count"]} 条')

    # 输出 JSON 文件
    law_output = output_dir / 'law_articles_parsed.json'
    with open(law_output, 'w', encoding='utf-8') as f:
        json.dump(all_law_articles, f, ensure_ascii=False, indent=2)
    print(f'\n法律条文 JSON: {law_output} ({len(all_law_articles)} 条)')

    platform_output = output_dir / 'platform_rules_parsed.json'
    with open(platform_output, 'w', encoding='utf-8') as f:
        json.dump(all_platform_rules, f, ensure_ascii=False, indent=2)
    print(f'平台规则 JSON: {platform_output} ({len(all_platform_rules)} 条)')

    # 统计信息
    stats_output = output_dir / 'parse_stats.json'
    with open(stats_output, 'w', encoding='utf-8') as f:
        json.dump(all_stats, f, ensure_ascii=False, indent=2)

    # 汇总
    print(f'\n========== 解析完成 ==========')
    print(f'法律/规章条文: {len(all_law_articles)} 条')
    print(f'平台规则条文: {len(all_platform_rules)} 条')
    print(f'合计: {len(all_law_articles) + len(all_platform_rules)} 条')

    # 按分类统计
    category_counts = {}
    for article in all_law_articles:
        cat = article['category']
        category_counts[cat] = category_counts.get(cat, 0) + 1
    print('\n按分类统计（法律/规章）:')
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        print(f'  {cat}: {count} 条')

    # 预期 vs 实际对比
    mismatches = [s for s in all_stats if s['expected_count'] != s['actual_count']]
    if mismatches:
        print(f'\n⚠ 数量不匹配的文件: {len(mismatches)}')
        for m in mismatches:
            print(f'  {m["filename"]}: 预期 {m["expected_count"]}, 实际 {m["actual_count"]}')
    else:
        print('\n✓ 所有文件条款数匹配')


if __name__ == '__main__':
    main()
