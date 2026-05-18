import json
import logging
import os
import sqlite3
from datetime import datetime

from src.config import DB_PATH

logger = logging.getLogger("DBManager")


def _outline_cache_key(notebook_name: str, outline_mode: str = "core") -> str:
    mode = (outline_mode or "core").strip() or "core"
    return notebook_name if mode == "core" else f"{notebook_name}::outline_mode={mode}"


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
                      section_name TEXT,
                      prompt_text TEXT,
                      markdown_content TEXT,
                      created_at TEXT)''')
                      
        c.execute('''CREATE TABLE IF NOT EXISTS outlines
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      notebook_name TEXT UNIQUE,
                      outline_json TEXT,
                      created_at TEXT)''')

        c.execute('''CREATE TABLE IF NOT EXISTS section_runs
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      notebook_id TEXT,
                      notebook_name TEXT,
                      chapter_name TEXT,
                      section_name TEXT,
                      prompt_text TEXT,
                      prompt_version TEXT,
                      raw_response TEXT,
                      rendered_markdown TEXT,
                      status TEXT,
                      created_at TEXT)''')

        c.execute('''CREATE TABLE IF NOT EXISTS section_blocks
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      run_id INTEGER,
                      notebook_id TEXT,
                      notebook_name TEXT,
                      chapter_name TEXT,
                      section_name TEXT,
                      block_type TEXT,
                      block_order INTEGER,
                      block_title TEXT,
                      content TEXT,
                      payload_json TEXT,
                      created_at TEXT,
                      FOREIGN KEY(run_id) REFERENCES section_runs(id))''')

        c.execute('''CREATE INDEX IF NOT EXISTS idx_section_runs_lookup
                     ON section_runs(notebook_name, chapter_name, section_name, created_at)''')

        c.execute('''CREATE INDEX IF NOT EXISTS idx_section_blocks_lookup
                     ON section_blocks(notebook_name, chapter_name, section_name, block_type, block_order)''')

        c.execute('''CREATE INDEX IF NOT EXISTS idx_guides_lookup
                     ON guides(notebook_name, chapter_name, section_name, created_at)''')

        self._ensure_column_exists(c, "section_blocks", "payload_json", "TEXT")
        conn.commit()
        conn.close()

    def _ensure_column_exists(self, cursor, table_name: str, column_name: str, column_type: str):
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in cursor.fetchall()]
        if column_name not in columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")

    def get_outline(self, notebook_name: str, outline_mode: str = "core") -> list:
        """从数据库中获取已缓存的大纲"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        cache_key = _outline_cache_key(notebook_name, outline_mode)
        c.execute("SELECT outline_json FROM outlines WHERE notebook_name=?", (cache_key,))
        result = c.fetchone()
        if not result and (outline_mode or "core") == "core":
            c.execute("SELECT outline_json FROM outlines WHERE notebook_name=?", (notebook_name,))
            result = c.fetchone()
        conn.close()
        if result:
            import json
            try:
                return json.loads(result[0])
            except json.JSONDecodeError:
                return []
        return []

    def save_outline(self, notebook_name: str, outline_list: list, outline_mode: str = "core"):
        """将大纲缓存到数据库"""
        import json
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        now_str = datetime.now().isoformat()
        outline_json = json.dumps(outline_list, ensure_ascii=False)
        cache_key = _outline_cache_key(notebook_name, outline_mode)
        c.execute("INSERT OR REPLACE INTO outlines (notebook_name, outline_json, created_at) VALUES (?, ?, ?)",
                  (cache_key, outline_json, now_str))
        conn.commit()
        conn.close()
        logger.info(f"💾 大纲已缓存入库 [{outline_mode}]")

    def delete_notebook_data(self, notebook_name: str):
        """仅清理指定笔记本的历史记录，不影响其他笔记本。"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("DELETE FROM outlines WHERE notebook_name=? OR notebook_name LIKE ?", (notebook_name, f"{notebook_name}::outline_mode=%"))
        c.execute("DELETE FROM guides WHERE notebook_name=?", (notebook_name,))
        c.execute("DELETE FROM section_blocks WHERE notebook_name=?", (notebook_name,))
        c.execute("DELETE FROM section_runs WHERE notebook_name=?", (notebook_name,))
        conn.commit()
        conn.close()
        logger.info(f"🧹 已清理笔记本历史数据: {notebook_name}")

    def reset_database(self):
        """彻底删除当前 SQLite 文件，并按最新结构重新初始化。"""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
            logger.info(f"🗑️ 已删除数据库文件: {self.db_path}")
        self._init_db()
        logger.info("🧱 数据库已按当前结构重新初始化。")

    def has_section(self, notebook_name: str, chapter_name: str, section_name: str) -> bool:
        """检查数据库中是否已存在该小节（用于断点续传）"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT id FROM guides WHERE notebook_name=? AND chapter_name=? AND section_name=? AND markdown_content IS NOT NULL", 
                 (notebook_name, chapter_name, section_name))
        result = c.fetchone()
        conn.close()
        return bool(result)

    def save_section(
        self,
        notebook_name: str,
        chapter_name: str,
        section_name: str,
        prompt_text: str,
        content: str,
        *,
        notebook_id: str | None = None,
        prompt_version: str = "legacy_markdown_v1",
        raw_response: str | None = None,
        structured_blocks: list | None = None,
        status: str = "completed",
    ):
        """保存生成结果，并同步写入兼容旧流程与新结构的两套表。"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        now_str = datetime.now().isoformat()

        c.execute("INSERT INTO guides (notebook_name, chapter_name, section_name, prompt_text, markdown_content, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                  (notebook_name, chapter_name, section_name, prompt_text, content, now_str))
        self._insert_section_run_with_blocks(
            c,
            notebook_name=notebook_name,
            chapter_name=chapter_name,
            section_name=section_name,
            prompt_text=prompt_text,
            content=content,
            notebook_id=notebook_id,
            prompt_version=prompt_version,
            raw_response=raw_response,
            structured_blocks=structured_blocks,
            status=status,
            created_at=now_str,
        )

        conn.commit()
        conn.close()
        logger.info(f"💾 成功入库: {section_name} (字数: {len(content)})")

    def save_section_progress(
        self,
        notebook_name: str,
        chapter_name: str,
        section_name: str,
        prompt_text: str,
        content: str,
        *,
        notebook_id: str | None = None,
        prompt_version: str = "legacy_markdown_v1",
        raw_response: str | None = None,
        structured_blocks: list | None = None,
        status: str = "stage_progress",
    ):
        """按阶段保存中间结果，只写结构化运行记录，不占用 guides 完成态。"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        now_str = datetime.now().isoformat()
        self._insert_section_run_with_blocks(
            c,
            notebook_name=notebook_name,
            chapter_name=chapter_name,
            section_name=section_name,
            prompt_text=prompt_text,
            content=content,
            notebook_id=notebook_id,
            prompt_version=prompt_version,
            raw_response=raw_response,
            structured_blocks=structured_blocks,
            status=status,
            created_at=now_str,
        )
        conn.commit()
        conn.close()
        logger.info(f"📝 已保存阶段进度: {section_name} [{status}] (字数: {len(content)})")

    def _insert_section_run_with_blocks(
        self,
        cursor,
        *,
        notebook_name: str,
        chapter_name: str,
        section_name: str,
        prompt_text: str,
        content: str,
        notebook_id: str | None = None,
        prompt_version: str = "legacy_markdown_v1",
        raw_response: str | None = None,
        structured_blocks: list | None = None,
        status: str = "completed",
        created_at: str,
    ) -> int:
        cursor.execute(
            """
            INSERT INTO section_runs
            (notebook_id, notebook_name, chapter_name, section_name, prompt_text, prompt_version, raw_response, rendered_markdown, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                notebook_id,
                notebook_name,
                chapter_name,
                section_name,
                prompt_text,
                prompt_version,
                raw_response or content,
                content,
                status,
                created_at,
            ),
        )
        run_id = cursor.lastrowid

        blocks = structured_blocks or [
            {
                "block_type": "legacy_markdown",
                "block_title": section_name,
                "content": content,
            }
        ]

        for idx, block in enumerate(blocks, start=1):
            payload = block.get("payload")
            payload_json = json.dumps(payload, ensure_ascii=False) if payload is not None else None
            cursor.execute(
                """
                INSERT INTO section_blocks
                (run_id, notebook_id, notebook_name, chapter_name, section_name, block_type, block_order, block_title, content, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    notebook_id,
                    notebook_name,
                    chapter_name,
                    section_name,
                    block.get("block_type", "unknown"),
                    block.get("block_order", idx),
                    block.get("block_title"),
                    block.get("content", ""),
                    payload_json,
                    created_at,
                ),
            )
        return run_id

    def get_all_sections(self, notebook_name: str) -> list:
        """获取某个笔记本下各小节最新一次生成的内容。"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            """
            SELECT g.chapter_name, g.section_name, g.markdown_content
            FROM guides g
            JOIN (
                SELECT MAX(id) AS latest_id
                FROM guides
                WHERE notebook_name=?
                  AND markdown_content IS NOT NULL
                  AND TRIM(markdown_content) != ''
                GROUP BY chapter_name, section_name
            ) latest ON latest.latest_id = g.id
            WHERE g.notebook_name=?
            ORDER BY g.id ASC
            """,
            (notebook_name, notebook_name),
        )
        results = c.fetchall()
        conn.close()
        return results

    def repair_structured_fallbacks(self, notebook_name: str | None = None) -> int:
        """尝试修复因解析失败而以 legacy_markdown 形式落库的结构化响应。"""
        from src.prompts.markdown_prompts import parse_structured_response, PROMPT_VERSION

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        if notebook_name:
            c.execute(
                """
                SELECT id, notebook_id, notebook_name, chapter_name, section_name, raw_response, created_at
                FROM section_runs
                WHERE prompt_version='legacy_markdown_fallback_v1' AND notebook_name=?
                ORDER BY id ASC
                """,
                (notebook_name,),
            )
        else:
            c.execute(
                """
                SELECT id, notebook_id, notebook_name, chapter_name, section_name, raw_response, created_at
                FROM section_runs
                WHERE prompt_version='legacy_markdown_fallback_v1'
                ORDER BY id ASC
                """
            )

        rows = c.fetchall()
        repaired = 0

        for run_id, notebook_id, nb_name, chapter_name, section_name, raw_response, created_at in rows:
            try:
                parsed = parse_structured_response(raw_response or "", section_name)
            except Exception as exc:
                logger.warning(f"修复 fallback 失败，跳过: {nb_name} / {section_name} ({exc})")
                continue

            rendered_markdown = parsed["rendered_markdown"]
            blocks = parsed["blocks"]

            c.execute(
                """
                UPDATE section_runs
                SET prompt_version=?, rendered_markdown=?
                WHERE id=?
                """,
                (PROMPT_VERSION, rendered_markdown, run_id),
            )

            c.execute(
                """
                UPDATE guides
                SET markdown_content=?
                WHERE notebook_name=? AND chapter_name=? AND section_name=? AND created_at=?
                """,
                (rendered_markdown, nb_name, chapter_name, section_name, created_at),
            )

            c.execute("DELETE FROM section_blocks WHERE run_id=?", (run_id,))
            for idx, block in enumerate(blocks, start=1):
                payload = block.get("payload")
                payload_json = json.dumps(payload, ensure_ascii=False) if payload is not None else None
                c.execute(
                    """
                    INSERT INTO section_blocks
                    (run_id, notebook_id, notebook_name, chapter_name, section_name, block_type, block_order, block_title, content, payload_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        notebook_id,
                        nb_name,
                        chapter_name,
                        section_name,
                        block.get("block_type", "unknown"),
                        block.get("block_order", idx),
                        block.get("block_title"),
                        block.get("content", ""),
                        payload_json,
                        created_at,
                    ),
                )
            repaired += 1

        conn.commit()
        conn.close()
        if repaired:
            logger.info(f"已修复 {repaired} 条 legacy fallback 记录。")
        return repaired

    def get_generation_status(self, notebook_name: str, outline: list) -> dict:
        """根据大纲与数据库记录计算整本笔记本/各章节的完成度。"""
        expected_pairs = []
        chapters = {}

        for part in outline or []:
            chapter = part.get("chapter", "未知章节")
            sections = [section for section in part.get("sections", []) if section]
            chapters[chapter] = {
                "total": len(sections),
                "completed": 0,
                "is_complete": False,
                "missing_sections": list(sections),
            }
            for section in sections:
                expected_pairs.append((chapter, section))

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            """
            SELECT DISTINCT chapter_name, section_name
            FROM guides
            WHERE notebook_name=?
              AND markdown_content IS NOT NULL
              AND TRIM(markdown_content) != ''
            """,
            (notebook_name,),
        )
        completed_pairs = set(c.fetchall())
        conn.close()

        missing_pairs = []
        for chapter, section in expected_pairs:
            if (chapter, section) in completed_pairs:
                chapters[chapter]["completed"] += 1
            else:
                missing_pairs.append((chapter, section))

        for chapter, meta in chapters.items():
            all_missing = meta["missing_sections"]
            meta["missing_sections"] = [
                section for section in all_missing if (chapter, section) in missing_pairs
            ]
            meta["is_complete"] = meta["completed"] >= meta["total"] and meta["total"] > 0

        return {
            "total_sections": len(expected_pairs),
            "completed_sections": len(expected_pairs) - len(missing_pairs),
            "is_complete": bool(expected_pairs) and not missing_pairs,
            "missing_sections": missing_pairs,
            "chapters": chapters,
        }

    def list_notebook_titles(self) -> list[str]:
        """列出数据库中已有内容的笔记本标题。"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            """
            SELECT notebook_name FROM guides
            UNION
            SELECT notebook_name FROM section_runs
            ORDER BY notebook_name COLLATE NOCASE ASC
            """
        )
        rows = [row[0] for row in c.fetchall() if row and row[0]]
        conn.close()
        return rows

    def get_latest_section_run(self, notebook_name: str, chapter_name: str, section_name: str) -> dict | None:
        """获取某个小节最近一次生成记录。"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            """
            SELECT id, notebook_id, notebook_name, chapter_name, section_name,
                   prompt_text, prompt_version, raw_response, rendered_markdown,
                   status, created_at
            FROM section_runs
            WHERE notebook_name=? AND chapter_name=? AND section_name=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (notebook_name, chapter_name, section_name),
        )
        row = c.fetchone()
        conn.close()

        if not row:
            return None

        return {
            "id": row[0],
            "notebook_id": row[1],
            "notebook_name": row[2],
            "chapter_name": row[3],
            "section_name": row[4],
            "prompt_text": row[5],
            "prompt_version": row[6],
            "raw_response": row[7],
            "rendered_markdown": row[8],
            "status": row[9],
            "created_at": row[10],
        }

    def get_section_blocks(self, notebook_name: str, chapter_name: str, section_name: str) -> list:
        """读取某个小节最近一次生成对应的结构化块。"""
        from src.prompts.markdown_prompts import enrich_block_for_reading

        latest_run = self.get_latest_section_run(notebook_name, chapter_name, section_name)
        if not latest_run:
            return []

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            """
            SELECT block_type, block_order, block_title, content, payload_json, created_at
            FROM section_blocks
            WHERE run_id=?
            ORDER BY block_order ASC, id ASC
            """,
            (latest_run["id"],),
        )
        rows = c.fetchall()
        conn.close()

        return [
            enrich_block_for_reading(
                {
                "block_type": row[0],
                "block_order": row[1],
                "block_title": row[2],
                "content": row[3],
                "payload": json.loads(row[4]) if row[4] else None,
                "created_at": row[5],
                }
            )
            for row in rows
        ]

    def get_structured_sections(self, notebook_name: str, outline: list | None = None, block_type: str | None = None) -> list:
        """读取整本笔记本最近一次生成的结构化内容，可按 block_type 过滤。"""
        from src.prompts.markdown_prompts import enrich_block_for_reading
        from src.prompts.section_style import get_outline_section_plan

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        query = """
            SELECT sr.chapter_name, sr.section_name, sr.status, sb.block_type, sb.block_order, sb.block_title, sb.content, sb.payload_json
            FROM section_runs sr
            JOIN (
                SELECT MAX(id) AS latest_id
                FROM section_runs
                WHERE notebook_name=?
                GROUP BY chapter_name, section_name
            ) latest ON latest.latest_id = sr.id
            JOIN section_blocks sb ON sb.run_id = sr.id
            WHERE sr.notebook_name=?
        """
        params = [notebook_name, notebook_name]
        if block_type:
            query += " AND sb.block_type=?"
            params.append(block_type)
        query += " ORDER BY sr.id ASC, sb.block_order ASC, sb.id ASC"

        c.execute(query, tuple(params))
        rows = c.fetchall()
        conn.close()

        grouped = {}
        for chapter_name, section_name, run_status, cur_block_type, block_order, block_title, content, payload_json in rows:
            key = (chapter_name, section_name)
            if key not in grouped:
                grouped[key] = {
                    "chapter_name": chapter_name,
                    "section_name": section_name,
                    "run_status": run_status,
                    "blocks": [],
                    "section_plan": get_outline_section_plan(outline, chapter_name, section_name) if outline else None,
                }
            grouped[key]["blocks"].append(
                enrich_block_for_reading(
                    {
                    "block_type": cur_block_type,
                    "block_order": block_order,
                    "block_title": block_title,
                    "content": content,
                    "payload": json.loads(payload_json) if payload_json else None,
                    }
                )
            )

        if not outline:
            return list(grouped.values())

        ordered_sections = []
        for part in outline:
            chapter = part.get("chapter", "未知章节")
            for section in part.get("sections", []):
                record = grouped.get((chapter, section))
                if record:
                    ordered_sections.append(record)
        return ordered_sections
