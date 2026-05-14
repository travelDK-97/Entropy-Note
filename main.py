import sys
import asyncio
import logging
from src.core.client import SafeNotebookClient
from src.db.manager import DatabaseManager
from src.prompts.markdown_prompts import get_markdown_prompt
from src.utils.exporter import export_to_markdown

# 基础日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("Main")

async def select_notebook(client: SafeNotebookClient):
    """交互式选择笔记本"""
    logger.info("正在获取您的笔记本列表...")
    notebooks = await client.list_notebooks()
    
    if not notebooks:
        logger.warning("未找到任何笔记本，请先在网页端创建。")
        return None

    print("\n[发现已有笔记本]")
    for i, nb in enumerate(notebooks, 1):
        print(f"{i}. {nb.title} (ID: {nb.id})")
        
    while True:
        try:
            choice = input("\n👉 请输入序号选择要处理的笔记本: ").strip()
            choice = int(choice)
            if 1 <= choice <= len(notebooks):
                selected = notebooks[choice-1]
                logger.info(f"已选择笔记本: {selected.title}")
                return selected
            else:
                print("无效序号。")
        except ValueError:
            print("请输入有效数字。")

async def main():
    logger.info("=== NotebookLM 自动化学习流水线 (安全重构版) ===")
    
    # 初始化核心组件
    db = DatabaseManager()
    client = SafeNotebookClient()
    
    if not await client.connect():
        sys.exit(1)

    try:
        # 1. 选择笔记本
        notebook = await select_notebook(client)
        if not notebook:
            return
            
        nb_id = notebook.id
        nb_title = notebook.title

        # 2. 提取大纲
        chapters = await client.extract_chapters(nb_id)
        if not chapters:
            logger.error("大纲提取失败，流程终止。")
            return
            
        logger.info(f"成功提取 {len(chapters)} 个章节，准备开始生成...")

        # 3. 逐个章节生成 (断点续传 + 安全防封停)
        for chapter in chapters:
            if db.has_chapter(nb_title, chapter):
                logger.info(f"⏭️ 跳过已存在章节 (断点续传): {chapter}")
                continue

            logger.info(f"正在生成: {chapter} ...")
            prompt = get_markdown_prompt(chapter)
            
            # 使用带有安全延时机制的请求方法
            content = await client.ask_with_retry(nb_id, prompt)
            
            if content:
                db.save_chapter(nb_title, chapter, prompt, content)
            else:
                logger.error(f"❌ 章节 {chapter} 生成失败。")

        # 4. 组装导出
        logger.info("所有章节生成完毕，开始导出 Markdown 文件...")
        results = db.get_all_chapters(nb_title)
        export_to_markdown(nb_title, results)

    finally:
        await client.close()
        logger.info("已安全关闭连接。")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
