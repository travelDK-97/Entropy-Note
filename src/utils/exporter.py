import json
import os
import logging
import re
import shutil
from collections import OrderedDict

from src.config import OUTPUT_DIR
from src.utils.mermaid import format_obsidian_mermaid_code, sanitize_mermaid_code

logger = logging.getLogger("MarkdownExporter")
PAGE_BREAK_MARKER = '<div style="page-break-after: always;"></div>\n\n<!-- pagebreak -->'
FAST_GUIDE_NAME = "快速学习指南"
FAST_GUIDE_CHAPTER_DIR = f"{FAST_GUIDE_NAME}_分章"
CHEATSHEET_NAME = "章节速查表"
CHEATSHEET_CHAPTER_DIR = f"{CHEATSHEET_NAME}_分章"
QUALITY_REPORT_CHAPTER_DIR = "质量报告_分章"
CHEATSHEET_GROUP_TITLES = {
    "definition": "定义速查",
    "theorem": "定理速查",
    "formula": "公式速查",
    "proof_or_derivation": "推导速查",
    "pitfall": "易错点速查",
}
CHEATSHEET_BLOCK_ORDER = [
    "definition",
    "theorem",
    "formula",
    "proof_or_derivation",
    "pitfall",
]


def _safe_title(notebook_title: str) -> str:
    title = notebook_title.strip().replace(" ", "_").replace("/", "-")
    title = re.sub(r'[<>:"/\\|?*]', "_", title)
    return title or "untitled_notebook"


def _group_plain_sections(db_results: list) -> list[dict]:
    grouped = OrderedDict()
    for chapter_name, section_name, content in db_results:
        grouped.setdefault(chapter_name, [])
        grouped[chapter_name].append(
            {
                "section_name": section_name,
                "content": content,
            }
        )
    return [
        {
            "chapter_name": chapter_name,
            "sections": sections,
        }
        for chapter_name, sections in grouped.items()
    ]


def _group_structured_by_chapter(structured_sections: list) -> list[dict]:
    grouped = OrderedDict()
    for section in structured_sections:
        chapter_name = section["chapter_name"]
        grouped.setdefault(chapter_name, [])
        grouped[chapter_name].append(section)
    return [
        {
            "chapter_name": chapter_name,
            "sections": sections,
        }
        for chapter_name, sections in grouped.items()
    ]


def _build_structured_markdown_lookup(structured_sections: list | None) -> dict[tuple[str, str], str]:
    from src.prompts.markdown_prompts import render_markdown_from_blocks

    lookup: dict[tuple[str, str], str] = {}
    for section in structured_sections or []:
        chapter_name = section["chapter_name"]
        section_name = section["section_name"]
        blocks = [
            block
            for block in (section.get("blocks", []) or [])
            if block.get("block_type") != "renderable_visual"
        ]
        rendered = render_markdown_from_blocks(section_name, blocks)
        if rendered:
            lookup[(chapter_name, section_name)] = rendered
    return lookup


def _build_fast_guide_rows(db_results: list, structured_sections: list | None) -> list[tuple[str, str, str]]:
    structured_lookup = _build_structured_markdown_lookup(structured_sections or [])
    if structured_sections and structured_lookup:
        rows = []
        for section in structured_sections:
            key = (section["chapter_name"], section["section_name"])
            rendered = structured_lookup.get(key)
            if rendered:
                rows.append((section["chapter_name"], section["section_name"], rendered))
        if rows:
            return rows
    return db_results


def _chapter_bundle_dir(notebook_title: str, bundle_name: str) -> str:
    safe_title = _safe_title(notebook_title)
    path = os.path.join(OUTPUT_DIR, safe_title, bundle_name)
    os.makedirs(path, exist_ok=True)
    return path


def _notebook_root_dir(notebook_title: str) -> str:
    safe_title = _safe_title(notebook_title)
    path = os.path.join(OUTPUT_DIR, safe_title)
    os.makedirs(path, exist_ok=True)
    return path


def _notebook_file_path(notebook_title: str, file_name: str) -> str:
    return os.path.join(_notebook_root_dir(notebook_title), file_name)


CHINESE_DIGITS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _parse_chinese_number(text: str) -> int | None:
    if not text:
        return None
    if text == "十":
        return 10
    if "十" in text:
        left, _, right = text.partition("十")
        tens = CHINESE_DIGITS.get(left, 1) if left else 1
        ones = CHINESE_DIGITS.get(right, 0) if right else 0
        return tens * 10 + ones
    if text in CHINESE_DIGITS:
        return CHINESE_DIGITS[text]
    return None


def _infer_chapter_order(chapter_name: str) -> int | None:
    text = (chapter_name or "").strip()
    digit_match = re.match(r"^(\d+)", text)
    if digit_match:
        return int(digit_match.group(1))
    chinese_match = re.match(r"^第([零一二两三四五六七八九十]+)章", text)
    if chinese_match:
        return _parse_chinese_number(chinese_match.group(1))
    return None


def _chapter_file_name(order: int, chapter_name: str) -> str:
    stable_order = _infer_chapter_order(chapter_name) or order
    safe_chapter = _safe_title(chapter_name)
    return f"{stable_order:02d}_{safe_chapter}.md"


def _remove_stale_chapter_files(bundle_dir: str, chapter_name: str, keep_file_name: str):
    suffix = "_" + _safe_title(chapter_name) + ".md"
    for file_name in os.listdir(bundle_dir):
        if file_name == keep_file_name:
            continue
        if file_name.endswith(suffix):
            os.remove(os.path.join(bundle_dir, file_name))


def _cleanup_legacy_guide_exports(notebook_title: str):
    for legacy_name in ("复习指南",):
        legacy_file = _notebook_file_path(notebook_title, f"{legacy_name}.md")
        legacy_dir = os.path.join(_notebook_root_dir(notebook_title), f"{legacy_name}_分章")
        if os.path.exists(legacy_file):
            os.remove(legacy_file)
        if os.path.exists(legacy_dir):
            shutil.rmtree(legacy_dir)


def _build_renderable_visual_lookup(structured_sections: list) -> dict[tuple[str, str], list[dict]]:
    lookup: dict[tuple[str, str], list[dict]] = {}
    for section in structured_sections or []:
        chapter_name = section["chapter_name"]
        section_name = section["section_name"]
        tasks = _build_renderable_visual_tasks(chapter_name, section_name, section.get("blocks", []))
        if tasks:
            lookup[(chapter_name, section_name)] = tasks
    return lookup


def _write_renderable_visual_summary(f, tasks: list[dict]):
    if not tasks:
        return

    f.write("### 相关图示\n\n")
    for task in tasks:
        f.write(f"#### {task['title']}\n\n")
        if task.get("render_goal"):
            f.write(f"- 图示目标: {task['render_goal']}\n")
        if task.get("caption"):
            f.write(f"- 图注: {task['caption']}\n")
        if task.get("notes"):
            for note in task["notes"]:
                f.write(f"- 说明: {note}\n")
        f.write(f"- 渲染类型: {task['visual_kind']}\n\n")
        if task.get("render_format") == "svg" and task.get("svg_code"):
            _write_svg_block(f, task["svg_code"])
        else:
            _write_mermaid_block(f, task["mermaid_code"])


def _write_chapter_index(bundle_dir: str, title: str, intro: str, chapters: list[dict]):
    index_path = os.path.join(bundle_dir, "00_目录.md")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n")
        f.write(f"{intro}\n\n")
        f.write("## 章节目录\n\n")
        for idx, chapter in enumerate(chapters, start=1):
            file_name = _chapter_file_name(idx, chapter["chapter_name"])
            section_count = len(chapter.get("sections", []))
            f.write(f"- [{chapter['chapter_name']}]({file_name}) ({section_count} 节)\n")
    return index_path


def _compact_text(text: str, *, limit: int = 140) -> str:
    compact = re.sub(r"\s+", " ", (text or "").strip())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _ensure_obsidian_mermaid_layout(mermaid_code: str) -> str:
    return format_obsidian_mermaid_code(mermaid_code)


