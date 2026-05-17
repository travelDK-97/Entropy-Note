import asyncio
import argparse
import logging
import sys
from src.config import (
    LEARNING_FIRST_MODE,
    PUBLISH_MAX_ERROR_COUNT,
    PUBLISH_MAX_WARNING_COUNT,
    PUBLISH_MIN_AVERAGE_SCORE,
)
from src.core.client import SafeNotebookClient
from src.core.quality import evaluate_publish_gate, validate_structured_sections
from src.db.manager import DatabaseManager
from src.prompts.markdown_prompts import (
    PROMPT_VERSION,
    build_stage_prompts,
    merge_stage_blocks,
    parse_structured_response,
)
from src.prompts.section_style import enrich_outline_with_section_plans, get_outline_section_plan
from src.utils.exporter import (
    export_cheatsheets,
    export_cheatsheets_by_chapter,
    export_comic_prompts,
    export_comic_prompts_by_chapter,
    export_image_tasks,
    export_image_tasks_by_chapter,
    export_notebook_index,
    export_publish_gate_report,
    export_quality_report,
    export_quality_report_by_chapter,
    export_renderable_visuals,
    export_renderable_visuals_by_chapter,
    export_structured_blocks,
    export_structured_blocks_by_chapter,
    export_to_markdown,
    export_to_markdown_by_chapter,
)

# 屏蔽底层 httpx 的刷屏日志
logging.getLogger("httpx").setLevel(logging.WARNING)

# 配置简洁的日志格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("Main")
QUALITY_REGEN_MAX_ATTEMPTS = 3


def _is_publish_exports_enabled() -> bool:
    return not LEARNING_FIRST_MODE


def log_generation_status(notebook_title: str, status: dict):
    total = status.get("total_sections", 0)
    completed = status.get("completed_sections", 0)
    logger.info(f"笔记本《{notebook_title}》当前完成度: {completed}/{total} 小节。")

    for chapter, meta in status.get("chapters", {}).items():
        total_sections = meta.get("total", 0)
        completed_sections = meta.get("completed", 0)
        if total_sections == 0:
            continue
        if meta.get("is_complete"):
            logger.info(f"✅ 章节已完成: {chapter} ({completed_sections}/{total_sections})")
            continue

        missing_sections = meta.get("missing_sections", [])
        preview = "，".join(missing_sections[:3])
        if len(missing_sections) > 3:
            preview += " ..."
        logger.info(
            f"🧩 章节待补全: {chapter} ({completed_sections}/{total_sections})"
            + (f"；缺失: {preview}" if preview else "")
        )


def _group_plain_chapters(results: list) -> list[dict]:
    grouped_map = {}
    ordered_chapters = []
    for chapter_name, section_name, content in results:
        if chapter_name not in grouped_map:
            grouped_map[chapter_name] = {
                "chapter_name": chapter_name,
                "sections": [],
            }
            ordered_chapters.append(grouped_map[chapter_name])
        grouped_map[chapter_name]["sections"].append(
            {
                "section_name": section_name,
                "content": content,
            }
        )
    return ordered_chapters


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


