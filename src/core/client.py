import asyncio
import json
import logging
import os
import re
import subprocess
from typing import Optional

from notebooklm import NotebookLMClient
from src.config import API_DELAY_SECONDS, MAX_RETRIES, RETRY_BASE_SECONDS, RETRY_MAX_SECONDS
from src.core.diagnostics import FailureType, diagnose_exception

logger = logging.getLogger("NotebookWrapper")

class SafeNotebookClient:
    """包装 NotebookLMClient，加入安全延时、重试机制和数据清洗"""
    
    def __init__(self):
        self.client = None
        self.last_failure = None

    async def _run_notebooklm_cli(self, args: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()

        def _run():
            return subprocess.run(
                ["notebooklm", *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )

        return await asyncio.to_thread(_run)

    async def _doctor_auth_status(self) -> Optional[bool]:
        try:
            result = await self._run_notebooklm_cli(["doctor", "--json"], timeout=30)
            if result.returncode != 0:
                return None
            data = json.loads(result.stdout or "{}")
            auth = (data.get("checks") or {}).get("auth") or {}
            status = auth.get("status")
            if status == "pass":
                return True
            if status == "fail":
                return False
            return None
        except Exception:
            return None

    async def _attempt_reauth(self) -> bool:
        logger.warning("检测到认证异常，尝试自动执行 notebooklm login 进行恢复...")

        before = await self._doctor_auth_status()
        if before is True:
            try:
                await self.client.refresh_auth()
                return True
            except Exception:
                pass

        try:
            result = await self._run_notebooklm_cli(["login"], timeout=180)
        except Exception as e:
            diag = diagnose_exception(e, stage="notebooklm login")
            self.last_failure = diag
            logger.error(f"自动登录启动失败[{diag.failure_type.value}]: {diag.summary}\n建议: {diag.action}\n详情: {diag.details}")
            return False

        if result.returncode != 0:
            combined = "\n".join([result.stdout or "", result.stderr or ""]).strip()
            diag = diagnose_exception(RuntimeError(combined or f"notebooklm login failed with code {result.returncode}"), stage="notebooklm login")
            self.last_failure = diag
            logger.error(f"自动登录失败[{diag.failure_type.value}]: {diag.summary}\n建议: {diag.action}\n详情: {combined or diag.details}")
            return False

        after = await self._doctor_auth_status()
        if after is False:
            diag = diagnose_exception(RuntimeError("not authenticated after login"), stage="notebooklm doctor")
            self.last_failure = diag
            logger.error(f"自动登录后仍未认证[{diag.failure_type.value}]: {diag.summary}\n建议: {diag.action}\n详情: {diag.details}")
            return False

        return True

    async def ensure_authenticated(self) -> bool:
        """在主流程启动前检查认证状态，必要时自动拉起登录。"""
        status = await self._doctor_auth_status()
        if status is True:
            logger.info("检测到 NotebookLM 已登录，继续执行主流程。")
            return True
        if status is False:
            logger.warning("当前 NotebookLM 未登录，准备自动拉起浏览器登录...")
            return await self._attempt_reauth()

        logger.warning("暂时无法确认 NotebookLM 登录状态，将继续尝试建立连接。")
        return True

    def _diagnose_suspicious_text(self, text: str, *, stage: str):
        t = (text or "").strip()
        if not t:
            return None
        tl = t.lower()
        if "<html" in tl or "<!doctype html" in tl:
            diag = diagnose_exception(RuntimeError("captcha/verify you are human/html response"), stage=stage)
            self.last_failure = diag
            return diag
        if any(k in tl for k in ["verify you are human", "captcha", "unusual traffic", "access denied", "robot"]):
            diag = diagnose_exception(RuntimeError("captcha/verify you are human"), stage=stage)
            self.last_failure = diag
            return diag
        if any(
            k in tl
            for k in [
                "authentication expired",
                "unauthorized",
                "unauthenticated",
                "login required",
                "status code 16",
            ]
        ):
            diag = diagnose_exception(RuntimeError("Authentication expired"), stage=stage)
            self.last_failure = diag
            return diag
        return None

    async def connect(self):
        return await self._connect(allow_reauth=True)

    async def _connect(self, *, allow_reauth: bool):
        self.last_failure = None
        try:
            try:
                self.client = await NotebookLMClient.from_storage()
            except Exception as e:
                diag = diagnose_exception(e, stage="from_storage")
                self.last_failure = diag
                logger.error(f"连接失败(from_storage)[{diag.failure_type.value}]: {diag.summary}\n建议: {diag.action}\n详情: {diag.details}")
                if allow_reauth and diag.failure_type == FailureType.AUTH:
                    if await self._attempt_reauth():
                        self.client = None
                        return await self._connect(allow_reauth=False)
                return False

            try:
                await self.client.__aenter__()
            except Exception as e:
                diag = diagnose_exception(e, stage="__aenter__")
                self.last_failure = diag
                logger.error(f"连接失败(__aenter__)[{diag.failure_type.value}]: {diag.summary}\n建议: {diag.action}\n详情: {diag.details}")
                if allow_reauth and diag.failure_type == FailureType.AUTH:
                    await self.close()
                    self.client = None
                    if await self._attempt_reauth():
                        return await self._connect(allow_reauth=False)
                return False

            try:
                await self.client.refresh_auth()
            except Exception as e:
                diag = diagnose_exception(e, stage="refresh_auth")
                self.last_failure = diag
                logger.error(f"连接失败(refresh_auth)[{diag.failure_type.value}]: {diag.summary}\n建议: {diag.action}\n详情: {diag.details}")
                if allow_reauth and diag.failure_type == FailureType.AUTH:
                    if await self._attempt_reauth():
                        await self.close()
                        self.client = None
                        return await self._connect(allow_reauth=False)
                return False

            logger.info("成功连接 Google NotebookLM 并刷新 Token。")
            return True
        except Exception as e:
            diag = diagnose_exception(e, stage="connect")
            self.last_failure = diag
            logger.error(f"连接失败(connect)[{diag.failure_type.value}]: {diag.summary}\n建议: {diag.action}\n详情: {diag.details}", exc_info=True)
            return False

    async def close(self):
        if self.client:
            await self.client.__aexit__(None, None, None)

    async def list_notebooks(self):
        return await self._list_notebooks(allow_reauth=True)

    async def _list_notebooks(self, *, allow_reauth: bool):
        if not self.client: return []
        self.last_failure = None
        try:
            return await self.client.notebooks.list()
        except Exception as e:
            diag = diagnose_exception(e, stage="list_notebooks")
            self.last_failure = diag
            logger.error(f"获取笔记本列表失败[{diag.failure_type.value}]: {diag.summary}\n建议: {diag.action}\n详情: {diag.details}")
            if allow_reauth and diag.failure_type == FailureType.AUTH:
                if await self._attempt_reauth() and await self._connect(allow_reauth=False):
                    return await self._list_notebooks(allow_reauth=False)
            return []

    async def ask_with_retry(self, notebook_id: str, prompt: str) -> str:
        """带有防封号延时和错误重试的请求方法"""
        if not self.client: return ""
        self.last_failure = None

        reauth_attempted = False
        skip_delay_next = False
        for attempt in range(MAX_RETRIES):
            try:
                if not skip_delay_next:
                    logger.info(f"等待 {API_DELAY_SECONDS} 秒以保护账号安全...")
                    await asyncio.sleep(API_DELAY_SECONDS)
                else:
                    skip_delay_next = False
                
                # 发送请求，如果成功，返回 answer
                result = await self.client.chat.ask(notebook_id, prompt)
                
                # NotebookLMClient.chat.ask 返回 AskResult 对象
                # 兼容不同版本的 notebooklm-py
                if hasattr(result, 'answer'):
                    text = result.answer.strip()
                elif hasattr(result, 'text'):
                    text = result.text.strip()
                elif isinstance(result, str):
                    text = result.strip()
                else:
                    logger.warning(f"请求返回了意外的格式: {result}")
                    text = str(result).strip()

                suspicious_diag = self._diagnose_suspicious_text(text, stage="chat.ask.response")
                if suspicious_diag:
                    if suspicious_diag.failure_type == FailureType.AUTH and not reauth_attempted:
                        reauth_attempted = True
                        logger.warning("响应内容显示认证已失效，尝试自动恢复后重试当前请求。")
                        if await self._attempt_reauth() and await self._connect(allow_reauth=False):
                            logger.info("认证恢复成功，继续生成流程。")
                            skip_delay_next = True
                            continue
                    return ""
                return text
                    
            except Exception as e:
                diag = diagnose_exception(e, stage="chat.ask")
                self.last_failure = diag

                logger.warning(
                    f"请求失败 (尝试 {attempt+1}/{MAX_RETRIES})[{diag.failure_type.value}]: {diag.summary}\n建议: {diag.action}\n详情: {diag.details}",
                    exc_info=True,
                )

                if diag.failure_type == FailureType.AUTH and not reauth_attempted:
                    reauth_attempted = True
                    if await self._attempt_reauth() and await self._connect(allow_reauth=False):
                        logger.info("认证恢复成功，继续生成流程。")
                        skip_delay_next = True
                        continue
                    return ""

                if not diag.retryable:
                    if diag.failure_type == FailureType.AUTH:
                        logger.error("认证问题导致无法继续请求。")
                    return ""

                if attempt < MAX_RETRIES - 1:
                    base_sleep = diag.wait_seconds if diag.wait_seconds is not None else 0
                    exp_sleep = min(RETRY_MAX_SECONDS, RETRY_BASE_SECONDS * (2 ** attempt))
                    sleep_time = max(base_sleep, exp_sleep)
                    logger.info(f"等待 {sleep_time} 秒后重试...")
                    await asyncio.sleep(sleep_time)
                    
        logger.error("达到最大重试次数，请求彻底失败。")
        return ""

    async def extract_outline(self, notebook_id: str) -> list:
        """让大模型提取 JSON 格式的章节大纲，并暴力清洗结果"""
        prompt = """请分析你所拥有的所有资料（包括教材和讲义），为我提取这门课的核心章节与小节目录，并在第一次大纲提取时就给出每个小节的学习类型判断。
要求：
1. 提取核心的章（Chapter）以及每章下面的核心节（Section）。
2. 对每个小节，你需要结合资料判断：
   - `style`: 只能是 `text_heavy`、`formula_heavy`、`mixed`
   - `derivation_needed`: 是否需要独立的严谨推导补充层
   - `visual_needed`: 是否需要可渲染图示
   - `visual_type`: 只能是 `none`、`svg_curve`、`svg_effect_decomposition`、`mermaid_flowchart`、`mermaid_structure`
   - `visual_ratio`: 只能是 `square`、`landscape_4_3`、`landscape_16_9`
   - `style_reason`: 用一句中文说明为什么这么判断
   - `visual_reason`: 用一句中文说明为什么需要或不需要图示，以及为什么是这种图
3. 必须输出为纯 JSON 格式的数组，数组中每个元素是一个对象，格式严格如下：
[
  {
    "chapter": "第一章：xxx",
    "sections": ["1.1 节名称", "1.2 节名称"],
    "section_plans": {
      "1.1 节名称": {
        "style": "text_heavy",
        "derivation_needed": false,
        "visual_needed": true,
        "visual_type": "svg_curve",
        "visual_ratio": "landscape_4_3",
        "style_reason": "本节主要是概念关系与机制说明，公式不是主体。",
        "visual_reason": "本节需要在坐标轴上展示曲线与均衡点，用 SVG 曲线图更直观且更适合控制比例。"
      }
    }
  }
]
4. `section_plans` 中的键必须与 `sections` 数组中的小节标题完全一致。
5. 判断必须以资料主内容为准，不要只根据标题机械猜测。
6. 微观/宏观经济学中凡是依赖坐标轴、曲线、预算线、无差异曲线、均衡点、替代效应/收入效应的内容，优先判断为 SVG 图，而不是流程框图。
6. 绝对不要有任何多余的解释、寒暄或 Markdown 格式。"""
        
        raw_response = await self.ask_with_retry(notebook_id, prompt)
        if not raw_response:
            return []

        # 暴力清洗：提取 JSON 数组
        if self._diagnose_suspicious_text(raw_response, stage="extract_outline"):
            logger.error(f"大模型返回内容疑似被拦截或需要重新登录。\n原始回复：\n{raw_response}")
            return []

        match = re.search(r'\[.*\]', raw_response, re.DOTALL)
        if match:
            try:
                outline = json.loads(match.group(0))
                if isinstance(outline, list) and outline:
                    return outline
            except json.JSONDecodeError:
                pass
                
        logger.error(f"无法从大模型回复中提取有效的章节 JSON 列表。\n原始回复：\n{raw_response}")
        return []