def _write_mermaid_block(f, mermaid_code: str):
    formatted_code = _ensure_obsidian_mermaid_layout(mermaid_code)
    if not formatted_code:
        return
    f.write("```mermaid\n")
    f.write(f"{formatted_code}\n")
    f.write("```\n\n")


def _write_svg_block(f, svg_code: str):
    if not (svg_code or "").strip():
        return
    f.write(f"{svg_code.strip()}\n\n")


def _collect_section_cheatsheet_items(blocks: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {key: [] for key in CHEATSHEET_BLOCK_ORDER}
    for block in blocks:
        block_type = block.get("block_type")
        if block_type not in grouped:
            continue

        payload = block.get("payload") or {}
        content = str(block.get("content", "")).strip()
        item = None

        if block_type == "definition":
            concept = str(payload.get("concept", "")).strip() or str(block.get("block_title", "")).strip() or "未命名概念"
            summary = str(payload.get("concise_definition", "")).strip() or _compact_text(content)
            extras = [f"要点: {'；'.join(payload.get('key_points', [])[:3])}"] if payload.get("key_points") else []
            item = {"label": concept, "summary": summary, "extras": extras}

        elif block_type == "theorem":
            theorem_name = str(payload.get("theorem_name", "")).strip() or str(block.get("block_title", "")).strip() or "未命名定理"
            summary = str(payload.get("conclusion", "")).strip() or _compact_text(content)
            extras = []
            if payload.get("assumptions"):
                extras.append(f"条件: {'；'.join(payload.get('assumptions', [])[:3])}")
            if payload.get("significance"):
                extras.append(f"意义: {_compact_text(str(payload.get('significance', '')).strip(), limit=80)}")
            item = {"label": theorem_name, "summary": summary, "extras": extras}

        elif block_type == "formula":
            formula_latex = str(payload.get("formula_latex", "")).strip()
            label = formula_latex or str(block.get("block_title", "")).strip() or "关键公式"
            summary = str(payload.get("usage", "")).strip() or _compact_text(content)
            extras = []
            if payload.get("variables"):
                variables = payload.get("variables", [])[:4]
                extras.append("变量: " + "；".join(f"`{item['symbol']}`={item['meaning']}" for item in variables))
            if payload.get("conditions"):
                extras.append(f"条件: {'；'.join(payload.get('conditions', [])[:3])}")
            item = {"label": label, "summary": summary, "extras": extras}

        elif block_type == "proof_or_derivation":
            label = str(block.get("block_title", "")).strip() or "严谨推导补充"
            item = {"label": label, "summary": _compact_text(content, limit=180), "extras": []}

        elif block_type == "pitfall":
            label = str(block.get("block_title", "")).strip() or "易错点"
            item = {"label": label, "summary": _compact_text(content, limit=180), "extras": []}

        if item and item.get("summary"):
            grouped[block_type].append(item)

    return {key: value for key, value in grouped.items() if value}


def _write_cheatsheet_items(f, groups: dict[str, list[dict]]):
    for block_type in CHEATSHEET_BLOCK_ORDER:
        items = groups.get(block_type, [])
        if not items:
            continue
        f.write(f"### {CHEATSHEET_GROUP_TITLES[block_type]}\n\n")
        for item in items:
            f.write(f"- {item['label']}: {item['summary']}\n")
            for extra in item.get("extras", []):
                f.write(f"  - {extra}\n")
        f.write("\n")


def export_cheatsheets(notebook_title: str, structured_sections: list, is_final: bool = False):
    if not structured_sections:
        logger.warning("没有结构化内容可用于导出章节速查表。")
        return

    output_path = _notebook_file_path(notebook_title, f"{CHEATSHEET_NAME}.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# {notebook_title} - {CHEATSHEET_NAME}\n")
        if not is_final:
            f.write("> 🔄 该文件会随着结构化内容生成实时更新，适合全局搜索定义、定理、公式与易错点。\n\n")
        else:
            f.write("> ✅ 该文件按章汇总了定义、定理、公式、推导与易错点，适合快速检索。\n\n")
        f.write("---\n\n")

        current_chapter = None
        for section in structured_sections:
            chapter_name = section["chapter_name"]
            section_name = section["section_name"]
            groups = _collect_section_cheatsheet_items(section.get("blocks", []))
            if not groups:
                continue

            if chapter_name != current_chapter:
                if current_chapter is not None:
                    f.write(f"{PAGE_BREAK_MARKER}\n\n")
                f.write(f"# {chapter_name}\n\n")
                current_chapter = chapter_name

            f.write(f"## {section_name}\n\n")
            _write_cheatsheet_items(f, groups)
            f.write("---\n\n")

    logger.info(f"📘 {CHEATSHEET_NAME}已导出至: {os.path.abspath(output_path)}")


def export_cheatsheets_by_chapter(notebook_title: str, structured_sections: list, is_final: bool = False):
    if not structured_sections:
        logger.warning("没有结构化内容可按章导出章节速查表。")
        return

    chapters = _group_structured_by_chapter(structured_sections)
    bundle_dir = _chapter_bundle_dir(notebook_title, CHEATSHEET_CHAPTER_DIR)
    intro = "按章拆分的速查表入口，适合快速检索本章的定义、定理、公式、推导与易错点。"
    index_path = _write_chapter_index(bundle_dir, f"{notebook_title} - {CHEATSHEET_NAME}（分章）", intro, chapters)

    exported_any = False
    for idx, chapter in enumerate(chapters, start=1):
        chapter_name = chapter["chapter_name"]
        output_path = os.path.join(bundle_dir, _chapter_file_name(idx, chapter_name))
        section_written = 0
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"# {notebook_title} - {chapter_name}（{CHEATSHEET_NAME}）\n\n")
            if not is_final:
                f.write("> 🔄 本章速查表仍可能继续更新。\n\n")
            else:
                f.write("> ✅ 本章速查表已整理完毕，可用于快速定位公式、定理、定义和易错点。\n\n")

            for section in chapter["sections"]:
                section_name = section["section_name"]
                groups = _collect_section_cheatsheet_items(section.get("blocks", []))
                if not groups:
                    continue
                f.write(f"## {section_name}\n\n")
                _write_cheatsheet_items(f, groups)
                f.write("---\n\n")
                section_written += 1
                exported_any = True

        if section_written == 0:
            os.remove(output_path)

    if not exported_any:
        logger.warning("当前还没有足够的结构化块可用于生成分章速查表。")
        return

    logger.info(f"📘 分章{CHEATSHEET_NAME}已导出至: {os.path.abspath(bundle_dir)} (目录: {os.path.basename(index_path)})")


def _collect_manual_mermaid_review_items(sections: list[dict]) -> list[dict]:
    review_items = []
    for section in sections:
        mermaid_issues = [
            issue["message"]
            for issue in section.get("issues", [])
            if "Mermaid" in issue.get("message", "") or "可渲染图示" in issue.get("message", "")
        ]
        if not mermaid_issues:
            continue
        review_items.append(
            {
                "chapter_name": section["chapter_name"],
                "section_name": section["section_name"],
                "messages": mermaid_issues,
            }
        )
    return review_items


