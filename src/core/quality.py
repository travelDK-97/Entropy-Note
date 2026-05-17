from __future__ import annotations

import re

from src.config import LEARNING_FIRST_MODE
from src.prompts.section_style import STYLE_LABELS, infer_section_plan
from src.utils.mermaid import inspect_mermaid_code


CORE_BLOCK_TYPES = [
    "background_storyline",
    "definition",
    "intuition_plain_language",
]


def _has_meaningful_text(value: str | None, *, min_len: int = 12) -> bool:
    return bool(value and len(value.strip()) >= min_len)


def _issue(level: str, message: str) -> dict:
    return {"level": level, "message": message}


def _dedupe_issues(issues: list[dict]) -> list[dict]:
    deduped = []
    seen = set()
    for item in issues:
        key = (item.get("level"), item.get("message"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _run_status_meta(run_status: str | None) -> dict:
    status = str(run_status or "").strip()
    stage_limited = status in {"guide_only_completed", "stage_progress_guide"}
    if status == "guide_only_completed":
        label = "仅完成 guide 阶段"
    elif status == "stage_progress_guide":
        label = "guide 阶段进度已保存"
    elif status.startswith("stage_progress_"):
        label = f"阶段进度：{status.removeprefix('stage_progress_')}"
    elif status.startswith("quality_retry_"):
        label = f"质量重生成：第 {status.removeprefix('quality_retry_')} 轮"
    elif status == "completed":
        label = "完整生成"
    else:
        label = status or "未知"
    return {
        "status": status,
        "label": label,
        "stage_limited": stage_limited,
    }


def _formula_has_readable_context(payload: dict, content: str) -> bool:
    if payload.get("variables") or payload.get("conditions"):
        return True
    formula_latex = str(payload.get("formula_latex", "")).strip()
    if "\\text{" in formula_latex or re.search(r"[\u4e00-\u9fff]", formula_latex):
        return True
    if any(token in (content or "") for token in ("变量释义", "核心变量释义", "机制推演", "适用于", "假设")):
        return True
    return False


def _summarize_plan_evidence(blocks: list[dict]) -> tuple[dict, list[str]]:
    counts = {
        "formula_like": 0,
        "visual": 0,
        "core_text": 0,
        "exercise_like": 0,
    }
    for block in blocks:
        block_type = block.get("block_type")
        if block_type in {"formula", "theorem", "proof_or_derivation"}:
            counts["formula_like"] += 1
        if block_type == "renderable_visual":
            counts["visual"] += 1
        if block_type in {"background_storyline", "definition", "intuition_plain_language"}:
            counts["core_text"] += 1
        if block_type in {"exercise_pattern", "pitfall"}:
            counts["exercise_like"] += 1

    evidence = []
    if counts["formula_like"]:
        evidence.append(f"检测到 {counts['formula_like']} 个公式/定理/推导块。")
    if counts["visual"]:
        evidence.append(f"检测到 {counts['visual']} 个可渲染图示块。")
    if counts["core_text"]:
        evidence.append(f"检测到 {counts['core_text']} 个核心正文块。")
    if counts["exercise_like"]:
        evidence.append(f"检测到 {counts['exercise_like']} 个习题/易错点块。")
    if not evidence:
        evidence.append("当前尚未观察到足够的结构化块证据。")
    return counts, evidence


def _analyze_section_plan_consistency(section_plan: dict, blocks: list[dict], *, plan_source: str, run_status: str | None = None) -> dict:
    counts, evidence = _summarize_plan_evidence(blocks)
    run_meta = _run_status_meta(run_status)
    current_style = section_plan.get("style", "mixed")
    suggestions = []
    suggested_style = None
    suggested_derivation_needed = None
    suggested_visual_needed = None

    if run_meta["stage_limited"]:
        evidence.append(f"当前为阶段受限运行：{run_meta['label']}。")

    if current_style == "text_heavy" and counts["formula_like"] >= 2:
        suggested_style = "mixed" if counts["formula_like"] <= 3 else "formula_heavy"
        suggestions.append("生成结果显示推导相关块明显存在，建议回看是否应上调为混合型或公式推导型。")
    elif (not run_meta["stage_limited"]) and current_style == "formula_heavy" and counts["formula_like"] == 0 and counts["core_text"] >= 2:
        suggested_style = "text_heavy"
        suggestions.append("当前几乎没有推导证据，建议回看是否应降为文字推理型。")
    elif (not run_meta["stage_limited"]) and current_style == "mixed" and counts["formula_like"] == 0 and counts["core_text"] >= 2:
        suggested_style = "text_heavy"
        suggestions.append("生成结果更接近正文说明，建议回看是否应降为文字推理型。")

    if not section_plan.get("derivation_needed") and counts["formula_like"] >= 2:
        suggested_derivation_needed = True
        suggestions.append("生成结果包含较多公式/定理/推导块，建议将严谨推导补充设为需要。")
    elif (not run_meta["stage_limited"]) and section_plan.get("derivation_needed") and counts["formula_like"] == 0 and counts["core_text"] >= 2:
        suggested_derivation_needed = False
        suggestions.append("当前缺少推导证据，建议回看是否真的需要独立推导补充层。")

    if not section_plan.get("visual_needed") and counts["visual"] >= 1:
        suggested_visual_needed = True
        suggestions.append("生成结果已出现可渲染图示，建议将图示需求设为需要。")
    elif (not run_meta["stage_limited"]) and section_plan.get("visual_needed") and counts["visual"] == 0 and counts["formula_like"] == 0 and counts["core_text"] >= 2:
        suggested_visual_needed = False
        suggestions.append("当前未看到图示证据且内容以正文说明为主，建议回看是否真的需要图示。")

    review_needed = bool(suggestions)
    suggested_plan = None
    if review_needed:
        suggested_plan = {
            "style": suggested_style or current_style,
            "label": STYLE_LABELS.get(suggested_style or current_style, section_plan.get("label", "混合型")),
            "derivation_needed": (
                suggested_derivation_needed
                if suggested_derivation_needed is not None
                else section_plan.get("derivation_needed")
            ),
            "visual_needed": (
                suggested_visual_needed
                if suggested_visual_needed is not None
                else section_plan.get("visual_needed")
            ),
            "visual_type": section_plan.get("visual_type", "none"),
            "visual_ratio": section_plan.get("visual_ratio", ""),
        }

    return {
        "plan_source": plan_source,
        "review_needed": review_needed,
        "status": ("建议回看" if review_needed else ("阶段受限" if run_meta["stage_limited"] else "基本一致")),
        "evidence": evidence,
        "suggestions": suggestions,
        "suggested_plan": suggested_plan,
        "run_status_label": run_meta["label"],
        "stage_limited": run_meta["stage_limited"],
    }


def _summarize_repair_hints(issues: list[dict], *, limit: int = 3) -> list[str]:
    seen = set()
    hints = []
    for level in ("error", "warning"):
        for item in issues:
            message = str(item.get("message", "")).strip()
            if item.get("level") != level or not message or message in seen:
                continue
            seen.add(message)
            hints.append(message)
            if len(hints) >= limit:
                return hints
    return hints


def _analyze_obsidian_mermaid_readability(mermaid_code: str) -> list[dict]:
    code = (mermaid_code or "").strip()
    if not code:
        return []

    lines = [line.rstrip() for line in code.splitlines() if line.strip()]
    if not lines:
        return []

    chart_start = next(
        (
            line.strip()
            for line in lines
            if not line.strip().startswith("%%{init:")
        ),
        "",
    )
    readable_code = "\n".join(
        line for line in lines if not line.strip().startswith("%%{init:")
    )
    issues = []

    node_ids = set(re.findall(r"\b([A-Za-z][A-Za-z0-9_]*)\s*(?:\[[^\]]*\]|\([^\)]*\)|\{[^}]*\}|>[^<]*<)", readable_code))
    edge_count = len(re.findall(r"-->|---|==>|-.->|-\.->|--o|--x", readable_code))
    subgraph_count = len(re.findall(r"^\s*subgraph\b", readable_code, flags=re.IGNORECASE | re.MULTILINE))

    label_candidates = re.findall(r"\[[^\]]+\]|\([^\)]+\)|\{[^}]+\}|\"[^\"]+\"", readable_code)
    normalized_labels = [
        re.sub(r"<br\s*/?>", "", label).strip("[](){}\" ")
        for label in label_candidates
    ]
    long_labels = [label for label in normalized_labels if len(label) >= 24]
    very_long_labels = [label for label in normalized_labels if len(label) >= 36]

    if chart_start.lower().startswith(("graph lr", "flowchart lr")) and len(node_ids) >= 6:
        issues.append(_issue("warning", "当前图示为横向 LR 布局且节点较多，在 Obsidian 中可能过宽；建议改为 `TD` 或拆成两张图。"))
    if len(node_ids) >= 14:
        issues.append(_issue("warning", f"当前图示节点数约为 {len(node_ids)}，单图信息量偏大；建议按子机制拆图，提升 Obsidian 阅读舒适度。"))
    if edge_count >= 13:
        issues.append(_issue("warning", f"当前图示连线数约为 {edge_count}，关系密度偏高；建议减少交叉关系或拆分主次链路。"))
    if subgraph_count >= 2:
        issues.append(_issue("warning", "当前图示包含多层 subgraph，Obsidian 中容易显得拥挤；建议减少嵌套层级。"))
    if len(long_labels) >= 4:
        issues.append(_issue("warning", "当前图示存在多处较长节点文本，Obsidian 中容易撑宽版面；建议缩短节点文字或主动使用 `<br/>` 断行。"))
    if very_long_labels:
        issues.append(_issue("warning", "当前图示存在过长节点文本，建议改写为关键词短语，再把解释放回图注或正文。"))

    return issues


def _inspect_svg_code(svg_code: str) -> list[dict]:
    code = str(svg_code or "").strip()
    if not code:
        return [_issue("warning", "可渲染图示块缺少有效 `svg_code`，暂时无法直接渲染。")]

    issues = []
    if "<svg" not in code.lower() or "</svg>" not in code.lower():
        issues.append(_issue("warning", "SVG 图示缺少完整 `<svg>...</svg>` 包裹。"))
        return issues
    if "viewBox=" not in code:
        issues.append(_issue("warning", "SVG 图示缺少 `viewBox`，在 Obsidian 中可能难以稳定控制比例。"))
    if "preserveAspectRatio=" not in code:
        issues.append(_issue("warning", "SVG 图示缺少 `preserveAspectRatio`，缩放时可能变形。"))
    if "width=" not in code or "height=" not in code:
        issues.append(_issue("warning", "SVG 图示缺少显式 `width` 或 `height`，显示尺寸可能不稳定。"))
    return issues


def _validate_block(block: dict) -> tuple[list[dict], list[str]]:
    block_type = block.get("block_type", "unknown")
    content = str(block.get("content", "")).strip()
    payload = block.get("payload") or {}
    issues = []
    auto_fixes = []

    if block_type == "background_storyline":
        if not (_has_meaningful_text(payload.get("core_question")) or _has_meaningful_text(payload.get("why_introduced"))):
            issues.append(_issue("warning", "主线/动机块缺少核心问题或引入动机，前后结构感可能不足。"))

    elif block_type == "definition":
        if not _has_meaningful_text(payload.get("concept"), min_len=2):
            issues.append(_issue("error", "定义块缺少 `concept`。"))
        if not _has_meaningful_text(payload.get("concise_definition")):
            issues.append(_issue("error", "定义块缺少 `concise_definition`。"))

    elif block_type == "theorem":
        if not _has_meaningful_text(payload.get("theorem_name"), min_len=2):
            issues.append(_issue("warning", "定理块缺少 `theorem_name`。"))
        if not payload.get("assumptions"):
            issues.append(_issue("error", "定理块缺少成立条件 `assumptions`。"))
        if not _has_meaningful_text(payload.get("conclusion")):
            issues.append(_issue("error", "定理块缺少结论 `conclusion`。"))

    elif block_type == "formula":
        if not _has_meaningful_text(payload.get("formula_latex"), min_len=4):
            issues.append(_issue("error", "公式块缺少 `formula_latex`。"))
        if not payload.get("variables"):
            level = "warning" if _formula_has_readable_context(payload, content) else "error"
            issues.append(_issue(level, "公式块缺少变量释义 `variables`。"))
        if not payload.get("conditions"):
            if re.search(r"(?:假设|适用于|在.+下|若|如果|前提)", content):
                issues.append(_issue("warning", "公式块缺少适用条件 `conditions`。"))

    elif block_type == "intuition_plain_language":
        if not (_has_meaningful_text(payload.get("plain_explanation")) or _has_meaningful_text(content)):
            issues.append(_issue("error", "大白话块缺少 `plain_explanation` 或有效正文。"))
        if not LEARNING_FIRST_MODE and not (
            _has_meaningful_text(payload.get("metaphor")) or _has_meaningful_text(payload.get("visual_scene"))
        ):
            issues.append(_issue("warning", "大白话块缺少类比或视觉场景，不利于后续生成漫画/图像。"))

    elif block_type == "image_generation_task":
        if not _has_meaningful_text(payload.get("prompt")) and not _has_meaningful_text(content):
            issues.append(_issue("warning", "图像任务块缺少主提示词 `prompt`。"))
        if not payload.get("tool_targets"):
            issues.append(_issue("warning", "图像任务块缺少建议工具 `tool_targets`。"))

    elif block_type == "renderable_visual":
        render_format = str(payload.get("render_format", "")).strip().lower()
        svg_code = str(payload.get("svg_code", "")).strip()
        mermaid_code = str(payload.get("mermaid_code", "")).strip()
        if not _has_meaningful_text(payload.get("render_goal"), min_len=4):
            issues.append(_issue("warning", "可渲染图示块缺少 `render_goal`，图示用途不够明确。"))
        if render_format == "svg" or svg_code:
            issues.extend(_inspect_svg_code(svg_code or content))
        else:
            inspected = inspect_mermaid_code(mermaid_code or content)
            if not inspected["sanitized_code"]:
                issues.append(_issue("warning", "可渲染图示块缺少有效 `mermaid_code`，暂时无法直接渲染。"))
            issues.extend(inspected["issues"])
            issues.extend(_analyze_obsidian_mermaid_readability(inspected["sanitized_code"]))
            auto_fixes.extend(inspected["auto_fixes"])

    return issues, auto_fixes


def validate_structured_sections(structured_sections: list[dict], notebook_title: str | None = None) -> dict:
    section_reports = []
    summary = {
        "section_count": 0,
        "passed_count": 0,
        "warning_count": 0,
        "error_count": 0,
        "auto_fix_count": 0,
        "plan_review_count": 0,
    }

    for section in structured_sections:
        chapter_name = section["chapter_name"]
        section_name = section["section_name"]
        blocks = section.get("blocks", [])
        issues = []
        auto_fixes = []

        block_types = {block.get("block_type") for block in blocks}
        run_status = section.get("run_status")
        plan_source = "outline_model" if section.get("section_plan") else "fallback"
        section_plan = infer_section_plan(
            notebook_title,
            chapter_name,
            section_name,
            plan_override=section.get("section_plan"),
        )
        consistency = _analyze_section_plan_consistency(section_plan, blocks, plan_source=plan_source, run_status=run_status)
        for required_type in CORE_BLOCK_TYPES:
            if required_type not in block_types:
                issues.append(_issue("error", f"缺少核心内容块 `{required_type}`。"))

        if (
            section_plan["derivation_needed"]
            and not consistency["stage_limited"]
            and not ({"formula", "theorem", "proof_or_derivation"} & block_types)
        ):
            issues.append(_issue("warning", "本节判定需要严谨推导补充，但未发现公式/定理/推导块。"))

        if "exercise_pattern" not in block_types and "pitfall" not in block_types:
            issues.append(_issue("warning", "未发现习题套路或易错点块。"))

        if section_plan["visual_needed"] and not consistency["stage_limited"] and "renderable_visual" not in block_types:
            issues.append(_issue("warning", "本节判定需要可渲染图示，但当前缺少 `renderable_visual` 块。"))

        for block in blocks:
            block_issues, block_auto_fixes = _validate_block(block)
            issues.extend(block_issues)
            auto_fixes.extend(block_auto_fixes)

        issues = _dedupe_issues(issues)
        error_count = sum(1 for item in issues if item["level"] == "error")
        warning_count = sum(1 for item in issues if item["level"] == "warning")
        auto_fix_count = len(auto_fixes)

        # 从 100 分起扣分，error 扣 15，warning 扣 5，最低 0。
        score = max(0, 100 - error_count * 15 - warning_count * 5)
        passed = error_count == 0

        summary["section_count"] += 1
        summary["passed_count"] += 1 if passed else 0
        summary["warning_count"] += warning_count
        summary["error_count"] += error_count
        summary["auto_fix_count"] += auto_fix_count
        summary["plan_review_count"] += 1 if consistency["review_needed"] else 0

        section_reports.append(
            {
                "chapter_name": chapter_name,
                "section_name": section_name,
                "passed": passed,
                "score": score,
                "error_count": error_count,
                "warning_count": warning_count,
                "auto_fix_count": auto_fix_count,
                "issues": issues,
                "auto_fixes": auto_fixes,
                "block_types": sorted(block_type for block_type in block_types if block_type),
                "derivation_needed": section_plan["derivation_needed"],
                "visual_needed": section_plan["visual_needed"],
                "visual_type": section_plan.get("visual_type", "none"),
                "visual_ratio": section_plan.get("visual_ratio", ""),
                "section_style": section_plan["label"],
                "style_reason": section_plan.get("style_reason", ""),
                "visual_reason": section_plan.get("visual_reason", ""),
                "repair_hints": _summarize_repair_hints(issues),
                "run_status": run_status,
                "run_status_label": consistency["run_status_label"],
                "plan_source": consistency["plan_source"],
                "plan_consistency": consistency["status"],
                "plan_review_needed": consistency["review_needed"],
                "plan_evidence": consistency["evidence"],
                "plan_suggestions": consistency["suggestions"],
                "suggested_plan": consistency["suggested_plan"],
            }
        )

    average_score = 0
    if summary["section_count"] > 0:
        average_score = round(sum(section["score"] for section in section_reports) / summary["section_count"], 2)
    summary["average_score"] = average_score

    chapter_map = {}
    for section in section_reports:
        chapter_name = section["chapter_name"]
        meta = chapter_map.setdefault(
            chapter_name,
            {
                "chapter_name": chapter_name,
                "section_count": 0,
                "passed_count": 0,
                "error_count": 0,
                "warning_count": 0,
                "plan_review_count": 0,
                "sections_to_review": [],
            },
        )
        meta["section_count"] += 1
        meta["passed_count"] += 1 if section["passed"] else 0
        meta["error_count"] += section["error_count"]
        meta["warning_count"] += section["warning_count"]
        meta["plan_review_count"] += 1 if section.get("plan_review_needed") else 0
        if section.get("plan_review_needed"):
            meta["sections_to_review"].append(section["section_name"])

    return {
        "summary": summary,
        "chapters": list(chapter_map.values()),
        "sections": section_reports,
    }


def evaluate_publish_gate(
    quality_report: dict,
    *,
    min_average_score: float = 80,
    max_error_count: int = 0,
    max_warning_count: int = 12,
) -> dict:
    summary = (quality_report or {}).get("summary", {})
    section_count = summary.get("section_count", 0)
    average_score = summary.get("average_score", 0)
    error_count = summary.get("error_count", 0)
    warning_count = summary.get("warning_count", 0)

    reasons = []
    if section_count == 0:
        reasons.append("当前没有可评估的小节，无法进入正式发布。")
    if average_score < min_average_score:
        reasons.append(f"平均分 {average_score} 低于阈值 {min_average_score}。")
    if error_count > max_error_count:
        reasons.append(f"错误数 {error_count} 超过阈值 {max_error_count}。")
    if warning_count > max_warning_count:
        reasons.append(f"警告数 {warning_count} 超过阈值 {max_warning_count}。")

    return {
        "passed": not reasons,
        "thresholds": {
            "min_average_score": min_average_score,
            "max_error_count": max_error_count,
            "max_warning_count": max_warning_count,
        },
        "summary": summary,
        "reasons": reasons,
    }
