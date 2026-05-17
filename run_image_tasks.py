import argparse
from pathlib import Path

from src.core.image_jobs import (
    PromptPackExecutor,
    SUPPORTED_IMAGE_TOOLS,
    discover_latest_image_task_jsonl,
    filter_image_tasks,
    load_image_tasks,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="读取 NotebookLM 导出的图像任务 JSONL，并按目标工具生成可批量执行的提示词包。"
    )
    parser.add_argument(
        "--input",
        help="图像任务 JSONL 路径。默认自动查找 outputs/ 下最新的 *_图像任务.jsonl。",
    )
    parser.add_argument(
        "--tool",
        choices=SUPPORTED_IMAGE_TOOLS,
        help="仅处理指定工具的任务。",
    )
    parser.add_argument(
        "--chapter",
        help="只处理章节名包含该关键词的任务。",
    )
    parser.add_argument(
        "--section",
        help="只处理小节名包含该关键词的任务。",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="最多处理多少条任务。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印筛选结果，不生成文件。",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    input_path = Path(args.input) if args.input else discover_latest_image_task_jsonl()
    tasks = load_image_tasks(input_path)
    filtered_tasks = filter_image_tasks(
        tasks,
        tool=args.tool,
        chapter_keyword=args.chapter,
        section_keyword=args.section,
        limit=args.limit,
    )

    if not filtered_tasks:
        raise SystemExit("筛选后没有可执行的图像任务。")

    executor = PromptPackExecutor()
    summary = executor.prepare(
        filtered_tasks,
        jsonl_path=input_path,
        tool=args.tool,
        dry_run=args.dry_run,
    )

    print(f"来源任务文件: {input_path.resolve()}")
    print(f"筛选后任务数: {summary.total_tasks}")
    print("按工具分组:")
    for tool_name, count in summary.grouped_counts.items():
        print(f"  - {tool_name}: {count}")

    if args.dry_run:
        print("当前为 dry-run 模式，未生成任何文件。")
        return

    print(f"输出目录: {summary.job_dir.resolve()}")
    if summary.manifest_path:
        print(f"Manifest: {summary.manifest_path.resolve()}")
    print(f"已生成任务包数量: {summary.total_outputs}")


if __name__ == "__main__":
    main()