def export_notebook_index(
    notebook_title: str,
    plain_chapters: list[dict],
    structured_chapters: list[dict] | None = None,
    quality_report: dict | None = None,
    publish_gate: dict | None = None,
    *,
    include_comic_exports: bool = True,
    include_image_exports: bool = True,
    include_renderable_visuals: bool = True,
    include_cheatsheets: bool = True,
):
    """导出笔记本级总索引首页，统一链接总文件、分章目录与质量报告。"""
    safe_title = _safe_title(notebook_title)
    notebook_dir = _notebook_root_dir(notebook_title)
    index_path = os.path.join(notebook_dir, "00_总索引.md")

    structured_chapters = structured_chapters or []
    structured_lookup = {chapter["chapter_name"]: chapter for chapter in structured_chapters}
    quality_summary = (quality_report or {}).get("summary", {})

    with open(index_path, "w", encoding="utf-8") as f:
        f.write(f"# {notebook_title} - 总索引\n\n")
        f.write("这是当前笔记本的阅读入口页。建议优先从分章文件开始阅读，总文件用于全局搜索与统一导出。\n\n")

        f.write("## 总文件\n\n")
        f.write(f"- [{FAST_GUIDE_NAME}]({FAST_GUIDE_NAME}.md)\n")
        if include_cheatsheets:
            f.write(f"- [{CHEATSHEET_NAME}]({CHEATSHEET_NAME}.md)\n")
        f.write("- [结构化资料](结构化资料.md)\n")
        if include_comic_exports:
            f.write("- [漫画提示词](漫画提示词.md)\n")
        if include_image_exports:
            f.write("- [图像任务](图像任务.md)\n")
            f.write("- [图像任务 JSONL](图像任务.jsonl)\n")
        if include_renderable_visuals:
            f.write("- [可渲染图示](可渲染图示.md)\n")
        f.write("- [质量报告](质量报告.md)\n")
        f.write(f"- [质量报告（分章）]({QUALITY_REPORT_CHAPTER_DIR}/00_目录.md)\n")
        if publish_gate:
            f.write("- [发布闸门](发布闸门.md)\n")
        f.write("\n")

        f.write("## 分章目录\n\n")
        f.write(f"- [{FAST_GUIDE_NAME}（分章）]({FAST_GUIDE_CHAPTER_DIR}/00_目录.md)\n")
        if include_cheatsheets:
            f.write(f"- [{CHEATSHEET_NAME}（分章）]({CHEATSHEET_CHAPTER_DIR}/00_目录.md)\n")
        f.write("- [结构化资料（分章）](结构化资料_分章/00_目录.md)\n")
        if include_comic_exports:
            f.write("- [漫画提示词（分章）](漫画提示词_分章/00_目录.md)\n")
        if include_image_exports:
            f.write("- [图像任务（分章）](图像任务_分章/00_目录.md)\n")
        if include_renderable_visuals:
            f.write("- [可渲染图示（分章）](可渲染图示_分章/00_目录.md)\n")
        f.write(f"- [质量报告（分章）]({QUALITY_REPORT_CHAPTER_DIR}/00_目录.md)\n")
        f.write("\n")

        if quality_report:
            f.write("## 质量摘要\n\n")
            f.write(f"- 小节总数: {quality_summary.get('section_count', 0)}\n")
            f.write(f"- 通过数: {quality_summary.get('passed_count', 0)}\n")
            f.write(f"- 错误数: {quality_summary.get('error_count', 0)}\n")
            f.write(f"- 警告数: {quality_summary.get('warning_count', 0)}\n\n")
            f.write(f"- 自动修复数: {quality_summary.get('auto_fix_count', 0)}\n\n")
            f.write(f"- 平均分: {quality_summary.get('average_score', 0)}\n\n")
            f.write(f"- 建议回看节级判定数: {quality_summary.get('plan_review_count', 0)}\n\n")

        if publish_gate:
            f.write("## 发布状态\n\n")
            f.write(f"- 是否允许生成正式版: {'是' if publish_gate.get('passed') else '否'}\n")
            for reason in publish_gate.get("reasons", []):
                f.write(f"- 原因: {reason}\n")
            f.write("\n")

        f.write("## 章节导航\n\n")
        for idx, chapter in enumerate(plain_chapters, start=1):
            chapter_name = chapter["chapter_name"]
            review_file = f"{FAST_GUIDE_CHAPTER_DIR}/{_chapter_file_name(idx, chapter_name)}"
            cheatsheet_file = f"{CHEATSHEET_CHAPTER_DIR}/{_chapter_file_name(idx, chapter_name)}"
            structured_file = f"结构化资料_分章/{_chapter_file_name(idx, chapter_name)}"
            comic_file = f"漫画提示词_分章/{_chapter_file_name(idx, chapter_name)}"
            section_count = len(chapter.get("sections", []))

            f.write(f"### {chapter_name}\n\n")
            f.write(f"- 节数: {section_count}\n")
            f.write(f"- [阅读本章{FAST_GUIDE_NAME}]({review_file})\n")
            f.write(f"- [查看本章质量报告]({QUALITY_REPORT_CHAPTER_DIR}/{_chapter_file_name(idx, chapter_name)})\n")
            if chapter_name in structured_lookup:
                if include_cheatsheets:
                    f.write(f"- [查看本章{CHEATSHEET_NAME}]({cheatsheet_file})\n")
                f.write(f"- [阅读本章结构化资料]({structured_file})\n")
                if include_comic_exports:
                    f.write(f"- [查看本章漫画提示词]({comic_file})\n")
                if include_image_exports:
                    f.write(f"- [查看本章图像任务](图像任务_分章/{_chapter_file_name(idx, chapter_name)})\n")
                if include_renderable_visuals:
                    f.write(f"- [查看本章可渲染图示](可渲染图示_分章/{_chapter_file_name(idx, chapter_name)})\n")
            f.write("\n")

    logger.info(f"🗂️ 总索引首页已导出至: {os.path.abspath(index_path)}")
    return index_path


def _build_image_task_payload(chapter_name: str, section_name: str, blocks: list[dict]) -> list[dict]:
    tasks = []
    background_text = "\n".join(
        str(block.get("content", "")).strip()
        for block in blocks
        if block.get("block_type") == "background_storyline" and str(block.get("content", "")).strip()
    ).strip()

    explicit_tasks = [block for block in blocks if block.get("block_type") == "image_generation_task"]
    for order, block in enumerate(explicit_tasks, start=1):
        payload = block.get("payload") or {}
        prompt = str(payload.get("prompt") or block.get("content", "")).strip()
        if not prompt:
            continue
        tasks.append(
            {
                "task_kind": "image_generation",
                "chapter_name": chapter_name,
                "section_name": section_name,
                "title": str(block.get("block_title") or "图像生成任务").strip(),
                "image_kind": str(payload.get("image_kind", "")).strip() or "concept_illustration",
                "tool_targets": payload.get("tool_targets") or ["lovart", "gpt_image_2", "banana_pro"],
                "prompt": prompt,
                "negative_prompt": str(payload.get("negative_prompt", "")).strip(),
                "focus_points": payload.get("focus_points") or [],
                "source_basis": str(payload.get("source_basis", "")).strip(),
                "background_text": background_text,
                "task_order": order,
            }
        )

    if tasks:
        return tasks

    intuition_blocks = [block for block in blocks if block.get("block_type") == "intuition_plain_language"]
    if not intuition_blocks:
        return []

    intuition_text = "\n".join(
        str(block.get("content", "")).strip() for block in intuition_blocks if str(block.get("content", "")).strip()
    ).strip()
    first_payload = next((block.get("payload") for block in intuition_blocks if block.get("payload")), None)
    if first_payload:
        prompt = _build_comic_prompt_from_payload(chapter_name, section_name, first_payload, background_text)
        focus_points = []
        if first_payload.get("metaphor"):
            focus_points.append(first_payload["metaphor"])
        if first_payload.get("visual_scene"):
            focus_points.append(first_payload["visual_scene"])
        source_basis = str(first_payload.get("plain_explanation", "")).strip()
    else:
        prompt = _build_comic_prompt(chapter_name, section_name, intuition_text, background_text)
        focus_points = []
        source_basis = intuition_text

    if not prompt:
        return []

    return [
        {
            "task_kind": "image_generation",
            "chapter_name": chapter_name,
            "section_name": section_name,
            "title": "由大白话自动派生的图像任务",
            "image_kind": "teaching_illustration",
            "tool_targets": ["lovart", "gpt_image_2", "banana_pro"],
            "prompt": prompt,
            "negative_prompt": "避免与公式含义矛盾，避免夸张二次元风，避免装饰性过强",
            "focus_points": focus_points,
            "source_basis": source_basis,
            "background_text": background_text,
            "task_order": 1,
        }
    ]


