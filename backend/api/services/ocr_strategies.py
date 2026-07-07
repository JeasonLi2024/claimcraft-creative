# -*- coding: utf-8 -*-
"""OCR 多引擎策略抽象 + 级联 Pipeline。

支持 5 种策略：
- TesseractStrategy：本地 Tesseract，离线可用
- PaddleOCRStrategy：本地 PaddleOCR，中文识别率高（需显式启用）
- PaddleOCRCloudStrategy：PaddleOCR-VL 云端服务（aistudio，需 LLM_OCR_API_KEY_PP）
- LLMVisionStrategy：多模态 LLM（DeepSeek-OCR 等，需 LLM_OCR_API_KEY）
- MockStrategy：兜底预置文本

通过环境变量 OCR_STRATEGIES 配置策略链（逗号分隔，按优先级）。
"""
import os
import json
import time
import logging
import base64
from abc import ABC, abstractmethod
from typing import Optional

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

logger = logging.getLogger(__name__)


def _get_ocr_retry_config() -> dict:
    """从 .env 读取 OCR 策略级重试参数。

    Returns:
        dict: {max_attempts, wait_min, wait_max}
    """
    return {
        'max_attempts': int(os.environ.get('OCR_RETRY_MAX_ATTEMPTS', '3') or '3'),
        'wait_min': int(os.environ.get('OCR_RETRY_WAIT_MIN', '1') or '1'),
        'wait_max': int(os.environ.get('OCR_RETRY_WAIT_MAX', '8') or '8'),
    }


