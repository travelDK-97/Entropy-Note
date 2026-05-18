import argparse
import logging
import os


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("VisualPostprocess")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="对已完成笔记本执行图示后处理：预渲染 Mermaid/SVG，并将图片写回 Markdown 文档。"
    )
    parser.add_argument("--notebook-title", help="指定要处理的笔记本标题。")
    parser.add_argument("--all", action="store_true", help="处理数据库中所有已有内容的笔记本。")
    parser.add_argument(
        "--outline-mode",
        choices=["core", "official_from_sources"],
        default="core",
        help="读取 outline 缓存时使用的大纲模式，默认 core。",
    )
    parser.add_argument(
        "--embed-mode",
        choices=["source_code", "rendered_images", "hybrid"],
        default="rendered_images",
        help="文档写回模式：源码、插图或混合，默认 rendered_images。",
    )
    parser.add_argument("--db-path", help="可选：指定数据库文件路径，默认使用项目内 study_guide.db。")
    return parser


def _filter_results_by_outline(results: list, outline: list) -> list:
    allowed_pairs = {
        (part.get("chapter", ""), section)
        for part in outline or []
        for section in (part.get("sections", []) or [])
    }
    if not allowed_pairs:
        return results
    return [
        row
        for row in results
        if len(row) >= 2 and (row[0], row[1]) in allowed_pairs
    ]


def _select_targets(db, *, notebook_title: str | None, run_all: bool) -> list[str]:
    titles = db.list_notebook_titles()
    if run_all:
        return titles
    if notebook_title:
        return [notebook_title]

    if not titles:
        return []

    print("\n[已完成笔记本]")
    for idx, title in enumerate(titles, start=1):
        print(f"{idx}. {title}")

    while True:
        choice = input("\n👉 请选择要后处理的笔记本序号: ").strip()
        if choice.isdigit():
            index = int(choice)
            if 1 <= index <= len(titles):
                return [titles[index - 1]]
        print("请输入有效序号。")


def _postprocess_notebook(db, notebook_title: str, *, outline_mode: str):
    from src.utils.exporter import (
        export_renderable_visuals,
        export_renderable_visuals_by_chapter,
        export_structured_blocks,
        export_structured_blocks_by_chapter,
        export_to_markdown,
        export_to_markdown_by_chapter,
        prepare_rendered_visual_assets,
        update_notebook_index_postprocess_status,
    )

    outline = db.get_outline(notebook_title, outline_mode=outline_mode)
    results = _filter_results_by_outline(db.get_all_sections(notebook_title), outline)
    structured_sections = db.get_structured_sections(notebook_title, outline=outline or None)

    if not results and not structured_sections:
        logger.warning("跳过 %s：数据库中没有可处理的内容。", notebook_title)
        return False

    rendered_visual_lookup = prepare_rendered_visual_assets(notebook_title, structured_sections)
    export_to_markdown(
        notebook_title,
        results,
        is_final=True,
        structured_sections=structured_sections,
        rendered_visual_lookup=rendered_visual_lookup,
    )
    export_to_markdown_by_chapter(
        notebook_title,
        results,
        is_final=True,
        structured_sections=structured_sections,
        rendered_visual_lookup=rendered_visual_lookup,
    )

    if structured_sections:
        export_structured_blocks(
            notebook_title,
            structured_sections,
            is_final=True,
            rendered_visual_lookup=rendered_visual_lookup,
        )
        export_structured_blocks_by_chapter(
            notebook_title,
            structured_sections,
            is_final=True,
            rendered_visual_lookup=rendered_visual_lookup,
        )
        export_renderable_visuals(
            notebook_title,
            structured_sections,
            is_final=True,
            rendered_visual_lookup=rendered_visual_lookup,
        )
        export_renderable_visuals_by_chapter(
            notebook_title,
            structured_sections,
            is_final=True,
            rendered_visual_lookup=rendered_visual_lookup,
        )

    asset_count = sum(
        1
        for tasks in rendered_visual_lookup.values()
        for task in tasks
        if task.get("asset_path")
    )
    update_notebook_index_postprocess_status(
        notebook_title,
        embed_mode=os.environ.get("ENTROPY_NOTE_VISUAL_EMBED_MODE", "rendered_images"),
        asset_count=asset_count,
        processed_section_count=len(rendered_visual_lookup),
    )
    logger.info("后处理完成: %s (写入图示资产 %s 个)", notebook_title, asset_count)
    return True


def main():
    parser = build_parser()
    args = parser.parse_args()

    os.environ["ENTROPY_NOTE_VISUAL_EMBED_MODE"] = args.embed_mode

    from src.db.manager import DatabaseManager

    db = DatabaseManager(args.db_path) if args.db_path else DatabaseManager()
    targets = _select_targets(
        db,
        notebook_title=args.notebook_title,
        run_all=args.all,
    )
    if not targets:
        raise SystemExit("没有找到可处理的笔记本。")

    completed = 0
    for notebook_title in targets:
        if _postprocess_notebook(db, notebook_title, outline_mode=args.outline_mode):
            completed += 1

    logger.info("图示后处理结束：成功处理 %s/%s 本笔记。", completed, len(targets))


if __name__ == "__main__":
    main()