def _build_renderable_visual_tasks(chapter_name: str, section_name: str, blocks: list[dict]) -> list[dict]:
    tasks = []
    for order, block in enumerate([b for b in blocks if b.get("block_type") == "renderable_visual"], start=1):
        payload = block.get("payload") or {}
        render_format = str(payload.get("render_format", "")).strip().lower()
        svg_code = str(payload.get("svg_code", "")).strip()
        mermaid_code = str(payload.get("mermaid_code", "")).strip()
        content = str(block.get("content", "")).strip()
        if not render_format:
            render_format = "svg" if svg_code else ("mermaid" if mermaid_code else "")
        if render_format != "svg" and not mermaid_code and "```mermaid" in content:
            mermaid_match = re.search(r"```mermaid\s*([\s\S]*?)```", content, re.IGNORECASE)
            if mermaid_match:
                mermaid_code = mermaid_match.group(1).strip()
        if render_format == "svg":
            if not svg_code:
                svg_match = re.search(r"(<svg[\s\S]*?</svg>)", content, re.IGNORECASE)
                if svg_match:
                    svg_code = svg_match.group(1).strip()
            if not svg_code:
                continue
        else:
            mermaid_code = sanitize_mermaid_code(mermaid_code or content)
            if not mermaid_code:
                continue

        tasks.append(
            {
                "task_kind": "renderable_visual",
                "chapter_name": chapter_name,
                "section_name": section_name,
                "title": str(payload.get("title") or block.get("block_title") or "可渲染图示").strip(),
                "visual_kind": str(payload.get("visual_kind", "")).strip() or ("svg_diagram" if render_format == "svg" else "mermaid_flowchart"),
                "render_format": render_format or "mermaid",
                "ratio_hint": str(payload.get("ratio_hint", "")).strip(),
                "render_goal": str(payload.get("render_goal", "")).strip(),
                "caption": str(payload.get("caption", "")).strip(),
                "notes": payload.get("notes") or [],
                "svg_code": svg_code,
                "mermaid_code": mermaid_code,
                "task_order": order,
            }
        )
    return tasks


def _collect_visual_exports(structured_sections: list) -> tuple[list[dict], list[dict]]:
    image_tasks = []
    renderable_tasks = []
    for section in structured_sections:
        chapter_name = section["chapter_name"]
        section_name = section["section_name"]
        blocks = section.get("blocks", [])
        image_tasks.extend(_build_image_task_payload(chapter_name, section_name, blocks))
        renderable_tasks.extend(_build_renderable_visual_tasks(chapter_name, section_name, blocks))
    return image_tasks, renderable_tasks

def export_to_markdown(
    notebook_title: str,
    db_results: list,
    is_final: bool = False,
    structured_sections: list | None = None,
):
    """将数据库中的章节记录导出为一个完整的 Markdown 文件。
    支持在每节生成后实时覆盖保存。"""
    guide_rows = _build_fast_guide_rows(db_results, structured_sections)
    if not guide_rows:
        logger.warning("没有内容可导出。")
        return

    _cleanup_legacy_guide_exports(notebook_title)
    output_path = _notebook_file_path(notebook_title, f"{FAST_GUIDE_NAME}.md")
    visual_lookup = _build_renderable_visual_lookup(structured_sections or [])

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# {notebook_title} - {FAST_GUIDE_NAME}\n")
        if not is_final:
            f.write("> 🔄 **本文档正在由流水线实时生成中，请刷新查看最新进度...**\n\n")
        else:
            f.write("> ✅ 本文档由 NotebookLM 自动生成完毕，采用直觉与推演模式，适合快速建立知识框架与系统学习。\n\n")
        f.write("---\n\n")

        current_chapter = None
        
        for row in guide_rows:
            chapter_name, section_name, content = row
            
            # 只有当章节变化时，才打印一级标题
            if chapter_name != current_chapter:
                if current_chapter is not None:
                    f.write(f"{PAGE_BREAK_MARKER}\n\n")
                f.write(f"\n# {chapter_name}\n\n")
                current_chapter = chapter_name
                
            # 清理可能被大模型过度添加的一级或二级标题，避免重复
            clean_content = content
            # 如果大模型开头自带了 ## 节名，我们就不做特殊处理；如果没带，我们在生成提示词里已经要求它带上了。
            
            f.write(f"{clean_content}\n\n")
            _write_renderable_visual_summary(f, visual_lookup.get((chapter_name, section_name), []))
            f.write("---\n\n")

    if not is_final:
        logger.info(f"🔄 进度已实时更新至: {output_path}")
    else:
        logger.info(f"🎉 导出成功！文件已保存至: {os.path.abspath(output_path)}")


def export_to_markdown_by_chapter(
    notebook_title: str,
    db_results: list,
    is_final: bool = False,
    structured_sections: list | None = None,
):
    """按章拆分导出快速学习指南，便于控制单文件体积。"""
    guide_rows = _build_fast_guide_rows(db_results, structured_sections)
    if not guide_rows:
        logger.warning("没有内容可按章导出。")
        return

    _cleanup_legacy_guide_exports(notebook_title)
    chapters = _group_plain_sections(guide_rows)
    bundle_dir = _chapter_bundle_dir(notebook_title, FAST_GUIDE_CHAPTER_DIR)
    visual_lookup = _build_renderable_visual_lookup(structured_sections or [])
    intro = "按章节拆分的快速学习指南入口。生成仍以小节为最小单元，但阅读和检索以章为单位。"
    index_path = _write_chapter_index(bundle_dir, f"{notebook_title} - {FAST_GUIDE_NAME}（分章）", intro, chapters)

    for idx, chapter in enumerate(chapters, start=1):
        chapter_name = chapter["chapter_name"]
        file_name = _chapter_file_name(idx, chapter_name)
        _remove_stale_chapter_files(bundle_dir, chapter_name, file_name)
        output_path = os.path.join(bundle_dir, file_name)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"# {notebook_title} - {chapter_name}\n\n")
            if not is_final:
                f.write("> 🔄 本章内容仍可能继续更新。\n\n")
            else:
                f.write("> ✅ 本章已完成导出，可单独阅读与打印。\n\n")
            for section in chapter["sections"]:
                f.write(f"{section['content']}\n\n")
                _write_renderable_visual_summary(
                    f,
                    visual_lookup.get((chapter_name, section["section_name"]), []),
                )
                f.write("---\n\n")

    logger.info(f"📚 分章{FAST_GUIDE_NAME}已导出至: {os.path.abspath(bundle_dir)} (目录: {os.path.basename(index_path)})")


