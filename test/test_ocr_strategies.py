# -*- coding: utf-8 -*-
"""OCR 策略对比测试脚本。

分别测试 LLMVisionStrategy 和 PaddleOCRStrategy 对 test/image_1.png 的识别效果，
验证两个策略的可用性并对比识别质量。
"""
import os
import sys
import time
import django
from pathlib import Path

# 在导入 paddleocr/paddlex 之前，重定向缓存目录到项目内可写路径
# 避免 TRAE 沙盒限制访问 ~/.paddlex/locks/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault('PADDLE_PDX_CACHE_HOME', str(_PROJECT_ROOT / '.paddlex_cache'))
# 临时目录重定向，避免沙盒限制系统 Temp
os.environ.setdefault('TEMP', str(_PROJECT_ROOT / '.tmp'))
os.environ.setdefault('TMP', str(_PROJECT_ROOT / '.tmp'))
# 禁用 PIR 执行器，回退到旧执行器（绕过 paddlepaddle 3.x PIR + oneDNN 兼容性 bug）
os.environ.setdefault('FLAGS_enable_pir_in_executor', '0')
os.environ.setdefault('FLAGS_enable_pir_api', '0')

# 设置 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'claimcraft.settings')
sys.path.insert(0, str(_PROJECT_ROOT / 'backend'))
django.setup()

# 加载 .env
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / '.env')

from api.services.ocr_strategies import (
    LLMVisionStrategy,
    PaddleOCRStrategy,
    PaddleOCRCloudStrategy,
    OCRPipeline,
)

IMAGE_PATH = str(Path(__file__).resolve().parent / 'image_1.png')


def test_strategy(strategy_class, name):
    """测试单个策略。"""
    print(f"\n{'='*60}")
    print(f"测试策略：{name}")
    print(f"{'='*60}")

    # 1. 初始化
    t0 = time.time()
    try:
        strategy = strategy_class()
        print(f"[OK] 初始化成功（{time.time()-t0:.2f}s）")
    except Exception as e:
        print(f"[FAIL] 初始化失败：{type(e).__name__}: {e}")
        return None

    # 2. 识别
    t0 = time.time()
    try:
        text = strategy.recognize(IMAGE_PATH)
        elapsed = time.time() - t0
        print(f"[OK] 识别成功（{elapsed:.2f}s）")
        print(f"\n--- 识别结果（{len(text)} 字符）---")
        print(text)
        print("--- 结果结束 ---")
        return text
    except Exception as e:
        elapsed = time.time() - t0
        print(f"[FAIL] 识别失败（{elapsed:.2f}s）：{type(e).__name__}: {e}")
        return None


def test_pipeline():
    """测试完整 Pipeline 级联。"""
    print(f"\n{'='*60}")
    print("测试完整 OCRPipeline 级联（按 OCR_STRATEGIES 配置）")
    print(f"{'='*60}")
    from api.services.ocr_service import ocr_image_with_strategy
    t0 = time.time()
    try:
        text, strategy_name = ocr_image_with_strategy(IMAGE_PATH)
        elapsed = time.time() - t0
        print(f"[OK] Pipeline 命中策略：{strategy_name}（{elapsed:.2f}s）")
        print(f"\n--- Pipeline 结果（{len(text)} 字符）---")
        print(text)
        print("--- 结果结束 ---")
    except Exception as e:
        print(f"[FAIL] Pipeline 失败：{type(e).__name__}: {e}")


if __name__ == '__main__':
    print(f"图片路径：{IMAGE_PATH}")
    print(f"图片大小：{os.path.getsize(IMAGE_PATH)} bytes")
    print(f"OCR_STRATEGIES={os.environ.get('OCR_STRATEGIES')}")
    print(f"LLM_OCR_PROVIDER={os.environ.get('LLM_OCR_PROVIDER')}")
    print(f"LLM_OCR_MODEL={os.environ.get('LLM_OCR_MODEL')}")
    print(f"LLM_OCR_API_KEY={'已配置' if os.environ.get('LLM_OCR_API_KEY') else '未配置'}")
    print(f"LLM_OCR_API_KEY_PP={'已配置' if os.environ.get('LLM_OCR_API_KEY_PP') else '未配置'}")
    print(f"PADDLEOCR_CLOUD_MODEL={os.environ.get('PADDLEOCR_CLOUD_MODEL', '(默认 PaddleOCR-VL-1.6)')}")

    # 分别测试三个策略
    paddle_vl_text = test_strategy(PaddleOCRCloudStrategy, 'PaddleOCRCloudStrategy (PaddleOCR-VL-1.6)')
    llm_text = test_strategy(LLMVisionStrategy, 'LLMVisionStrategy (DeepSeek-OCR)')
    paddle_text = test_strategy(PaddleOCRStrategy, 'PaddleOCRStrategy (本地)')

    # 测试完整 Pipeline
    test_pipeline()

    # 对比摘要
    print(f"\n{'='*60}")
    print("识别效果对比摘要")
    print(f"{'='*60}")
    print(f"PaddleOCR-VL 云端 识别字符数：{len(paddle_vl_text) if paddle_vl_text else 0}")
    print(f"LLM Vision (DeepSeek-OCR) 识别字符数：{len(llm_text) if llm_text else 0}")
    print(f"PaddleOCR 本地 识别字符数：{len(paddle_text) if paddle_text else 0}")