def export_all_views(db: DatabaseManager, notebook_title: str, outline: list, *, is_final: bool):
    repaired = db.repair_structured_fallbacks(notebook_title)
    if repaired:
        logger.info(f"已自动修复 {repaired} 个历史结构化回退结果，并重新导出。")
    results = _filter_results_by_outline(db.get_all_sections(notebook_title), outline)
    plain_chapters = _group_plain_chapters(results)
    structured_sections = db.get_structured_sections(notebook_title, outline=outline)
    export_to_markdown(
        notebook_title,
        results,
        is_final=is_final,
        structured_sections=structured_sections,
    )
    export_to_markdown_by_chapter(
        notebook_title,
        results,
        is_final=is_final,
        structured_sections=structured_sections,
    )

    if structured_sections:
        export_cheatsheets(notebook_title, structured_sections, is_final=is_final)
        export_cheatsheets_by_chapter(notebook_title, structured_sections, is_final=is_final)
        export_structured_blocks(notebook_title, structured_sections, is_final=is_final)
        export_structured_blocks_by_chapter(notebook_title, structured_sections, is_final=is_final)
        export_renderable_visuals(notebook_title, structured_sections, is_final=is_final)
        export_renderable_visuals_by_chapter(notebook_title, structured_sections, is_final=is_final)
        quality_report = validate_structured_sections(structured_sections, notebook_title=notebook_title)
        export_quality_report(notebook_title, quality_report)
        export_quality_report_by_chapter(notebook_title, quality_report)
        summary = quality_report.get("summary", {})
        logger.info(
            "质量校验摘要: "
            f"{summary.get('passed_count', 0)}/{summary.get('section_count', 0)} 小节通过，"
            f"{summary.get('error_count', 0)} 个错误，"
            f"{summary.get('warning_count', 0)} 个警告。"
        )

        publish_gate = None
        if _is_publish_exports_enabled():
            export_comic_prompts(notebook_title, structured_sections, is_final=is_final)
            export_comic_prompts_by_chapter(notebook_title, structured_sections, is_final=is_final)
            export_image_tasks(notebook_title, structured_sections, is_final=is_final)
            export_image_tasks_by_chapter(notebook_title, structured_sections, is_final=is_final)
            publish_gate = evaluate_publish_gate(
                quality_report,
                min_average_score=PUBLISH_MIN_AVERAGE_SCORE,
                max_error_count=PUBLISH_MAX_ERROR_COUNT,
                max_warning_count=PUBLISH_MAX_WARNING_COUNT,
            )
            export_publish_gate_report(notebook_title, publish_gate)
            logger.info(f"发布闸门状态: {'通过' if publish_gate.get('passed') else '未通过'}。")
        else:
            logger.info("当前为学习优先模式：已保留学习图示，跳过漫画、图像任务与发布闸门导出。")

        structured_chapters = []
        current = None
        for section in structured_sections:
            chapter_name = section["chapter_name"]
            if current is None or current["chapter_name"] != chapter_name:
                current = {"chapter_name": chapter_name, "sections": []}
                structured_chapters.append(current)
            current["sections"].append(section)
        export_notebook_index(
            notebook_title,
            plain_chapters,
            structured_chapters,
            quality_report,
            publish_gate,
            include_comic_exports=_is_publish_exports_enabled(),
            include_image_exports=_is_publish_exports_enabled(),
            include_renderable_visuals=True,
        )
        return quality_report

    export_notebook_index(
        notebook_title,
        plain_chapters,
        [],
        None,
        None,
        include_comic_exports=_is_publish_exports_enabled(),
        include_image_exports=_is_publish_exports_enabled(),
        include_renderable_visuals=True,
    )
    return None


def _get_quality_retry_sections(quality_report: dict | None) -> list[dict]:
    if not quality_report:
        return []
    return [
        section
        for section in quality_report.get("sections", [])
        if section.get("error_count", 0) > 0 or section.get("warning_count", 0) > 0
    ]


def _build_quality_retry_messages(issues: list[dict]) -> list[str]:
    messages = [item["message"] for item in issues if item.get("message")]
    if messages:
        return messages
    return ["请修复上一版中质量检查指出的问题。"]