def export_structured_blocks(notebook_title: str, structured_sections: list, is_final: bool = False):
    """按结构化 block 导出一份更适合后续加工的 Markdown 资料。"""
    if not structured_sections:
        logger.warning("没有结构化内容可导出。")
        return

    output_path = _notebook_file_path(notebook_title, "结构化资料.md")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# {notebook_title} - 结构化学习资料\n")
        if not is_final:
            f.write("> 🔄 该文件会随着流水线生成实时更新。\n\n")
        else:
            f.write("> ✅ 该文件已按结构化内容块整理完毕，可用于二次加工与知识卡片制作。\n\n")
        f.write("---\n\n")

        current_chapter = None
        for section in structured_sections:
            chapter_name = section["chapter_name"]
            section_name = section["section_name"]
            blocks = section.get("blocks", [])

            if chapter_name != current_chapter:
                if current_chapter is not None:
                    f.write(f"{PAGE_BREAK_MARKER}\n\n")
                f.write(f"# {chapter_name}\n\n")
                current_chapter = chapter_name

            f.write(f"## {section_name}\n\n")
            for block in blocks:
                title = (block.get("block_title") or block.get("block_type") or "未命名内容").strip()
                content = str(block.get("content", "")).strip()
                payload = block.get("payload") or {}
                if not content:
                    continue
                f.write(f"### {title}\n")
                if block.get("block_type") == "renderable_visual":
                    if payload.get("render_format"):
                        f.write(f"- 渲染格式: {payload['render_format']}\n")
                    if payload.get("visual_kind"):
                        f.write(f"- 图示类型: {payload['visual_kind']}\n")
                    if payload.get("ratio_hint"):
                        f.write(f"- 建议比例: {payload['ratio_hint']}\n")
                    if payload.get("title"):
                        f.write(f"- 图示标题: {payload['title']}\n")
                    if payload.get("render_goal"):
                        f.write(f"- 图示目标: {payload['render_goal']}\n")
                    if payload.get("caption"):
                        f.write(f"- 图注: {payload['caption']}\n")
                    for item in payload.get("notes", []):
                        f.write(f"- 说明: {item}\n")
                    if payload:
                        f.write("\n")
                    svg_code = str(payload.get("svg_code", "")).strip()
                    mermaid_code = str(payload.get("mermaid_code", "")).strip()
                    if svg_code:
                        _write_svg_block(f, svg_code)
                    elif mermaid_code:
                        _write_mermaid_block(f, mermaid_code)
                    elif content:
                        f.write(f"{content}\n\n")
                    continue

                f.write(f"{content}\n\n")
            f.write("---\n\n")

    logger.info(f"🧱 结构化资料已导出至: {os.path.abspath(output_path)}")


def export_structured_blocks_by_chapter(notebook_title: str, structured_sections: list, is_final: bool = False):
    """按章拆分导出结构化资料。"""
    if not structured_sections:
        logger.warning("没有结构化内容可按章导出。")
        return

    chapters = _group_structured_by_chapter(structured_sections)
    bundle_dir = _chapter_bundle_dir(notebook_title, "结构化资料_分章")
    intro = "按章拆分的结构化资料入口，适合顺序阅读和局部精修。"
    index_path = _write_chapter_index(bundle_dir, f"{notebook_title} - 结构化资料（分章）", intro, chapters)

    for idx, chapter in enumerate(chapters, start=1):
        chapter_name = chapter["chapter_name"]
        output_path = os.path.join(bundle_dir, _chapter_file_name(idx, chapter_name))
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"# {notebook_title} - {chapter_name}（结构化）\n\n")
            if not is_final:
                f.write("> 🔄 本章结构化资料仍可能继续更新。\n\n")
            else:
                f.write("> ✅ 本章结构化资料已整理完毕。\n\n")

            for section in chapter["sections"]:
                section_name = section["section_name"]
                blocks = section.get("blocks", [])
                f.write(f"## {section_name}\n\n")
                for block in blocks:
                    title = (block.get("block_title") or block.get("block_type") or "未命名内容").strip()
                    content = str(block.get("content", "")).strip()
                    payload = block.get("payload") or {}
                    if not content:
                        continue
                    f.write(f"### {title}\n")
                    if block.get("block_type") == "renderable_visual":
                        if payload.get("render_format"):
                            f.write(f"- 渲染格式: {payload['render_format']}\n")
                        if payload.get("visual_kind"):
                            f.write(f"- 图示类型: {payload['visual_kind']}\n")
                        if payload.get("ratio_hint"):
                            f.write(f"- 建议比例: {payload['ratio_hint']}\n")
                        if payload.get("title"):
                            f.write(f"- 图示标题: {payload['title']}\n")
                        if payload.get("render_goal"):
                            f.write(f"- 图示目标: {payload['render_goal']}\n")
                        if payload.get("caption"):
                            f.write(f"- 图注: {payload['caption']}\n")
                        for item in payload.get("notes", []):
                            f.write(f"- 说明: {item}\n")
                        if payload:
                            f.write("\n")
                        svg_code = str(payload.get("svg_code", "")).strip()
                        mermaid_code = str(payload.get("mermaid_code", "")).strip()
                        if svg_code:
                            _write_svg_block(f, svg_code)
                        elif mermaid_code:
                            _write_mermaid_block(f, mermaid_code)
                        elif content:
                            f.write(f"{content}\n\n")
                        continue

                    f.write(f"{content}\n\n")
                f.write("---\n\n")

    logger.info(f"🧱 分章结构化资料已导出至: {os.path.abspath(bundle_dir)} (目录: {os.path.basename(index_path)})")


def _build_comic_prompt(chapter_name: str, section_name: str, intuition_text: str, background_text: str = "") -> str:
    lines = [
        f"请将“{chapter_name} - {section_name}”设计成一页或一组教学漫画分镜。",
        "风格要求：学术准确、形象直观、适合复习笔记配图，不要夸张二次元风。",
        "画面目标：把抽象概念变成可视化场景，让读者一眼理解核心机制。",
    ]
    if background_text:
        lines.append(f"背景主线：{background_text}")
    lines.append(f"大白话核心解释：{intuition_text}")
    lines.append("请突出：角色/物体隐喻、空间关系、因果过程、关键变量变化，并避免与公式含义矛盾。")
    return "\n".join(lines)


def _build_comic_prompt_from_payload(chapter_name: str, section_name: str, payload: dict, background_text: str = "") -> str:
    direct_prompt = str(payload.get("comic_prompt", "")).strip()
    if direct_prompt:
        lines = [
            f"主题：{chapter_name} - {section_name}",
            direct_prompt,
        ]
        if background_text:
            lines.append(f"背景主线：{background_text}")
        return "\n".join(lines)

    plain_explanation = str(payload.get("plain_explanation", "")).strip()
    metaphor = str(payload.get("metaphor", "")).strip()
    visual_scene = str(payload.get("visual_scene", "")).strip()

    lines = [
        f"请将“{chapter_name} - {section_name}”设计成教学漫画分镜。",
        "风格要求：简洁、准确、适合复习资料配图。",
    ]
    if background_text:
        lines.append(f"背景主线：{background_text}")
    if plain_explanation:
        lines.append(f"核心解释：{plain_explanation}")
    if metaphor:
        lines.append(f"隐喻设计：{metaphor}")
    if visual_scene:
        lines.append(f"画面场景：{visual_scene}")
    lines.append("请明确主体角色、动作过程、空间关系、变量变化，并保持数学含义准确。")
    return "\n".join(lines)


def export_comic_prompts(notebook_title: str, structured_sections: list, is_final: bool = False):
    """从 intuition_plain_language 块提取漫画提示词。"""
    if not structured_sections:
        logger.warning("没有结构化内容可用于导出漫画提示词。")
        return

    output_path = _notebook_file_path(notebook_title, "漫画提示词.md")

    exported_count = 0
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# {notebook_title} - 漫画提示词\n")
        if not is_final:
            f.write("> 🔄 该文件会随着结构化内容的生成实时更新。\n\n")
        else:
            f.write("> ✅ 该文件由 `intuition_plain_language` 为主、`background_storyline` 为辅自动整理。\n\n")
        f.write("---\n\n")

        current_chapter = None
        for section in structured_sections:
            chapter_name = section["chapter_name"]
            section_name = section["section_name"]
            blocks = section.get("blocks", [])

            intuition_blocks = [block for block in blocks if block.get("block_type") == "intuition_plain_language"]
            if not intuition_blocks:
                continue

            background_blocks = [block for block in blocks if block.get("block_type") == "background_storyline"]
            intuition_text = "\n".join(
                block.get("content", "").strip() for block in intuition_blocks if block.get("content", "").strip()
            ).strip()
            background_text = "\n".join(
                block.get("content", "").strip() for block in background_blocks if block.get("content", "").strip()
            ).strip()

            if not intuition_text:
                has_payload_only = any((block.get("payload") or {}).get("plain_explanation") or (block.get("payload") or {}).get("comic_prompt") for block in intuition_blocks)
                if not has_payload_only:
                    continue

            if chapter_name != current_chapter:
                if current_chapter is not None:
                    f.write(f"{PAGE_BREAK_MARKER}\n\n")
                f.write(f"# {chapter_name}\n\n")
                current_chapter = chapter_name

            first_payload = next((block.get("payload") for block in intuition_blocks if block.get("payload")), None)
            if first_payload:
                prompt = _build_comic_prompt_from_payload(chapter_name, section_name, first_payload, background_text)
            else:
                prompt = _build_comic_prompt(chapter_name, section_name, intuition_text, background_text)
            f.write(f"## {section_name}\n\n")
            f.write(f"{prompt}\n\n")
            f.write("---\n\n")
            exported_count += 1

    if exported_count == 0:
        logger.warning("当前还没有可用的 intuition_plain_language 块，暂未生成漫画提示词文件。")
        return

    logger.info(f"🖼️ 漫画提示词已导出至: {os.path.abspath(output_path)}")