def _build_ocr_retry():
    """构造 OCR 重试装饰器（参数从 .env 读取，运行时生效）。"""
    cfg = _get_ocr_retry_config()
    return retry(
        stop=stop_after_attempt(cfg['max_attempts']),
        wait=wait_exponential(multiplier=1, min=cfg['wait_min'], max=cfg['wait_max']),
        retry=retry_if_exception_type((TimeoutError, ConnectionError, OSError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


# 模块加载时构造默认装饰器（参数从 .env 读取）
_ocr_retry = _build_ocr_retry()


async def _encode_and_compress_image(image_path: str, max_mb: int) -> tuple[str, str]:
    """读取图片并按大小上限压缩，返回 base64 编码 + MIME 类型。

    安全最佳实践（DJANGO-UPLOAD-001）：
    - 设置 Image.MAX_IMAGE_PIXELS 防止解压炸弹 DoS
    - 按质量递降压缩至阈值以下
    - 统一转 JPEG 格式（兼容性最佳）

    Args:
        image_path: 图片本地路径（Django storage 管理，非用户直接输入）
        max_mb: 最大图片大小（MB）

    Returns:
        (base64_data, mime_type)
    """
    from asgiref.sync import sync_to_async
    from PIL import Image
    import io

    # 安全：限制 PIL 解压炸弹（2 亿像素上限，约 14000x14000）
    Image.MAX_IMAGE_PIXELS = 200_000_000

    def _compress():
        img = Image.open(image_path)
        # 转换色彩模式（RGBA/P 转 RGB）
        if img.mode in ('RGBA', 'P', 'LA'):
            img = img.convert('RGB')

        quality = 85
        while quality >= 30:
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=quality)
            size_mb = buf.tell() / 1024 / 1024
            if size_mb <= max_mb:
                break
            quality -= 10

        return base64.b64encode(buf.getvalue()).decode('utf-8'), 'jpeg'

    return await sync_to_async(_compress)()


class OCRStrategy(ABC):
    """OCR 策略抽象基类（v9 异步化）。"""
    name: str = "base"

    @abstractmethod
    async def recognize(self, image_path: str, category: str = "") -> str:
        """识别图片文本，返回纯文本。失败抛异常。

        Args:
            image_path: 图片本地路径
            category: 证据类别（用于按类型选 prompt，仅 LLMVisionStrategy 生效）
        """
        ...

    async def correct_text(self, raw_text: str, case_description: str = "") -> str:
        """文本纠错（默认不纠错，子类按需重写）。

        约定：与 recognize() 用同一模型纠错，确保「识别用啥纠错用啥」。
        - LLMVisionStrategy：用同款 LLM 纠错（重写）
        - PaddleOCRCloudStrategy / PaddleOCRStrategy / TesseractStrategy / MockStrategy：
          非 LLM 模型，无文本纠错能力，直接返回原文

        Args:
            raw_text: OCR 识别的原始文本
            case_description: 案件描述（可选，用于纠错上下文）
        """
        return raw_text


class TesseractStrategy(OCRStrategy):
    """本地 Tesseract 策略。"""
    name = "tesseract"

    def __init__(self):
        # 复用 ocr_service 的跨平台路径解析
        from api.services.ocr_service import TESSERACT_CMD
        if not TESSERACT_CMD:
            raise RuntimeError("Tesseract 未在 PATH 中且 TESSERACT_CMD 未配置")
        self.tesseract_cmd = TESSERACT_CMD

    async def recognize(self, image_path: str, category: str = "") -> str:
        from asgiref.sync import sync_to_async
        import pytesseract
        from PIL import Image
        pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd
        # 安全：限制 PIL 解压炸弹（DoS 防护）
        Image.MAX_IMAGE_PIXELS = 200_000_000
        img = await sync_to_async(Image.open)(image_path)
        text = await sync_to_async(pytesseract.image_to_string)(img, lang='chi_sim+eng')
        logger.info(f"Tesseract OCR 成功 (cmd={self.tesseract_cmd})")
        return text.strip()


class PaddleOCRStrategy(OCRStrategy):
    """PaddleOCR 策略：中文识别率比 Tesseract 高 20%+。

    需显式启用：环境变量 OCR_PADDLEOCR_ENABLED=true。
    """
    name = "paddleocr"

    def __init__(self):
        if os.environ.get('OCR_PADDLEOCR_ENABLED', 'false').lower() != 'true':
            raise RuntimeError("PaddleOCR 未启用（设置 OCR_PADDLEOCR_ENABLED=true 启用）")
        try:
            from paddleocr import PaddleOCR
        except ImportError as e:
            raise RuntimeError(
                "未安装 paddleocr。请运行 pip install paddleocr paddlepaddle"
            ) from e
        # 懒加载实例（首次调用时初始化，避免模块导入时开销）
        self._ocr_instance = None

    def _get_instance(self):
        if self._ocr_instance is None:
            from paddleocr import PaddleOCR
            # PaddleOCR 3.x API 变更：use_angle_cls → use_textline_orientation，show_log 已移除
            # 兼容 2.x 和 3.x：优先用新参数，失败回退旧参数
            try:
                self._ocr_instance = PaddleOCR(
                    use_textline_orientation=True,
                    lang='ch',
                )
            except (TypeError, ValueError):
                # 回退到 PaddleOCR 2.x API
                self._ocr_instance = PaddleOCR(
                    use_angle_cls=True,
                    lang='ch',
                    show_log=False,
                )
        return self._ocr_instance

    @_ocr_retry
    async def recognize(self, image_path: str, category: str = "") -> str:
        from asgiref.sync import sync_to_async
        ocr = self._get_instance()
        try:
            # PaddleOCR 3.x 保留 ocr() 方法作为兼容入口
            result = await sync_to_async(ocr.ocr)(image_path, cls=True)
        except TypeError:
            # 3.x 某些版本 ocr() 不接受 cls 参数
            result = await sync_to_async(ocr.ocr)(image_path)
        except Exception as e:
            logger.warning(f"PaddleOCR 调用失败: {type(e).__name__}: {e}")
            raise
        if not result or not result[0]:
            logger.warning("PaddleOCR 返回空结果")
            return ""
        lines = []
        for line in result[0]:
            if line and len(line) >= 2:
                # 兼容 2.x [[box, (text, score)], ...] 和 3.x 可能的结构变化
                text = line[1][0] if isinstance(line[1], (list, tuple)) else str(line[1])
                lines.append(text)
        logger.info(f"PaddleOCR 成功，识别 {len(lines)} 行")
        return "\n".join(lines)


class LLMVisionStrategy(OCRStrategy):
    """多模态 LLM 视觉 OCR 策略。

    通过 langchain-openai 的多模态接口调用 GPT-4o / Qwen-VL / GLM-4V / DeepSeek-OCR。
    配置来源（按场景拆分的 LLM_OCR_* 一组）：

    - LLM_OCR_PROVIDER / LLM_OCR_API_KEY / LLM_OCR_BASE_URL / LLM_OCR_MODEL
    - LLM_OCR_TEMPERATURE / LLM_OCR_TIMEOUT / LLM_OCR_MAX_RETRIES
    - LLM_OCR_PROMPT：自定义 Prompt（可选，留空使用默认）
    - LLM_OCR_MAX_IMAGE_MB：上传图片大小上限（MB，可选）

    如果 LLM_OCR_* 未独立配置，自动回退到通用 LLM_* 配置（向后兼容）。
    """
    name = "llm_vision"

    def __init__(self):
        from api.services.llm_service import is_scenario_available, get_scenario_llm
        if not is_scenario_available('ocr'):
            raise RuntimeError("LLM [ocr] 不可用（未配置 LLM_OCR_API_KEY 或 LLM_API_KEY）")

        # 预热：触发一次场景实例化（失败即抛错，让 Pipeline 自动跳过）
        self._llm = get_scenario_llm('ocr')

    @_ocr_retry
    async def recognize(self, image_path: str, category: str = "") -> str:
        from api.services.llm_service import get_scenario_config
        from api.services.ocr_config import get_llm_ocr_prompt_by_category, get_llm_ocr_max_image_mb
        from langchain_core.messages import HumanMessage

        cfg = get_scenario_config('ocr')
        prompt = get_llm_ocr_prompt_by_category(category)
        logger.info(
            f"LLM Vision OCR 调用 (provider={cfg['provider']}, model={cfg['model']}, "
            f"base_url={cfg['base_url']}, temp={cfg['temperature']}, timeout={cfg['timeout']}, "
            f"category={category or 'default'})"
        )

        # 安全：读取图片并按大小上限压缩（防 DoS + 降延迟）
        image_data, mime = await _encode_and_compress_image(image_path, get_llm_ocr_max_image_mb())

        message = HumanMessage(content=[
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{image_data}"}},
        ])
        try:
            response = await self._llm.ainvoke([message])
        except Exception as e:
            logger.warning(f"LLM Vision OCR 调用失败 (model={cfg['model']}): {type(e).__name__}: {e}")
            raise
        text = response.content if hasattr(response, 'content') else str(response)
        if not text or not text.strip():
            logger.warning(f"LLM Vision OCR 返回空文本 (model={cfg['model']})")
        else:
            logger.info(f"LLM Vision OCR 成功 (model={cfg['model']}, len={len(text)})")
        return text.strip()

    async def correct_text(self, raw_text: str, case_description: str = "") -> str:
        """LLM 纠错：用同款 LLM（self._llm）修错别字（如「兀」→「元」）。

        约定：与 recognize() 用同一 LLM 实例，确保「识别用啥纠错用啥」。
        若纠错失败，返回原文（不影响主流程）。

        Args:
            raw_text: OCR 识别的原始文本
            case_description: 案件描述（可选，用于纠错上下文）
        """
        if not raw_text or not raw_text.strip():
            return raw_text

        from api.services.llm_service import get_scenario_config
        from api.agents.prompts.templates import OCR_CORRECTION_PROMPT

        cfg = get_scenario_config('ocr')
        prompt = OCR_CORRECTION_PROMPT.format(
            case_description=case_description or "（无）",
            raw_text=raw_text,
        )
        logger.info(
            f"LLM 纠错调用 (provider={cfg['provider']}, model={cfg['model']})"
        )

        try:
            response = await self._llm.ainvoke([{"role": "user", "content": prompt}])
            text = response.content if hasattr(response, 'content') else str(response)
            if text and text.strip():
                logger.info(
                    f"LLM 纠错成功 (model={cfg['model']}, "
                    f"raw_len={len(raw_text)}, corrected_len={len(text)})"
                )
                return text.strip()
            logger.warning(f"LLM 纠错返回空文本 (model={cfg['model']})，使用原文")
        except Exception as e:
            logger.warning(
                f"LLM 纠错失败 (model={cfg['model']}): {type(e).__name__}: {e}，使用原文"
            )
        return raw_text


class PaddleOCRCloudStrategy(OCRStrategy):
    """PaddleOCR-VL 云端 OCR 策略（aistudio 在线服务）。

    通过 PaddleOCR-VL-1.6 模型进行高精度文档识别，支持版面分析、表格、公式等。

    所有可调参数均从 .env 读取（命名空间 PADDLEOCR_VL_*），
    业务代码不再硬编码任何 URL/模型名/超时/开关。

    环境变量：
    - PADDLEOCR_VL_TOKEN：aistudio 平台 Token（必填）
    - PADDLEOCR_VL_BASE_URL：任务提交地址（必填）
    - PADDLEOCR_VL_MODEL：模型名（必填）
    - PADDLEOCR_VL_USE_DOC_ORIENTATION：是否启用版面方向分类（true/false）
    - PADDLEOCR_VL_USE_DOC_UNWARPING：是否启用文档矫正（true/false）
    - PADDLEOCR_VL_USE_CHART_RECOGNITION：是否启用图表识别（true/false）
    - PADDLEOCR_VL_POLL_INTERVAL：轮询间隔秒
    - PADDLEOCR_VL_POLL_TIMEOUT：轮询总超时秒
    - PADDLEOCR_VL_REQUEST_TIMEOUT：单次 HTTP 请求超时秒（提交/查询/下载共用）
    """
    name = "paddleocr_vl"

    def __init__(self):
        from api.services.ocr_config import get_paddleocr_vl_config
        cfg = get_paddleocr_vl_config()

        missing = [k for k, v in cfg.items() if v in (None, '') and k in ('token', 'base_url', 'model')]
        if missing:
            raise RuntimeError(
                f"PaddleOCR-VL 策略不可用：.env 中缺少必要配置 {missing}。"
                f"请在 .env 中设置 PADDLEOCR_VL_TOKEN / PADDLEOCR_VL_BASE_URL / PADDLEOCR_VL_MODEL。"
            )

        self._token = cfg['token']
        self._job_url = cfg['base_url']
        self._model = cfg['model']
        self._use_doc_orientation = cfg['use_doc_orientation']
        self._use_doc_unwarping = cfg['use_doc_unwarping']
        self._use_chart_recognition = cfg['use_chart_recognition']
        self._poll_interval = cfg['poll_interval']
        self._poll_timeout = cfg['poll_timeout']
        self._request_timeout = cfg['request_timeout']

    def _submit_job(self, image_path: str) -> str:
        """提交 OCR 任务，返回 jobId。"""
        import requests

        headers = {"Authorization": f"bearer {self._token}"}
        optional_payload = {
            "useDocOrientationClassify": self._use_doc_orientation,
            "useDocUnwarping": self._use_doc_unwarping,
            "useChartRecognition": self._use_chart_recognition,
        }
        data = {
            "model": self._model,
            "optionalPayload": json.dumps(optional_payload),
        }

        with open(image_path, 'rb') as f:
            files = {"file": f}
            resp = requests.post(
                self._job_url, headers=headers, data=data, files=files,
                timeout=self._request_timeout,
            )

        if resp.status_code != 200:
            raise RuntimeError(
                f"提交任务失败 (HTTP {resp.status_code}): {resp.text[:200]}"
            )
        job_id = resp.json().get("data", {}).get("jobId")
        if not job_id:
            raise RuntimeError(f"响应缺少 jobId: {resp.text[:200]}")
        logger.info(
            f"PaddleOCR 云端任务已提交 (model={self._model}, jobId={job_id})"
        )
        return job_id

    def _poll_result(self, job_id: str) -> str:
        """轮询任务结果，返回拼接的 markdown 文本。"""
        import requests

        headers = {"Authorization": f"bearer {self._token}"}
        url = f"{self._job_url}/{job_id}"
        start = time.time()

        while True:
            elapsed = time.time() - start
            if elapsed > self._poll_timeout:
                raise RuntimeError(
                    f"轮询超时（{self._poll_timeout}s），任务仍为未完成状态"
                )

            resp = requests.get(url, headers=headers, timeout=self._request_timeout)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"查询任务状态失败 (HTTP {resp.status_code}): {resp.text[:200]}"
                )

            data = resp.json().get("data", {})
            state = data.get("state", '')

            if state == 'pending':
                logger.debug(f"PaddleOCR 云端任务 pending（{elapsed:.0f}s）")
            elif state == 'running':
                try:
                    progress = data.get("extractProgress", {})
                    total = progress.get("totalPages", '?')
                    extracted = progress.get("extractedPages", 0)
                    logger.debug(
                        f"PaddleOCR 云端任务 running "
                        f"（{elapsed:.0f}s, {extracted}/{total} pages）"
                    )
                except Exception:
                    logger.debug(
                        f"PaddleOCR 云端任务 running（{elapsed:.0f}s）"
                    )
            elif state == 'done':
                jsonl_url = data.get("resultUrl", {}).get("jsonUrl", '')
                if not jsonl_url:
                    raise RuntimeError("任务完成但缺少 resultUrl.jsonUrl")
                logger.info(
                    f"PaddleOCR 云端任务完成（{elapsed:.1f}s），下载结果"
                )
                return self._download_and_parse(jsonl_url)
            elif state == 'failed':
                err = data.get("errorMsg", "未知错误")
                raise RuntimeError(f"任务失败: {err}")
            else:
                logger.debug(
                    f"PaddleOCR 云端任务状态={state}（{elapsed:.0f}s）"
                )

            time.sleep(self._poll_interval)

    def _download_and_parse(self, jsonl_url: str) -> str:
        """下载 jsonl 结果并解析为纯文本。

        PaddleOCR-VL 返回 markdown 格式，含 <img> / <div> 等 HTML 标签。
        这里提取纯文本内容，过滤掉图片占位符等非文本元素，便于后续字段抽取。
        """
        import re
        import requests

        resp = requests.get(jsonl_url, timeout=self._request_timeout)
        resp.raise_for_status()
        lines = resp.text.strip().split('\n')

        all_texts = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            result = obj.get("result", {})
            layout_results = result.get("layoutParsingResults", [])
            for res in layout_results:
                md_text = res.get("markdown", {}).get("text", "")
                if not md_text:
                    continue
                # 过滤 HTML 标签（PaddleOCR-VL 用 <img>/<div> 标记图片和版式）
                clean = re.sub(r'<[^>]+>', '', md_text)
                # 折叠多余空行
                clean = re.sub(r'\n{3,}', '\n\n', clean).strip()
                if clean:
                    all_texts.append(clean)

        return "\n\n".join(all_texts).strip()

    @_ocr_retry
    async def recognize(self, image_path: str, category: str = "") -> str:
        from asgiref.sync import sync_to_async
        logger.info(
            f"PaddleOCR 云端 OCR 调用 (model={self._model})"
        )
        try:
            job_id = await sync_to_async(self._submit_job)(image_path)
            text = await sync_to_async(self._poll_result)(job_id)
        except Exception as e:
            logger.warning(
                f"PaddleOCR 云端 OCR 失败: {type(e).__name__}: {e}"
            )
            raise

        if not text or not text.strip():
            logger.warning(
                f"PaddleOCR 云端 OCR 返回空文本 (model={self._model})"
            )
        else:
            logger.info(
                f"PaddleOCR 云端 OCR 成功 (model={self._model}, len={len(text)})"
            )
        return text.strip()


class MockStrategy(OCRStrategy):
    """Mock 兜底策略，返回预置文本。"""
    name = "mock"

    async def recognize(self, image_path: str, category: str = "") -> str:
        from api.services.ocr_service import MOCK_OCR_TEXT
        logger.info("使用 Mock OCR 兜底")
        return MOCK_OCR_TEXT


class OCRPipeline:
    """多策略级联 Pipeline（v9 异步化）。

    按策略顺序尝试，首个成功即返回。全部失败则用 MockStrategy 兜底。
    """

    def __init__(self, strategies: list[OCRStrategy]):
        self.strategies = strategies

    async def recognize(
        self, image_path: str, case_description: str = "", evidence_category: str = ""
    ) -> tuple[str, str, str]:
        """识别图片文本（异步）。

        Args:
            image_path: 图片本地路径
            case_description: 案件描述（可选，透传给策略的 correct_text 用于纠错上下文）
            evidence_category: 证据类别（透传给 LLMVisionStrategy 选 prompt）

        Returns:
            (raw_text, corrected_text, strategy_name) 三元组
            - raw_text: OCR 原始识别文本
            - corrected_text: 纠错后文本（同款模型纠错；非 LLM 策略等于 raw_text）
            - strategy_name: 命中的策略名
        """
        failures: list[tuple[str, str]] = []
        for s in self.strategies:
            try:
                text = await s.recognize(image_path, evidence_category)
                if text and text.strip():
                    # 用同款模型纠错（策略内部自管）
                    corrected = await s.correct_text(text, case_description)
                    if failures:
                        logger.info(
                            f"OCR 降级链路：{' → '.join(n for n, _ in failures)} → {s.name}（成功）"
                        )
                    return text, corrected, s.name
                else:
                    msg = "返回空文本"
                    logger.warning(f"OCR 策略 {s.name} {msg}，尝试下一策略")
                    failures.append((s.name, msg))
            except Exception as e:
                err_msg = f"{type(e).__name__}: {e}"
                logger.warning(f"OCR 策略 {s.name} 失败：{err_msg}，尝试下一策略")
                failures.append((s.name, err_msg))
                continue
        # 全部失败 → Mock 兜底
        mock = MockStrategy()
        logger.warning(
            f"OCR 全部策略失败，降级到 Mock。失败链路：{failures}"
        )
        text = await mock.recognize(image_path)
        return text, await mock.correct_text(text), mock.name


def get_default_pipeline() -> OCRPipeline:
    """根据环境变量 OCR_STRATEGIES 构建默认 pipeline。

    环境变量格式：逗号分隔的策略名，按优先级排序
    默认：tesseract,mock
    """
    strategy_names = os.environ.get('OCR_STRATEGIES', 'tesseract,mock').split(',')
    strategy_map = {
        'tesseract': TesseractStrategy,
        'paddleocr': PaddleOCRStrategy,
        'paddleocr_vl': PaddleOCRCloudStrategy,
        'llm_vision': LLMVisionStrategy,
        'mock': MockStrategy,
    }
    strategies = []
    for name in strategy_names:
        name = name.strip()
        if not name:
            continue
        cls = strategy_map.get(name)
        if not cls:
            logger.warning(f"未知 OCR 策略: {name}")
            continue
        try:
            strategies.append(cls())
        except Exception as e:
            logger.warning(f"初始化 OCR 策略 {name} 失败: {e}")

    if not strategies:
        logger.warning("无可用 OCR 策略，使用 Mock 兜底")
        strategies.append(MockStrategy())
    return OCRPipeline(strategies)
