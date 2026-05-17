from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.config import OUTPUT_DIR

IMAGE_TASK_SUFFIX = "_图像任务.jsonl"
SUPPORTED_IMAGE_TOOLS = ("lovart", "gpt_image_2", "banana_pro")


def _safe_name(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', "_", (value or "").strip())
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned.strip("._") or "untitled"


def _slugify_task(chapter_name: str, section_name: str, title: str, order: int) -> str:
    parts = [_safe_name(chapter_name), _safe_name(section_name), _safe_name(title)]
    return f"{order:03d}_{'_'.join(part for part in parts if part)}"


def infer_notebook_safe_title_from_jsonl(jsonl_path: str | Path) -> str:
    path = Path(jsonl_path)
    name = path.name
    if name.endswith(IMAGE_TASK_SUFFIX):
        return name[: -len(IMAGE_TASK_SUFFIX)]
    return _safe_name(path.stem)


def discover_latest_image_task_jsonl(notebook_keyword: str | None = None) -> Path:
    output_root = Path(OUTPUT_DIR)
    candidates = sorted(output_root.glob(f"*{IMAGE_TASK_SUFFIX}"), key=lambda item: item.stat().st_mtime, reverse=True)
    if notebook_keyword:
        keyword = notebook_keyword.lower()
        candidates = [item for item in candidates if keyword in item.stem.lower()]
    if not candidates:
        raise FileNotFoundError("未找到可用的 *_图像任务.jsonl 文件，请先运行主流程生成图像任务。")
    return candidates[0]


def load_image_tasks(jsonl_path: str | Path) -> list[dict]:
    path = Path(jsonl_path)
    tasks = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise ValueError(f"第 {line_no} 行不是 JSON 对象。")
            if payload.get("task_kind") != "image_generation":
                continue
            prompt = str(payload.get("prompt", "")).strip()
            if not prompt:
                continue
            tasks.append(payload)
    if not tasks:
        raise ValueError("图像任务文件中没有可执行的 image_generation 任务。")
    return tasks


def filter_image_tasks(
    tasks: list[dict],
    *,
    tool: str | None = None,
    chapter_keyword: str | None = None,
    section_keyword: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    filtered = []
    for task in tasks:
        tool_targets = [str(item).strip().lower() for item in task.get("tool_targets", []) if str(item).strip()]
        chapter_name = str(task.get("chapter_name", ""))
        section_name = str(task.get("section_name", ""))

        if tool and tool not in tool_targets:
            continue
        if chapter_keyword and chapter_keyword.lower() not in chapter_name.lower():
            continue
        if section_keyword and section_keyword.lower() not in section_name.lower():
            continue
        filtered.append(task)

    if limit is not None and limit >= 0:
        return filtered[:limit]
    return filtered


def group_tasks_by_tool(tasks: list[dict], tool: str | None = None) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for task in tasks:
        task_tools = [str(item).strip().lower() for item in task.get("tool_targets", []) if str(item).strip()]
        if tool:
            if tool in task_tools:
                grouped.setdefault(tool, []).append(task)
            continue

        for item in task_tools:
            if item in SUPPORTED_IMAGE_TOOLS:
                grouped.setdefault(item, []).append(task)
    return grouped


def _tool_instruction(tool_name: str) -> str:
    if tool_name == "lovart":
        return "建议将主提示词直接作为主输入，保留反向提示词为补充限制，按章批量执行更稳定。"
    if tool_name == "gpt_image_2":
        return "建议优先保留学术准确性、变量关系和空间结构描述，避免过多风格词稀释教学重点。"
    if tool_name == "banana_pro":
        return "建议强调机制示意、流程和结构层次，减少装饰性形容词，保证画面可读性。"
    return "请按目标工具的输入规范手动执行。"


def _render_task_markdown(tool_name: str, task: dict) -> str:
    lines = [
        f"# {task.get('chapter_name', '')} / {task.get('section_name', '')}",
        "",
        f"- 目标工具: {tool_name}",
        f"- 图像类型: {task.get('image_kind', '')}",
        f"- 标题: {task.get('title', '')}",
        f"- 建议说明: {_tool_instruction(tool_name)}",
    ]
    focus_points = task.get("focus_points") or []
    if focus_points:
        lines.append(f"- 重点元素: {'；'.join(str(item) for item in focus_points)}")
    if task.get("source_basis"):
        lines.append(f"- 知识依据: {task['source_basis']}")
    if task.get("background_text"):
        lines.append(f"- 背景主线: {task['background_text']}")
    lines.extend(
        [
            "",
            "## 主提示词",
            "",
            str(task.get("prompt", "")).strip(),
        ]
    )
    negative_prompt = str(task.get("negative_prompt", "")).strip()
    if negative_prompt:
        lines.extend(["", "## 反向提示词", "", negative_prompt])
    return "\n".join(lines).strip() + "\n"


@dataclass
class ExecutionSummary:
    job_dir: Path
    manifest_path: Path | None
    total_tasks: int
    total_outputs: int
    grouped_counts: dict[str, int]


class PromptPackExecutor:
    def __init__(self, output_root: str | Path = OUTPUT_DIR):
        self.output_root = Path(output_root)

    def build_job_dir(self, notebook_safe_title: str) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        job_dir = self.output_root / notebook_safe_title / "图像执行任务" / timestamp
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir

    def prepare(
        self,
        tasks: list[dict],
        *,
        jsonl_path: str | Path,
        tool: str | None = None,
        dry_run: bool = False,
    ) -> ExecutionSummary:
        notebook_safe_title = infer_notebook_safe_title_from_jsonl(jsonl_path)
        grouped = group_tasks_by_tool(tasks, tool=tool)
        grouped_counts = {name: len(items) for name, items in grouped.items()}

        if dry_run:
            return ExecutionSummary(
                job_dir=self.output_root / notebook_safe_title / "图像执行任务" / "dry_run",
                manifest_path=None,
                total_tasks=len(tasks),
                total_outputs=sum(grouped_counts.values()),
                grouped_counts=grouped_counts,
            )

        job_dir = self.build_job_dir(notebook_safe_title)
        manifest = {
            "created_at": datetime.now().isoformat(),
            "source_jsonl": str(Path(jsonl_path).resolve()),
            "notebook_safe_title": notebook_safe_title,
            "tool_filter": tool,
            "grouped_counts": grouped_counts,
            "jobs": [],
        }

        total_outputs = 0
        for tool_name, tool_tasks in grouped.items():
            tool_dir = job_dir / tool_name
            tool_dir.mkdir(parents=True, exist_ok=True)
            batch_lines = [
                f"# {notebook_safe_title} / {tool_name} 批处理任务",
                "",
                f"- 任务数: {len(tool_tasks)}",
                f"- 建议说明: {_tool_instruction(tool_name)}",
                "",
            ]
            for idx, task in enumerate(tool_tasks, start=1):
                slug = _slugify_task(
                    str(task.get("chapter_name", "")),
                    str(task.get("section_name", "")),
                    str(task.get("title", "")),
                    idx,
                )
                json_path = tool_dir / f"{slug}.json"
                md_path = tool_dir / f"{slug}.md"
                task_payload = dict(task)
                task_payload["selected_tool"] = tool_name
                json_path.write_text(json.dumps(task_payload, ensure_ascii=False, indent=2), encoding="utf-8")
                md_path.write_text(_render_task_markdown(tool_name, task_payload), encoding="utf-8")

                batch_lines.extend(
                    [
                        f"## {idx}. {task.get('chapter_name', '')} / {task.get('section_name', '')}",
                        "",
                        f"- 图像类型: {task.get('image_kind', '')}",
                        f"- 标题: {task.get('title', '')}",
                        "",
                        "### 主提示词",
                        "",
                        str(task.get("prompt", "")).strip(),
                        "",
                    ]
                )
                negative_prompt = str(task.get("negative_prompt", "")).strip()
                if negative_prompt:
                    batch_lines.extend(["### 反向提示词", "", negative_prompt, ""])

                manifest["jobs"].append(
                    {
                        "tool_name": tool_name,
                        "json_path": str(json_path),
                        "markdown_path": str(md_path),
                        "chapter_name": task.get("chapter_name", ""),
                        "section_name": task.get("section_name", ""),
                        "title": task.get("title", ""),
                    }
                )
                total_outputs += 1

            (tool_dir / "00_batch_prompts.md").write_text("\n".join(batch_lines).strip() + "\n", encoding="utf-8")

        manifest_path = job_dir / "00_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return ExecutionSummary(
            job_dir=job_dir,
            manifest_path=manifest_path,
            total_tasks=len(tasks),
            total_outputs=total_outputs,
            grouped_counts=grouped_counts,
        )