def export_comic_prompts_by_chapter(notebook_title: str, structured_sections: list, is_final: bool = False):
    """按章拆分导出漫画提示词。"""
    if not structured_sections:
        logger.warning("没有结构化内容可按章导出漫画提示词。")
        return

    chapters = _group_structured_by_chapter(structured_sections)
    bundle_dir = _chapter_bundle_dir(notebook_title, "漫画提示词_分章")
    intro = "按章拆分的漫画提示词入口，便于按知识主线批量生成图像。"
    index_path = _write_chapter_index(bundle_dir, f"{notebook_title} - 漫画提示词（分章）", intro, chapters)

    exported_any = False
    for idx, chapter in enumerate(chapters, start=1):
        chapter_name = chapter["chapter_name"]
        output_path = os.path.join(bundle_dir, _chapter_file_name(idx, chapter_name))
        section_written = 0
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"# {notebook_title} - {chapter_name}（漫画提示词）\n\n")
            if not is_final:
                f.write("> 🔄 本章漫画提示词仍可能继续更新。\n\n")
            else:
                f.write("> ✅ 本章漫画提示词已整理完毕。\n\n")

            for section in chapter["sections"]:
                section_name = section["section_name"]
                blocks = section.get("blocks", [])
                intuition_blocks = [block for block in blocks if block.get("block_type") == "intuition_plain_language"]
                if not intuition_blocks:
                    continue

                background_blocks = [block for block in blocks if block.get("block_type") == "background_storyline"]
                intuition_text = "\n".join(
                    block.get("content", "").strip() for block in intuition_blocks if block.get("content", "").strip()
                ).strip()
                background_text = "\n".join(
                    block.get("content", "").strip() for block in background_blocks if block.get("content", "").strip()
                ).strip()

                if not intuition_text:
                    has_payload_only = any((block.get("payload") or {}).get("plain_explanation") or (block.get("payload") or {}).get("comic_prompt") for block in intuition_blocks)
                    if not has_payload_only:
                        continue

                first_payload = next((block.get("payload") for block in intuition_blocks if block.get("payload")), None)
                if first_payload:
                    prompt = _build_comic_prompt_from_payload(chapter_name, section_name, first_payload, background_text)
                else:
                    prompt = _build_comic_prompt(chapter_name, section_name, intuition_text, background_text)

                f.write(f"## {section_name}\n\n")
                f.write(f"{prompt}\n\n")
                f.write("---\n\n")
                section_written += 1
                exported_any = True

        if section_written == 0:
            os.remove(output_path)

    if not exported_any:
        logger.warning("当前还没有可用的 intuition_plain_language 块，暂未生成分章漫画提示词文件。")
        return

    logger.info(f"🖼️ 分章漫画提示词已导出至: {os.path.abspath(bundle_dir)} (目录: {os.path.basename(index_path)})")


def export_image_tasks(notebook_title: str, structured_sections: list, is_final: bool = False):
    """导出面向外部图像模型的任务清单。"""
    if not structured_sections:
        logger.warning("没有结构化内容可用于导出图像任务。")
        return

    image_tasks, _ = _collect_visual_exports(structured_sections)
    if not image_tasks:
        logger.warning("当前还没有可用的图像任务。")
        return

    output_path = _notebook_file_path(notebook_title, "图像任务.md")
    jsonl_path = _notebook_file_path(notebook_title, "图像任务.jsonl")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# {notebook_title} - 图像任务\n")
        if not is_final:
            f.write("> 🔄 该文件会随着结构化内容的生成实时更新。\n\n")
        else:
            f.write("> ✅ 该文件适合批量喂给 Lovart、GPT Image 2、Banana Pro 等图像模型。\n\n")
        f.write("---\n\n")

        current_chapter = None
        for task in image_tasks:
            if task["chapter_name"] != current_chapter:
                if current_chapter is not None:
                    f.write(f"{PAGE_BREAK_MARKER}\n\n")
                f.write(f"# {task['chapter_name']}\n\n")
                current_chapter = task["chapter_name"]
            f.write(f"## {task['section_name']} / {task['title']}\n\n")
            f.write(f"- 任务类型: {task['image_kind']}\n")
            f.write(f"- 建议工具: {', '.join(task.get('tool_targets', []))}\n")
            if task.get("focus_points"):
                f.write(f"- 重点元素: {'；'.join(task['focus_points'])}\n")
            if task.get("source_basis"):
                f.write(f"- 知识依据: {task['source_basis']}\n")
            f.write("\n### 主提示词\n\n")
            f.write(f"{task['prompt']}\n\n")
            if task.get("negative_prompt"):
                f.write("### 反向提示词\n\n")
                f.write(f"{task['negative_prompt']}\n\n")
            f.write("---\n\n")

    with open(jsonl_path, "w", encoding="utf-8") as f:
        for task in image_tasks:
            f.write(json.dumps(task, ensure_ascii=False) + "\n")

    logger.info(f"🖼️ 图像任务已导出至: {os.path.abspath(output_path)}")


def export_image_tasks_by_chapter(notebook_title: str, structured_sections: list, is_final: bool = False):
    """按章拆分导出图像任务。"""
    if not structured_sections:
        logger.warning("没有结构化内容可按章导出图像任务。")
        return

    chapters = _group_structured_by_chapter(structured_sections)
    bundle_dir = _chapter_bundle_dir(notebook_title, "图像任务_分章")
    intro = "按章拆分的图像任务入口，适合批量调用 Lovart、GPT Image 2、Banana Pro。"
    index_path = _write_chapter_index(bundle_dir, f"{notebook_title} - 图像任务（分章）", intro, chapters)

    exported_any = False
    for idx, chapter in enumerate(chapters, start=1):
        chapter_name = chapter["chapter_name"]
        output_path = os.path.join(bundle_dir, _chapter_file_name(idx, chapter_name))
        tasks = []
        for section in chapter["sections"]:
            tasks.extend(_build_image_task_payload(chapter_name, section["section_name"], section.get("blocks", [])))
        if not tasks:
            if os.path.exists(output_path):
                os.remove(output_path)
            continue

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"# {notebook_title} - {chapter_name}（图像任务）\n\n")
            if not is_final:
                f.write("> 🔄 本章图像任务仍可能继续更新。\n\n")
            else:
                f.write("> ✅ 本章图像任务已整理完毕。\n\n")
            for task in tasks:
                f.write(f"## {task['section_name']} / {task['title']}\n\n")
                f.write(f"- 任务类型: {task['image_kind']}\n")
                f.write(f"- 建议工具: {', '.join(task.get('tool_targets', []))}\n")
                if task.get("focus_points"):
                    f.write(f"- 重点元素: {'；'.join(task['focus_points'])}\n")
                f.write("\n### 主提示词\n\n")
                f.write(f"{task['prompt']}\n\n")
                if task.get("negative_prompt"):
                    f.write("### 反向提示词\n\n")
                    f.write(f"{task['negative_prompt']}\n\n")
                f.write("---\n\n")
        exported_any = True

    if not exported_any:
        logger.warning("当前还没有可用的分章图像任务。")
        return

    logger.info(f"🖼️ 分章图像任务已导出至: {os.path.abspath(bundle_dir)} (目录: {os.path.basename(index_path)})")