async def _generate_and_save_section(
    client: SafeNotebookClient,
    db: DatabaseManager,
    *,
    notebook_id: str,
    notebook_title: str,
    chapter_name: str,
    section_name: str,
    prompt: str | None = None,
    repair_messages: list[str] | None = None,
    save_status: str = "completed",
    section_plan_override: dict | None = None,
    guide_only: bool = False,
    save_stage_progress: bool = True,
) -> bool:
    stage_prompts = build_stage_prompts(
        chapter_name,
        section_name,
        notebook_title=notebook_title,
        repair_messages=repair_messages,
        section_plan_override=section_plan_override,
    )
    if guide_only:
        stage_prompts = [item for item in stage_prompts if item.get("stage") == "guide"]
        logger.info(f"🪶 已启用 guide-only：{chapter_name} -> {section_name} 仅生成首阶段。")
    stage_prompt_texts = []
    stage_raw_responses = []
    parsed_stage_blocks = []
    prompt_version = PROMPT_VERSION

    for stage_info in stage_prompts:
        stage = stage_info["stage"]
        stage_prompt = stage_info["prompt"]
        logger.info(f"🧱 小节阶段生成: {chapter_name} -> {section_name} [{stage}]")
        stage_prompt_texts.append(f"===== STAGE:{stage} =====\n{stage_prompt}")
        raw_response = await client.ask_with_retry(notebook_id, stage_prompt)
        if not raw_response:
            if stage_info.get("required"):
                logger.error(f"❌ 小节 {section_name} 的阶段 {stage} 生成失败。")
                return False
            logger.warning(f"⚠️ 小节 {section_name} 的阶段 {stage} 未返回内容，跳过该阶段。")
            continue

        stage_raw_responses.append(f"===== STAGE:{stage} =====\n{raw_response}")
        try:
            parsed = parse_structured_response(raw_response, section_name)
        except Exception as parse_error:
            if stage_info.get("required"):
                logger.warning(f"结构化解析失败，回退为 legacy_markdown 存储: {chapter_name} -> {section_name} ({parse_error})")
                db.save_section(
                    notebook_title,
                    chapter_name,
                    section_name,
                    "\n\n".join(stage_prompt_texts) if stage_prompt_texts else (prompt or ""),
                    raw_response,
                    notebook_id=notebook_id,
                    prompt_version="legacy_markdown_fallback_v1",
                    raw_response="\n\n".join(stage_raw_responses),
                    structured_blocks=None,
                    status=save_status,
                )
                return True
            logger.warning(f"阶段 {stage} 结构化解析失败，跳过该阶段: {chapter_name} -> {section_name} ({parse_error})")
            continue

        parsed_stage_blocks.append(parsed["blocks"])
        if save_stage_progress:
            partial_merged = merge_stage_blocks(section_name, parsed_stage_blocks)
            db.save_section_progress(
                notebook_title,
                chapter_name,
                section_name,
                "\n\n".join(stage_prompt_texts) if stage_prompt_texts else (prompt or ""),
                partial_merged["rendered_markdown"],
                notebook_id=notebook_id,
                prompt_version=prompt_version,
                raw_response="\n\n".join(stage_raw_responses),
                structured_blocks=partial_merged["blocks"],
                status=f"stage_progress_{stage}",
            )

    merged = merge_stage_blocks(section_name, parsed_stage_blocks)
    rendered_content = merged["rendered_markdown"]
    structured_blocks = merged["blocks"]

    db.save_section(
        notebook_title,
        chapter_name,
        section_name,
        "\n\n".join(stage_prompt_texts) if stage_prompt_texts else (prompt or ""),
        rendered_content,
        notebook_id=notebook_id,
        prompt_version=prompt_version,
        raw_response="\n\n".join(stage_raw_responses),
        structured_blocks=structured_blocks,
        status=save_status,
    )
    return True


