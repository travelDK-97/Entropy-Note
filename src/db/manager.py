import sqlite3
import logging
from datetime import datetime
from src.config import DB_PATH

logger = logging.getLogger("DBManager")

class DatabaseManager:
    """管理 SQLite 数据库，记录 Prompt、Response 以及支持断点续传"""
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        # 记录所有的生成结果
        c.execute('''CREATE TABLE IF NOT EXISTS guides
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      notebook_name TEXT,
                      chapter_name TEXT,
                      prompt_text TEXT,
                      markdown_content TEXT,
                      created_at TEXT)''')
        conn.commit()
        conn.close()

    def has_chapter(self, notebook_name: str, chapter_name: str) -> bool:
        """检查数据库中是否已存在该章节（用于断点续传）"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT id FROM guides WHERE notebook_name=? AND chapter_name=? AND markdown_content IS NOT NULL", 
                 (notebook_name, chapter_name))
        result = c.fetchone()
        conn.close()
        return bool(result)

    def save_chapter(self, notebook_name: str, chapter_name: str, prompt_text: str, content: str):
        """保存生成的 Markdown 内容和 Prompt 到数据库"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        now_str = datetime.now().isoformat() 
        c.execute("INSERT INTO guides (notebook_name, chapter_name, prompt_text, markdown_content, created_at) VALUES (?, ?, ?, ?, ?)",
                  (notebook_name, chapter_name, prompt_text, content, now_str))
        conn.commit()
        conn.close()
        logger.debug(f"已将 {chapter_name} 保存到数据库。")

    def get_all_chapters(self, notebook_name: str) -> list:
        """获取某个笔记本下所有已生成的章节标题和内容"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT chapter_name, markdown_content FROM guides WHERE notebook_name=? ORDER BY id ASC", (notebook_name,))
        results = c.fetchall()
        conn.close()
        return results