def export_renderable_visuals(notebook_title: str, structured_sections: list, is_final: bool = False):
    """导出可直接渲染的图表/图示，支持 SVG 与 Mermaid。"""
    if not structured_sections:
        logger.warning("没有结构化内容可用于导出可渲染图示。")
        return

    _, renderable_tasks = _collect_visual_exports(structured_sections)
    if not renderable_tasks:
        logger.warning("当前还没有可用的可渲染图示。")
        return

    output_path = _notebook_file_path(notebook_title, "可渲染图示.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# {notebook_title} - 可渲染图示\n")
        if not is_final:
            f.write("> 🔄 该文件会随着结构化内容的生成实时更新。\n\n")
        else:
            f.write("> ✅ 该文件输出 SVG 或 Mermaid，可直接在 Obsidian / Markdown 环境中渲染。\n\n")
        f.write("---\n\n")

        current_chapter = None
        for task in renderable_tasks:
            if task["chapter_name"] != current_chapter:
                if current_chapter is not None:
                    f.write(f"{PAGE_BREAK_MARKER}\n\n")
                f.write(f"# {task['chapter_name']}\n\n")
                current_chapter = task["chapter_name"]
            f.write(f"## {task['section_name']} / {task['title']}\n\n")
            if task.get("render_goal"):
                f.write(f"- 图示目标: {task['render_goal']}\n")
            if task.get("caption"):
                f.write(f"- 图注: {task['caption']}\n")
            if task.get("notes"):
                for note in task["notes"]:
                    f.write(f"- 说明: {note}\n")
            f.write(f"- 渲染类型: {task['visual_kind']}\n\n")
            if task.get("render_format") == "svg" and task.get("svg_code"):
                _write_svg_block(f, task["svg_code"])
            else:
                _write_mermaid_block(f, task["mermaid_code"])
            f.write("---\n\n")

    logger.info(f"📊 可渲染图示已导出至: {os.path.abspath(output_path)}")


def export_renderable_visuals_by_chapter(notebook_title: str, structured_sections: list, is_final: bool = False):
    """按章拆分导出可渲染图示。"""
    if not structured_sections:
        logger.warning("没有结构化内容可按章导出可渲染图示。")
        return

    chapters = _group_structured_by_chapter(structured_sections)
    bundle_dir = _chapter_bundle_dir(notebook_title, "可渲染图示_分章")
    intro = "按章拆分的可渲染图示入口，支持 SVG 与 Mermaid，便于直接在 Markdown 中预览。"
    index_path = _write_chapter_index(bundle_dir, f"{notebook_title} - 可渲染图示（分章）", intro, chapters)

    exported_any = False
    for idx, chapter in enumerate(chapters, start=1):
        chapter_name = chapter["chapter_name"]
        output_path = os.path.join(bundle_dir, _chapter_file_name(idx, chapter_name))
        tasks = []
        for section in chapter["sections"]:
            tasks.extend(_build_renderable_visual_tasks(chapter_name, section["section_name"], section.get("blocks", [])))
        if not tasks:
            if os.path.exists(output_path):
                os.remove(output_path)
            continue

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"# {notebook_title} - {chapter_name}（可渲染图示）\n\n")
            if not is_final:
                f.write("> 🔄 本章可渲染图示仍可能继续更新。\n\n")
            else:
                f.write("> ✅ 本章可渲染图示已整理完毕。\n\n")
            for task in tasks:
                f.write(f"## {task['section_name']} / {task['title']}\n\n")
                if task.get("render_goal"):
                    f.write(f"- 图示目标: {task['render_goal']}\n")
                if task.get("caption"):
                    f.write(f"- 图注: {task['caption']}\n")
                if task.get("notes"):
                    for note in task["notes"]:
                        f.write(f"- 说明: {note}\n")
                f.write(f"- 渲染类型: {task['visual_kind']}\n\n")
                if task.get("render_format") == "svg" and task.get("svg_code"):
                    _write_svg_block(f, task["svg_code"])
                else:
                    _write_mermaid_block(f, task["mermaid_code"])
                f.write("---\n\n")
        exported_any = True

    if not exported_any:
        logger.warning("当前还没有可用的分章可渲染图示。")
        return

    logger.info(f"📊 分章可渲染图示已导出至: {os.path.abspath(bundle_dir)} (目录: {os.path.basename(index_path)})")


def export_quality_report(notebook_title: str, quality_report: dict):
    """导出结构化内容质量校验报告。"""
    if not quality_report:
        logger.warning("没有质量报告可导出。")
        return

    summary = quality_report.get("summary", {})
    chapter_summaries = quality_report.get("chapters", [])
    sections = quality_report.get("sections", [])
    manual_mermaid_reviews = _collect_manual_mermaid_review_items(sections)

    output_path = _notebook_file_path(notebook_title, "质量报告.md")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# {notebook_title} - 内容质量报告\n\n")
        f.write(f"- 小节总数: {summary.get('section_count', 0)}\n")
        f.write(f"- 通过数: {summary.get('passed_count', 0)}\n")
        f.write(f"- 错误数: {summary.get('error_count', 0)}\n")
        f.write(f"- 警告数: {summary.get('warning_count', 0)}\n\n")
        f.write(f"- 自动修复数: {summary.get('auto_fix_count', 0)}\n\n")
        f.write(f"- 平均分: {summary.get('average_score', 0)}\n\n")
        f.write(f"- 建议回看节级判定数: {summary.get('plan_review_count', 0)}\n\n")

        f.write(f"- 待人工检查图示数: {len(manual_mermaid_reviews)}\n\n")
        f.write("---\n\n")

        f.write("## 按章摘要\n\n")
        if not chapter_summaries:
            f.write("- 当前没有可汇总的章节质量数据。\n\n")
        else:
            for chapter in chapter_summaries:
                f.write(f"### {chapter['chapter_name']}\n\n")
                f.write(f"- 小节数: {chapter.get('section_count', 0)}\n")
                f.write(f"- 通过数: {chapter.get('passed_count', 0)}\n")
                f.write(f"- 错误数: {chapter.get('error_count', 0)}\n")
                f.write(f"- 警告数: {chapter.get('warning_count', 0)}\n")
                f.write(f"- 建议回看节级判定数: {chapter.get('plan_review_count', 0)}\n")
                if chapter.get("sections_to_review"):
                    f.write(f"- 建议回看小节: {'；'.join(chapter['sections_to_review'])}\n")
                f.write("\n")
        f.write("---\n\n")

        f.write("## 待人工检查图示\n\n")
        if not manual_mermaid_reviews:
            f.write("- 当前未发现仍需人工处理的 Mermaid / 可渲染图示问题。\n\n")
        else:
            for item in manual_mermaid_reviews:
                f.write(f"### {item['chapter_name']} / {item['section_name']}\n\n")
                for message in item["messages"]:
                    f.write(f"- 待检查: {message}\n")
                f.write("\n")
        f.write("---\n\n")

        for section in sections:
            chapter_name = section["chapter_name"]
            section_name = section["section_name"]
            status = "通过" if section["passed"] else "需补强"
            f.write(f"## {chapter_name} / {section_name}\n\n")
            f.write(f"- 状态: {status}\n")
            f.write(f"- 分数: {section['score']}\n")
            f.write(f"- 风格判定: {section.get('section_style', '未知')}\n")
            if section.get("style_reason"):
                f.write(f"- 风格判定依据: {section['style_reason']}\n")
            f.write(f"- 需要严谨推导补充: {'是' if section.get('derivation_needed') else '否'}\n")
            f.write(f"- 需要可渲染图示: {'是' if section.get('visual_needed') else '否'}\n")
            if section.get("visual_type") and section.get("visual_type") != "none":
                f.write(f"- 首判图示类型: {section['visual_type']}\n")
            if section.get("visual_ratio"):
                f.write(f"- 首判图示比例: {section['visual_ratio']}\n")
            if section.get("visual_reason"):
                f.write(f"- 图示判定依据: {section['visual_reason']}\n")
            if section.get("run_status_label"):
                f.write(f"- 运行状态: {section['run_status_label']}\n")
            f.write(f"- 判定来源: {'首次大纲模型判定' if section.get('plan_source') == 'outline_model' else '代码兜底判定'}\n")
            f.write(f"- 轻校正状态: {section.get('plan_consistency', '未知')}\n")
            f.write(f"- 错误数: {section['error_count']}\n")
            f.write(f"- 警告数: {section['warning_count']}\n")
            f.write(f"- 自动修复数: {section.get('auto_fix_count', 0)}\n")
            f.write(f"- 已有内容块: {', '.join(section.get('block_types', [])) or '无'}\n\n")
            plan_evidence = section.get("plan_evidence", [])
            if plan_evidence:
                f.write("### 生成证据\n\n")
                for item in plan_evidence:
                    f.write(f"- {item}\n")
                f.write("\n")
            plan_suggestions = section.get("plan_suggestions", [])
            suggested_plan = section.get("suggested_plan")
            if plan_suggestions or suggested_plan:
                f.write("### 建议校正\n\n")
                for item in plan_suggestions:
                    f.write(f"- {item}\n")
                if suggested_plan:
                    f.write(
                        f"- 建议风格: {suggested_plan.get('label', '未知')}；"
                        f"严谨推导补充: {'是' if suggested_plan.get('derivation_needed') else '否'}；"
                        f"可渲染图示: {'是' if suggested_plan.get('visual_needed') else '否'}；"
                        f"图示类型: {suggested_plan.get('visual_type', 'none')}；"
                        f"图示比例: {suggested_plan.get('visual_ratio') or '未指定'}\n"
                    )
                f.write("\n")
            repair_hints = section.get("repair_hints", [])
            if repair_hints:
                f.write("### 当前最值得优先补强\n\n")
                for hint in repair_hints:
                    f.write(f"- {hint}\n")
                f.write("\n")
            for auto_fix in section.get("auto_fixes", []):
                f.write(f"- 自动修复: {auto_fix}\n")
            for issue in section.get("issues", []):
                prefix = "错误" if issue["level"] == "error" else "警告"
                f.write(f"- {prefix}: {issue['message']}\n")
            f.write("\n---\n\n")

    logger.info(f"🩺 质量报告已导出至: {os.path.abspath(output_path)}")