async def rerun_failed_quality_sections(
    client: SafeNotebookClient,
    db: DatabaseManager,
    *,
    notebook_id: str,
    notebook_title: str,
    outline: list,
    initial_quality_report: dict | None = None,
    max_attempts: int = QUALITY_REGEN_MAX_ATTEMPTS,
) -> dict | None:
    quality_report = initial_quality_report or validate_structured_sections(
        db.get_structured_sections(notebook_title, outline=outline),
        notebook_title=notebook_title,
    )
    retry_sections = _get_quality_retry_sections(quality_report)
    if not retry_sections:
        logger.info("质量报告没有错误或警告，无需触发小节重生成。")
        return quality_report

    for attempt in range(1, max_attempts + 1):
        retry_sections = _get_quality_retry_sections(quality_report)
        if not retry_sections:
            break

        logger.warning(
            f"发现 {len(retry_sections)} 个存在错误或警告的小节，开始第 {attempt}/{max_attempts} 轮质量重生成。"
        )
        regenerated_count = 0
        for section_report in retry_sections:
            chapter_name = section_report["chapter_name"]
            section_name = section_report["section_name"]
            logger.info(f"🔁 质量重生成: {chapter_name} -> {section_name}")
            retry_messages = _build_quality_retry_messages(
                section_report.get("issues", []),
            )
            ok = await _generate_and_save_section(
                client,
                db,
                notebook_id=notebook_id,
                notebook_title=notebook_title,
                chapter_name=chapter_name,
                section_name=section_name,
                repair_messages=retry_messages,
                save_status=f"quality_retry_{attempt}",
                section_plan_override=get_outline_section_plan(outline, chapter_name, section_name),
                save_stage_progress=True,
            )
            if ok:
                regenerated_count += 1

        quality_report = export_all_views(db, notebook_title, outline, is_final=False)
        remaining = len(_get_quality_retry_sections(quality_report))
        logger.info(f"第 {attempt} 轮质量重生成结束，剩余 {remaining} 个仍含错误或警告的小节。")

        if remaining == 0:
            break
        if regenerated_count == 0:
            logger.warning("本轮没有成功生成新的替换结果，停止继续重试。")
            break

    final_failed = len(_get_quality_retry_sections(quality_report))
    if final_failed:
        logger.warning(f"含错误或警告的小节在最多 {max_attempts} 轮重生成后仍剩余 {final_failed} 个。")
    else:
        logger.info("所有含错误或警告的小节已重生成到无警告状态。")
    return quality_report

def parse_args():
    parser = argparse.ArgumentParser(description="Entropy Note 学习资料流水线")
    parser.add_argument("--notebook-id", help="直接指定要处理的笔记本 ID")
    parser.add_argument("--notebook-title", help="直接指定要处理的笔记本标题")
    parser.add_argument("--notebook-index", type=int, help="直接指定笔记本列表序号（从 1 开始）")
    parser.add_argument("--force-regenerate", action="store_true", help="即使小节已存在，也按当前提示词重新生成全部小节")
    parser.add_argument("--chapter-title", help="只处理指定章节标题")
    parser.add_argument("--chapter-index", type=int, help="只处理指定章节序号（从 1 开始）")
    parser.add_argument("--section-title", help="只处理指定小节标题；使用时需先限定到单个章节")
    parser.add_argument("--section-index", type=int, help="只处理指定小节序号（从 1 开始）；使用时需先限定到单个章节")
    parser.add_argument("--guide-only", action="store_true", help="仅生成 guide 阶段，便于快速验证单小节首阶段")
    return parser.parse_args()


def _outline_section_count(outline: list) -> int:
    return sum(len(part.get("sections", []) or []) for part in outline or [])


def select_outline_subset(
    outline: list,
    *,
    chapter_title: str | None = None,
    chapter_index: int | None = None,
    section_title: str | None = None,
    section_index: int | None = None,
) -> list:
    if chapter_title and chapter_index is not None:
        raise ValueError("`--chapter-title` 和 `--chapter-index` 不能同时使用。")
    if section_title and section_index is not None:
        raise ValueError("`--section-title` 和 `--section-index` 不能同时使用。")

    selected_outline = outline
    if chapter_title:
        for part in outline:
            if part.get("chapter") == chapter_title:
                selected_outline = [part]
                break
        else:
            raise ValueError(f"未找到指定章节标题: {chapter_title}")
    elif chapter_index is not None:
        if 1 <= chapter_index <= len(outline):
            selected_outline = [outline[chapter_index - 1]]
        else:
            raise ValueError(f"指定的章节序号无效: {chapter_index}")

    if not section_title and section_index is None:
        return selected_outline

    if len(selected_outline) != 1:
        raise ValueError("使用 `--section-title` 或 `--section-index` 前，请先通过 `--chapter-title` 或 `--chapter-index` 限定到单个章节。")

    selected_part = selected_outline[0]
    sections = selected_part.get("sections", []) or []
    if not sections:
        raise ValueError(f"章节《{selected_part.get('chapter', '未知章节')}》下没有可用小节。")

    if section_title:
        for section in sections:
            if section == section_title:
                return [{**selected_part, "sections": [section]}]
        raise ValueError(f"未找到指定小节标题: {section_title}")

    if section_index is not None:
        if 1 <= section_index <= len(sections):
            return [{**selected_part, "sections": [sections[section_index - 1]]}]
        raise ValueError(f"指定的小节序号无效: {section_index}")

    return selected_outline


