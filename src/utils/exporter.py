import os
import logging
from src.config import OUTPUT_DIR

logger = logging.getLogger("MarkdownExporter")

def export_to_markdown(notebook_title: str, db_results: list):
    """将数据库中的章节记录导出为一个完整的 Markdown 文件"""
    if not db_results:
        logger.warning("没有内容可导出。")
        return

    safe_title = notebook_title.replace(" ", "_").replace("/", "-")
    output_path = os.path.join(OUTPUT_DIR, f"{safe_title}_复习指南.md")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# {notebook_title} - 期末速读复习指南\n")
        f.write("> 本文档由 NotebookLM 自动生成，采用直觉与推演模式，适合考前突击与框架梳理。\n\n")
        f.write("---\n\n")

        for chapter_name, content in db_results:
            f.write(f"<!-- {chapter_name} -->\n")
            f.write(content)
            f.write("\n\n---\n\n")

    logger.info(f"🎉 导出成功！文件已保存至: {os.path.abspath(output_path)}")
