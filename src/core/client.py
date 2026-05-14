import asyncio
import json
import logging
import re
from notebooklm import NotebookLMClient
from src.config import API_DELAY_SECONDS, MAX_RETRIES

logger = logging.getLogger("NotebookWrapper")

class SafeNotebookClient:
    """包装 NotebookLMClient，加入安全延时、重试机制和数据清洗"""
    
    def __init__(self):
        self.client = None

    async def connect(self):
        try:
            self.client = await NotebookLMClient.from_storage()
            await self.client.__aenter__()
            await self.client.refresh_auth()
            logger.info("成功连接 Google NotebookLM 并刷新 Token。")
            return True
        except Exception as e:
            logger.error(f"连接失败: {e}")
            return False

    async def close(self):
        if self.client:
            await self.client.__aexit__(None, None, None)

    async def list_notebooks(self):
        if not self.client: return []
        return await self.client.notebooks.list()

    async def ask_with_retry(self, notebook_id: str, prompt: str) -> str:
        """带有防封号延时和错误重试的请求方法"""
        if not self.client: return ""

        for attempt in range(MAX_RETRIES):
            try:
                # 每次提问前强制休息，防止触发防机器人机制
                logger.info(f"等待 {API_DELAY_SECONDS} 秒以保护账号安全...")
                await asyncio.sleep(API_DELAY_SECONDS)
                
                # 发送请求
                result = await self.client.chat.ask(notebook_id, prompt)
                return result.answer.strip()
            except Exception as e:
                logger.warning(f"请求失败 (尝试 {attempt+1}/{MAX_RETRIES}): {e}")
                await asyncio.sleep(API_DELAY_SECONDS * 2)  # 失败后加倍惩罚时间
                
        logger.error("达到最大重试次数，请求彻底失败。")
        return ""

    async def extract_chapters(self, notebook_id: str) -> list:
        """让大模型提取 JSON 格式的章节大纲，并暴力清洗结果"""
        prompt = """请分析你所拥有的所有资料（包括教材和讲义），为我提取出这门课的核心章节目录。
要求：
1. 只需要输出核心的章或大节（建议控制在 5 到 10 个核心模块）。
2. 必须输出为纯 JSON 格式的字符串列表，例如：["第一章：xxx", "第二章：yyy"]。
3. 绝对不要有任何多余的解释、寒暄或 Markdown 格式。"""
        
        raw_response = await self.ask_with_retry(notebook_id, prompt)
        if not raw_response:
            return []

        # 暴力清洗：提取 JSON 数组
        match = re.search(r'\[.*\]', raw_response, re.DOTALL)
        if match:
            try:
                chapters = json.loads(match.group(0))
                if isinstance(chapters, list) and chapters:
                    return chapters
            except json.JSONDecodeError:
                pass
                
        logger.error(f"无法从大模型回复中提取有效的章节 JSON 列表。\n原始回复：\n{raw_response}")
        return []