async def select_notebook(
    client: SafeNotebookClient,
    *,
    preferred_id: str | None = None,
    preferred_title: str | None = None,
    preferred_index: int | None = None,
):
    """交互式选择笔记本"""
    logger.info("正在获取您的笔记本列表...")
    notebooks = await client.list_notebooks()
    
    if not notebooks:
        logger.warning("未找到任何笔记本，请先在网页端创建。")
        return None

    print("\n[发现已有笔记本]")
    for i, nb in enumerate(notebooks, 1):
        print(f"{i}. {nb.title} (ID: {nb.id})")

    if preferred_id:
        for nb in notebooks:
            if nb.id == preferred_id:
                logger.info(f"已按 ID 选择笔记本: {nb.title}")
                return nb
        logger.error(f"未找到指定的笔记本 ID: {preferred_id}")
        return None

    if preferred_title:
        for nb in notebooks:
            if nb.title == preferred_title:
                logger.info(f"已按标题选择笔记本: {nb.title}")
                return nb
        logger.error(f"未找到指定的笔记本标题: {preferred_title}")
        return None

    if preferred_index is not None:
        if 1 <= preferred_index <= len(notebooks):
            selected = notebooks[preferred_index - 1]
            logger.info(f"已按序号选择笔记本: {selected.title}")
            return selected
        logger.error(f"指定的笔记本序号无效: {preferred_index}")
        return None

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
    args = parse_args()
    logger.info("=== Entropy Note 学习资料流水线 ===")
    
    # 初始化核心组件
    db = DatabaseManager()
    client = SafeNotebookClient()
    
    if not await client.ensure_authenticated():
        sys.exit(1)

    if not await client.connect():
        sys.exit(1)

    try:
        # 1. 选择笔记本
        notebook = await select_notebook(
            client,
            preferred_id=args.notebook_id,
            preferred_title=args.notebook_title,
            preferred_index=args.notebook_index,
        )
        if not notebook:
            return
            
        nb_id = notebook.id
        nb_title = notebook.title

        # 2. 提取或读取大纲
        outline = db.get_outline(nb_title)
        if not outline:
            logger.info("未找到大纲缓存，正在请求 AI 提取...")
            outline = await client.extract_outline(nb_id)
            if not outline:
                logger.error("大纲提取失败，流程终止。")
                return
            outline = enrich_outline_with_section_plans(outline, nb_title)
            db.save_outline(nb_title, outline)
        else:
            logger.info("已从数据库读取大纲缓存。")
            normalized_outline = enrich_outline_with_section_plans(outline, nb_title)
            if normalized_outline != outline:
                outline = normalized_outline
                db.save_outline(nb_title, outline)
            else:
                outline = normalized_outline

        try:
            selected_outline = select_outline_subset(
                outline,
                chapter_title=args.chapter_title,
                chapter_index=args.chapter_index,
                section_title=args.section_title,
                section_index=args.section_index,
            )
        except ValueError as exc:
            logger.error(str(exc))
            return

        scoped_run = (
            len(selected_outline) != len(outline)
            or _outline_section_count(selected_outline) != _outline_section_count(outline)
        )
        if scoped_run:
            selected_pairs = [
                f"{part.get('chapter', '未知章节')} -> {section}"
                for part in selected_outline
                for section in (part.get("sections", []) or [])
            ]
            if len(selected_pairs) == 1:
                logger.info(f"已启用单小节测试模式：仅处理 {selected_pairs[0]}")
            else:
                logger.info(
                    "已启用范围限定模式：仅处理 "
                    + "；".join(
                        part.get("chapter", "未知章节") for part in selected_outline
                    )
                )
        export_outline = selected_outline if scoped_run else outline

        status = db.get_generation_status(nb_title, export_outline)
        log_generation_status(nb_title, status)

        if status.get("is_complete") and not args.force_regenerate:
            logger.info("检测到该笔记本所有小节均已生成完成，先进行质量检查，必要时自动重生成未通过小节。")
            quality_report = export_all_views(db, nb_title, export_outline, is_final=False)
            await rerun_failed_quality_sections(
                client,
                db,
                notebook_id=nb_id,
                notebook_title=nb_title,
                outline=export_outline,
                initial_quality_report=quality_report,
            )
            export_all_views(db, nb_title, export_outline, is_final=True)
            return
        if status.get("is_complete") and args.force_regenerate:
            logger.info("已启用强制重生成：即使全部小节已完成，也会按当前提示词重新生成。")
        
        logger.info(f"成功加载 {len(selected_outline)} 个章节结构，准备开始生成剩余内容...")

        # 3. 逐个章节和小节生成 (断点续传 + 安全防封停)
        for part in selected_outline:
            chapter = part.get("chapter", "未知章节")
            sections = part.get("sections", [])
            chapter_status = status.get("chapters", {}).get(chapter, {})

            if chapter_status.get("is_complete") and not args.force_regenerate:
                logger.info(f"⏭️ 整章已完成，跳过: {chapter}")
                continue
            
            for section in sections:
                if db.has_section(nb_title, chapter, section) and not args.force_regenerate:
                    logger.info(f"⏭️ 跳过已存在小节 (断点续传): {chapter} - {section}")
                    continue
                if args.force_regenerate and db.has_section(nb_title, chapter, section):
                    logger.info(f"🔁 强制重生成已存在小节: {chapter} - {section}")

                logger.info(f"正在生成: {chapter} -> {section} ...")
                if await _generate_and_save_section(
                    client,
                    db,
                    notebook_id=nb_id,
                    notebook_title=nb_title,
                    chapter_name=chapter,
                    section_name=section,
                    save_status="guide_only_completed" if args.guide_only else "completed",
                    section_plan_override=get_outline_section_plan(selected_outline, chapter, section),
                    guide_only=args.guide_only,
                    save_stage_progress=True,
                ):
                    # 实时导出进度
                    export_all_views(db, nb_title, export_outline, is_final=False)

        # 4. 最终组装导出
        if scoped_run:
            logger.info("范围限定测试已完成，跳过整本完成度判定与整本级自动重生成。")
            export_all_views(db, nb_title, export_outline, is_final=True)
            return

        final_status = db.get_generation_status(nb_title, outline)
        if not final_status.get("is_complete"):
            missing = final_status.get("missing_sections", [])
            missing_preview = "；".join([f"{chapter} -> {section}" for chapter, section in missing[:5]])
            logger.warning(
                f"仍有 {len(missing)} 个小节未完成，本次先导出当前进度。"
                + (f" 示例缺失项: {missing_preview}" if missing_preview else "")
            )
            export_all_views(db, nb_title, outline, is_final=False)
            return

        logger.info("所有章节生成完毕，开始执行质量检查与未通过小节重生成...")
        quality_report = export_all_views(db, nb_title, outline, is_final=False)
        await rerun_failed_quality_sections(
            client,
            db,
            notebook_id=nb_id,
            notebook_title=nb_title,
            outline=outline,
            initial_quality_report=quality_report,
        )
        logger.info("质量检查与重生成结束，开始导出最终 Markdown 文件...")
        export_all_views(db, nb_title, outline, is_final=True)

    except Exception as e:
        logger.error(f"流水线执行过程中出现未捕获异常: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await client.close()
        logger.info("已安全关闭连接。")

def cli():
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())

if __name__ == "__main__":
    cli()