def export_quality_report_by_chapter(notebook_title: str, quality_report: dict):
    if not quality_report:
        logger.warning("没有质量报告可按章导出。")
        return

    sections = quality_report.get("sections", [])
    if not sections:
        logger.warning("质量报告中没有可按章导出的 section 数据。")
        return

    grouped = {}
    for section in sections:
        grouped.setdefault(section["chapter_name"], []).append(section)

    chapters = [{"chapter_name": name, "sections": data} for name, data in grouped.items()]
    bundle_dir = _chapter_bundle_dir(notebook_title, QUALITY_REPORT_CHAPTER_DIR)
    intro = "按章节拆分的质量报告入口，重点展示每节的首次判定、生成证据与建议回看项。"
    index_path = _write_chapter_index(bundle_dir, f"{notebook_title} - 质量报告（分章）", intro, chapters)

    for idx, chapter in enumerate(chapters, start=1):
        chapter_name = chapter["chapter_name"]
        output_path = os.path.join(bundle_dir, _chapter_file_name(idx, chapter_name))
        chapter_sections = chapter["sections"]
        section_count = len(chapter_sections)
        passed_count = sum(1 for item in chapter_sections if item.get("passed"))
        error_count = sum(item.get("error_count", 0) for item in chapter_sections)
        warning_count = sum(item.get("warning_count", 0) for item in chapter_sections)
        plan_review_count = sum(1 for item in chapter_sections if item.get("plan_review_needed"))

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"# {notebook_title} - {chapter_name}（质量报告）\n\n")
            f.write(f"- 小节数: {section_count}\n")
            f.write(f"- 通过数: {passed_count}\n")
            f.write(f"- 错误数: {error_count}\n")
            f.write(f"- 警告数: {warning_count}\n")
            f.write(f"- 建议回看节级判定数: {plan_review_count}\n\n")
            f.write("---\n\n")

            for section in chapter_sections:
                f.write(f"## {section['section_name']}\n\n")
                f.write(f"- 状态: {'通过' if section.get('passed') else '需补强'}\n")
                f.write(f"- 风格判定: {section.get('section_style', '未知')}\n")
                if section.get("visual_type") and section.get("visual_type") != "none":
                    f.write(f"- 首判图示类型: {section.get('visual_type')}\n")
                if section.get("visual_ratio"):
                    f.write(f"- 首判图示比例: {section.get('visual_ratio')}\n")
                if section.get("run_status_label"):
                    f.write(f"- 运行状态: {section.get('run_status_label')}\n")
                f.write(f"- 判定来源: {'首次大纲模型判定' if section.get('plan_source') == 'outline_model' else '代码兜底判定'}\n")
                f.write(f"- 轻校正状态: {section.get('plan_consistency', '未知')}\n")
                evidence = section.get("plan_evidence", [])
                if evidence:
                    f.write("- 生成证据:\n")
                    for item in evidence:
                        f.write(f"  - {item}\n")
                suggestions = section.get("plan_suggestions", [])
                suggested_plan = section.get("suggested_plan")
                if suggestions or suggested_plan:
                    f.write("- 建议校正:\n")
                    for item in suggestions:
                        f.write(f"  - {item}\n")
                    if suggested_plan:
                        f.write(
                            f"  - 建议风格: {suggested_plan.get('label', '未知')}；"
                            f"严谨推导补充: {'是' if suggested_plan.get('derivation_needed') else '否'}；"
                            f"可渲染图示: {'是' if suggested_plan.get('visual_needed') else '否'}；"
                            f"图示类型: {suggested_plan.get('visual_type', 'none')}；"
                            f"图示比例: {suggested_plan.get('visual_ratio') or '未指定'}\n"
                        )
                for issue in section.get("issues", []):
                    prefix = "错误" if issue["level"] == "error" else "警告"
                    f.write(f"- {prefix}: {issue['message']}\n")
                f.write("\n---\n\n")

    logger.info(f"🩺 分章质量报告已导出至: {os.path.abspath(bundle_dir)} (目录: {os.path.basename(index_path)})")


def export_publish_gate_report(notebook_title: str, publish_gate: dict):
    """导出是否允许生成正式版的闸门报告。"""
    if not publish_gate:
        logger.warning("没有发布闸门结果可导出。")
        return

    output_path = _notebook_file_path(notebook_title, "发布闸门.md")
    summary = publish_gate.get("summary", {})
    thresholds = publish_gate.get("thresholds", {})

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# {notebook_title} - 发布闸门\n\n")
        f.write(f"- 是否通过: {'是' if publish_gate.get('passed') else '否'}\n")
        f.write(f"- 平均分: {summary.get('average_score', 0)} / 阈值 {thresholds.get('min_average_score', 0)}\n")
        f.write(f"- 错误数: {summary.get('error_count', 0)} / 阈值 {thresholds.get('max_error_count', 0)}\n")
        f.write(f"- 警告数: {summary.get('warning_count', 0)} / 阈值 {thresholds.get('max_warning_count', 0)}\n\n")

        reasons = publish_gate.get("reasons", [])
        if reasons:
            f.write("## 未通过原因\n\n")
            for reason in reasons:
                f.write(f"- {reason}\n")
        else:
            f.write("## 结论\n\n")
            f.write("- 当前质量已达到正式导出阈值，可以进入正式版导出。\n")

    logger.info(f"🚦 发布闸门报告已导出至: {os.path.abspath(output_path)}")
