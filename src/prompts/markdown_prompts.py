import json
import re

from src.config import LEARNING_FIRST_MODE
from src.prompts.section_style import infer_section_plan
from src.utils.mermaid import format_obsidian_mermaid_code

PROMPT_VERSION = "structured_blocks_v6_obsidian_visual"

BLOCK_TYPE_TITLES = {
    "background_storyline": "核心主线与历史动机",
    "definition": "定义与概念",
    "theorem": "定理与结论",
    "formula": "公式与符号",
    "proof_or_derivation": "严谨推导补充",
    "intuition_plain_language": "大白话直觉",
    "image_generation_task": "图像生成任务",
    "renderable_visual": "可渲染图示",
    "exercise_pattern": "习题套路",
    "pitfall": "易错点与防坑指南",
}

BLOCK_TYPE_ORDER = [
    "background_storyline",
    "definition",
    "theorem",
    "formula",
    "proof_or_derivation",
    "intuition_plain_language",
    "image_generation_task",
    "renderable_visual",
    "exercise_pattern",
    "pitfall",
]

STAGE_BLOCK_TYPES = {
    "guide": [
        "background_storyline",
        "definition",
        "intuition_plain_language",
        "exercise_pattern",
        "pitfall",
    ],
    "derivation": [
        "theorem",
        "formula",
        "proof_or_derivation",
    ],
    "visual": [
        "renderable_visual",
    ],
}


def _normalize_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _repair_latex_escapes(text: str) -> str:
    if not text:
        return ""
    repaired = str(text)
    control_prefixes = {
        "\t": "t",
        "\f": "f",
        "\b": "b",
        "\r": "r",
    }
    for control_char, prefix in control_prefixes.items():
        repaired = re.sub(re.escape(control_char) + r"(?=[A-Za-z])", rf"\\{prefix}", repaired)
    return repaired


def _strip_markdown_markers(text: str) -> str:
    cleaned = re.sub(r"[*_`#>\-]", " ", (text or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" :.-")
    return cleaned


def _first_nonempty_paragraph(content: str) -> str:
    for chunk in re.split(r"\n\s*\n", content or ""):
        cleaned = _strip_markdown_markers(chunk)
        if cleaned:
            return cleaned
    return ""


def _extract_bullet_lines(content: str) -> list[str]:
    return [
        _strip_markdown_markers(line)
        for line in (content or "").splitlines()
        if re.match(r"^\s*(?:[-*]|\d+[.)])\s+", line)
    ]


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        cleaned = str(item or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def _looks_like_theorem_assumption(text: str) -> bool:
    cleaned = _strip_markdown_markers(text)
    if not cleaned:
        return False
    if any(token in cleaned for token in ("条件", "前提", "假设", "其他条件不变")):
        return True
    if len(cleaned) > 40:
        return False
    if any(token in cleaned for token in ("机制", "结论", "意义", "说明", "因此", "可得", "推动", "导致")):
        return False
    return bool(
        re.search(
            r"(仅.+变动|.+不变|同时变动|当.+时|若.+|如果.+|在.+下|只要.+)",
            cleaned,
        )
    )


def _extract_definition_payload_from_content(content: str, block_title: str) -> dict | None:
    content = _repair_latex_escapes(content)
    concept = ""
    concise_definition = ""
    key_points = []

    concept_match = re.search(r"\*\*概念\*\*[:：]\s*(.+)", content)
    if concept_match:
        concept = _strip_markdown_markers(concept_match.group(1))
    if not concept:
        title_head = _strip_markdown_markers(block_title).split("：")[0].split(":")[0]
        if title_head and len(title_head) <= 24:
            concept = title_head

    def_match = re.search(r"\*\*定义\*\*[:：]\s*(.+)", content)
    if def_match:
        concise_definition = _strip_markdown_markers(def_match.group(1))
    if not concise_definition:
        paragraph = _first_nonempty_paragraph(content)
        concise_definition = paragraph[:160].strip()

    key_points = [item for item in _extract_bullet_lines(content)[:4] if item]
    payload = {}
    if concept:
        payload["concept"] = concept
    if concise_definition:
        payload["concise_definition"] = concise_definition
    if key_points:
        payload["key_points"] = key_points
    return payload or None


def _extract_theorem_payload_from_content(content: str, block_title: str) -> dict | None:
    content = _repair_latex_escapes(content)
    theorem_name = _strip_markdown_markers(block_title)
    assumptions = []
    conclusion = ""
    significance = ""

    if not theorem_name:
        first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
        theorem_name = _strip_markdown_markers(first_line)

    for line in content.splitlines():
        cleaned = _strip_markdown_markers(line)
        if not cleaned:
            continue
        if _looks_like_theorem_assumption(cleaned):
            assumptions.append(cleaned)
        elif any(token in cleaned for token in ("结论", "因此", "可得")) and not conclusion:
            conclusion = cleaned
        elif any(token in cleaned for token in ("意义", "作用", "说明")) and not significance:
            significance = cleaned

    if not assumptions:
        for item in _extract_bullet_lines(content):
            if _looks_like_theorem_assumption(item):
                assumptions.append(item)

    assumptions = _dedupe_keep_order(assumptions)

    if not conclusion:
        paragraph = _first_nonempty_paragraph(content)
        conclusion = paragraph[:180].strip()

    payload = {}
    if theorem_name:
        payload["theorem_name"] = theorem_name
    if assumptions:
        payload["assumptions"] = assumptions[:3]
    if conclusion:
        payload["conclusion"] = conclusion
    if significance:
        payload["significance"] = significance
    return payload or None


def _extract_formula_payload_from_content(content: str, block_title: str) -> dict | None:
    content = _repair_latex_escapes(content)
    display_formula = re.search(r"\$\$([\s\S]*?)\$\$", content)
    inline_formula = re.search(r"\$(.+?)\$", content)
    formula_latex = ""
    if display_formula:
        formula_latex = f"$${display_formula.group(1).strip()}$$"
    elif inline_formula:
        formula_latex = f"${inline_formula.group(1).strip()}$"

    variables = []
    for symbol, meaning in re.findall(r"[-*]\s*`([^`]+)`\s*[:：]\s*(.+)", content):
        variables.append({"symbol": symbol.strip(), "meaning": _strip_markdown_markers(meaning)})
    for symbol, meaning in re.findall(r"[-*]\s*\$([^$]+)\$\s*(?:\([^)]*\))?\s*[:：]\s*(.+)", content):
        variables.append({"symbol": symbol.strip(), "meaning": _strip_markdown_markers(meaning)})
    for symbol, meaning in re.findall(r"[-*]\s*([A-Za-z][A-Za-z0-9_]*)\s*(?:\([^)]*\))?\s*[:：]\s*(.+)", content):
        variables.append({"symbol": symbol.strip(), "meaning": _strip_markdown_markers(meaning)})
    for label, meaning in re.findall(r"[-*]\s*\*\*([^*]+)\*\*\s*[:：]\s*(.+)", content):
        variables.append({"symbol": _strip_markdown_markers(label), "meaning": _strip_markdown_markers(meaning)})
    for meaning, symbol in re.findall(r"([^\n，。；;:：$]{2,16})\s*\$([A-Za-z][A-Za-z0-9_]*)\$", content):
        clean_meaning = _strip_markdown_markers(meaning)
        if clean_meaning and len(clean_meaning) <= 16:
            variables.append({"symbol": symbol.strip(), "meaning": clean_meaning})
    title_acronyms = re.findall(r"\b([A-Z]{2,8})\b", block_title or "")
    for acronym in title_acronyms:
        variables.append({"symbol": acronym, "meaning": _strip_markdown_markers(block_title)})
    deduped_variables = []
    seen_symbols = set()
    for item in variables:
        symbol = item["symbol"]
        if symbol in seen_symbols:
            continue
        seen_symbols.add(symbol)
        deduped_variables.append(item)

    conditions = []
    for line in content.splitlines():
        cleaned = _strip_markdown_markers(line)
        if any(token in cleaned for token in ("条件", "适用", "前提", "假设")):
            conditions.append(cleaned)
    for sentence in re.findall(r"((?:在|当|若|如果|假设|适用于)[^。！？\n]{6,120})", content):
        cleaned = _strip_markdown_markers(sentence)
        if cleaned and cleaned not in conditions:
            conditions.append(cleaned)

    usage = ""
    paragraph = _first_nonempty_paragraph(re.sub(r"\$\$[\s\S]*?\$\$", " ", content))
    if paragraph:
        usage = paragraph[:180].strip()

    payload = {}
    if formula_latex:
        payload["formula_latex"] = formula_latex
    if deduped_variables:
        payload["variables"] = deduped_variables[:6]
    if conditions:
        payload["conditions"] = conditions[:4]
    if usage:
        payload["usage"] = usage
    return payload or None


def _extract_intuition_payload_from_content(content: str) -> dict | None:
    content = _repair_latex_escapes(content)
    plain_explanation = _first_nonempty_paragraph(content)
    metaphor = ""
    visual_scene = ""
    for line in content.splitlines():
        cleaned = _strip_markdown_markers(line)
        if not cleaned:
            continue
        if any(token in cleaned for token in ("就像", "好比", "想象成", "可以把")) and not metaphor:
            metaphor = cleaned
        if any(token in cleaned for token in ("画面", "场景", "像是", "仿佛")) and not visual_scene:
            visual_scene = cleaned
    payload = {}
    if plain_explanation:
        payload["plain_explanation"] = plain_explanation
    if metaphor:
        payload["metaphor"] = metaphor
    if visual_scene:
        payload["visual_scene"] = visual_scene
    return payload or None


def _extract_background_payload_from_content(content: str) -> dict | None:
    content = _repair_latex_escapes(content)
    first_paragraph = _first_nonempty_paragraph(content)
    payload = {}
    if first_paragraph:
        payload["why_introduced"] = first_paragraph[:180].strip()
    question_match = re.search(r"(为什么[^。！？\n]*[。！？]?)", content)
    if question_match:
        payload["core_question"] = _strip_markdown_markers(question_match.group(1))
    prerequisite_match = re.search(r"(理解[^。！？\n]*需要[^。！？\n]*[。！？]?)", content)
    if prerequisite_match:
        payload["prerequisite"] = _strip_markdown_markers(prerequisite_match.group(1))
    return payload or None


def _infer_visual_render_goal(block_title: str, mermaid_code: str, caption: str) -> str:
    clean_title = _strip_markdown_markers(block_title)
    clean_caption = _strip_markdown_markers(caption)
    code = mermaid_code or ""

    if clean_caption and len(clean_caption) >= 8:
        return clean_caption[:80]

    signals = []
    if any(token in code for token in ("需求", "供给")):
        signals.append("供求关系")
    if any(token in code for token in ("均衡", "Pe", "Qe")):
        signals.append("均衡结果")
    if any(token in code for token in ("过剩", "短缺", "回归", "调整")):
        signals.append("价格调节机制")
    if any(token in code for token in ("同向", "反向", "不确定", "单因素", "同时变动")):
        signals.append("比较静态变化")

    signals = _dedupe_keep_order(signals)
    if clean_title and signals:
        return f"帮助理解{clean_title}中的{'、'.join(signals)}。"
    if clean_title:
        return f"帮助理解{clean_title}的核心关系。"
    if signals:
        return f"帮助理解{'、'.join(signals)}。"
    return ""


def _extract_svg_code(content: str) -> str:
    match = re.search(r"(<svg[\s\S]*?</svg>)", content or "", re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _svg_ratio_dimensions(ratio_hint: str | None) -> tuple[int, int]:
    ratio = str(ratio_hint or "").strip().lower()
    if ratio == "landscape_16_9":
        return 1600, 900
    if ratio == "square":
        return 1000, 1000
    return 1200, 900


def _parse_svg_numeric_attr(svg_tag: str, attr_name: str) -> int | None:
    match = re.search(rf'\b{attr_name}\s*=\s*"([0-9.]+)(?:px)?"', svg_tag, re.IGNORECASE)
    if not match:
        return None
    try:
        return max(int(float(match.group(1))), 1)
    except ValueError:
        return None


def _normalize_svg_code(svg_code: str, ratio_hint: str | None = None) -> str:
    code = str(svg_code or "").strip()
    if not code:
        return ""

    svg_match = re.search(r"<svg\b[^>]*>", code, re.IGNORECASE)
    if not svg_match:
        return code

    svg_tag = svg_match.group(0)
    width_default, height_default = _svg_ratio_dimensions(ratio_hint)

    if "viewBox=" in svg_tag:
        viewbox_match = re.search(
            r'viewBox\s*=\s*"[^"]*?([0-9.]+)\s+([0-9.]+)\s*$',
            svg_tag,
            re.IGNORECASE,
        )
        if viewbox_match:
            try:
                width_default = max(int(float(viewbox_match.group(1))), 1)
                height_default = max(int(float(viewbox_match.group(2))), 1)
            except ValueError:
                width_default, height_default = _svg_ratio_dimensions(ratio_hint)

    width_value = _parse_svg_numeric_attr(svg_tag, "width") or width_default
    height_value = _parse_svg_numeric_attr(svg_tag, "height") or height_default

    attrs_to_add = []
    if "xmlns=" not in svg_tag.lower():
        attrs_to_add.append('xmlns="http://www.w3.org/2000/svg"')
    if "viewBox=" not in svg_tag:
        attrs_to_add.append(f'viewBox="0 0 {width_value} {height_value}"')
    if "width=" not in svg_tag:
        attrs_to_add.append(f'width="{width_value}"')
    if "height=" not in svg_tag:
        attrs_to_add.append(f'height="{height_value}"')
    if "preserveAspectRatio=" not in svg_tag:
        attrs_to_add.append('preserveAspectRatio="xMidYMid meet"')

    if not attrs_to_add:
        return code

    normalized_tag = svg_tag[:-1] + " " + " ".join(attrs_to_add) + ">"
    return code.replace(svg_tag, normalized_tag, 1)


def _extract_visual_payload_from_content(content: str, block_title: str) -> dict | None:
    content = _repair_latex_escapes(content)
    ratio_match = re.search(r"(?:ratio_hint|建议比例|图示比例)\s*[:：]\s*(square|landscape_4_3|landscape_16_9)", content, re.IGNORECASE)
    ratio_hint = ratio_match.group(1).strip() if ratio_match else ""
    svg_code = _normalize_svg_code(_extract_svg_code(content), ratio_hint)
    mermaid_code = ""
    if not svg_code:
        mermaid_code = format_obsidian_mermaid_code(content)
    if not svg_code and not mermaid_code:
        fence_match = re.search(r"```mermaid\s*([\s\S]*?)```", content, re.IGNORECASE)
        if fence_match:
            mermaid_code = format_obsidian_mermaid_code(fence_match.group(1))

    payload = {}
    if block_title:
        payload["title"] = _strip_markdown_markers(block_title)
    goal_match = re.search(r"(?:图示目标|render_goal)\s*[:：]\s*(.+)", content, re.IGNORECASE)
    caption_match = re.search(r"(?:图注|caption)\s*[:：]\s*(.+)", content, re.IGNORECASE)
    note_matches = re.findall(r"(?:说明|备注|notes?)\s*[:：]\s*(.+)", content, re.IGNORECASE)
    if goal_match:
        payload["render_goal"] = _strip_markdown_markers(goal_match.group(1))
    if caption_match:
        payload["caption"] = _strip_markdown_markers(caption_match.group(1))
    if note_matches:
        payload["notes"] = [_strip_markdown_markers(item) for item in note_matches if _strip_markdown_markers(item)]

    render_format_match = re.search(r"(?:render_format|渲染格式)\s*[:：]\s*(svg|mermaid)", content, re.IGNORECASE)
    if render_format_match:
        payload["render_format"] = render_format_match.group(1).lower()
    if ratio_hint:
        payload["ratio_hint"] = ratio_hint

    if svg_code:
        payload["svg_code"] = svg_code
        payload["render_format"] = "svg"
        payload.setdefault("visual_kind", "svg_diagram")
    elif mermaid_code:
        payload["mermaid_code"] = mermaid_code
        payload["render_format"] = "mermaid"
        first_chart_line = next(
            (line.strip() for line in mermaid_code.splitlines() if line.strip() and not line.strip().startswith("%%{init:")),
            "",
        )
        if first_chart_line.lower().startswith(("graph td", "flowchart td")):
            payload["visual_kind"] = "flowchart"
        elif first_chart_line.lower().startswith(("graph lr", "flowchart lr")):
            payload["visual_kind"] = "flowchart"
        elif first_chart_line.lower().startswith("sequencediagram"):
            payload["visual_kind"] = "sequenceDiagram"
        else:
            payload["visual_kind"] = "mermaid_diagram"
    if not payload.get("render_goal"):
        inferred_goal = _infer_visual_render_goal(
            block_title,
            payload.get("mermaid_code", ""),
            payload.get("caption", ""),
        )
        if inferred_goal:
            payload["render_goal"] = inferred_goal
    return payload or None


def _enrich_payload_from_content(block_type: str, payload: dict | None, content: str, block_title: str) -> dict | None:
    current = dict(payload or {})
    extractor = None
    if block_type == "definition":
        extractor = _extract_definition_payload_from_content(content, block_title)
    elif block_type == "theorem":
        extractor = _extract_theorem_payload_from_content(content, block_title)
    elif block_type == "formula":
        extractor = _extract_formula_payload_from_content(content, block_title)
    elif block_type == "intuition_plain_language":
        extractor = _extract_intuition_payload_from_content(content)
    elif block_type == "background_storyline":
        extractor = _extract_background_payload_from_content(content)
    elif block_type == "renderable_visual":
        extractor = _extract_visual_payload_from_content(content, block_title)
    if extractor:
        for key, value in extractor.items():
            if key not in current or not current.get(key):
                current[key] = value
    return current or None


def enrich_block_for_reading(block: dict) -> dict:
    block_type = str(block.get("block_type", "")).strip()
    block_title = str(block.get("block_title") or BLOCK_TYPE_TITLES.get(block_type, "")).strip()
    content = _repair_latex_escapes(str(block.get("content", "")).strip())
    payload = _normalize_payload(block_type, block.get("payload"), content)
    payload = _enrich_payload_from_content(block_type, payload, content, block_title)
    if block_type == "renderable_visual" and payload:
        content = _content_from_payload(block_type, payload)
    elif not content and payload:
        content = _content_from_payload(block_type, payload)
    return {
        **block,
        "block_type": block_type,
        "block_title": block_title or block.get("block_title"),
        "content": content,
        "payload": payload,
    }


def _normalize_payload(block_type: str, payload, content: str) -> dict | None:
    if not isinstance(payload, dict):
        return None

    normalized = {}
    if block_type == "definition":
        concept = str(payload.get("concept", "")).strip()
        concise_definition = str(payload.get("concise_definition", "")).strip()
        key_points = _normalize_list(payload.get("key_points"))
        if concept:
            normalized["concept"] = concept
        if concise_definition:
            normalized["concise_definition"] = concise_definition
        if key_points:
            normalized["key_points"] = key_points

    elif block_type == "theorem":
        theorem_name = str(payload.get("theorem_name", "")).strip()
        assumptions = _normalize_list(payload.get("assumptions"))
        conclusion = str(payload.get("conclusion", "")).strip()
        significance = str(payload.get("significance", "")).strip()
        if theorem_name:
            normalized["theorem_name"] = theorem_name
        if assumptions:
            normalized["assumptions"] = assumptions
        if conclusion:
            normalized["conclusion"] = conclusion
        if significance:
            normalized["significance"] = significance

    elif block_type == "formula":
        formula_latex = _repair_latex_escapes(str(payload.get("formula_latex", "")).strip())
        variables = payload.get("variables")
        conditions = _normalize_list(payload.get("conditions"))
        usage = _repair_latex_escapes(str(payload.get("usage", "")).strip())
        normalized_variables = []
        if isinstance(variables, list):
            for item in variables:
                if not isinstance(item, dict):
                    continue
                symbol = _repair_latex_escapes(str(item.get("symbol", "")).strip())
                meaning = _repair_latex_escapes(str(item.get("meaning", "")).strip())
                if symbol and meaning:
                    normalized_variables.append({"symbol": symbol, "meaning": meaning})
        if formula_latex:
            normalized["formula_latex"] = formula_latex
        if normalized_variables:
            normalized["variables"] = normalized_variables
        if conditions:
            normalized["conditions"] = conditions
        if usage:
            normalized["usage"] = usage

    elif block_type == "intuition_plain_language":
        plain_explanation = str(payload.get("plain_explanation", "")).strip()
        metaphor = str(payload.get("metaphor", "")).strip()
        visual_scene = str(payload.get("visual_scene", "")).strip()
        comic_prompt = str(payload.get("comic_prompt", "")).strip()
        if plain_explanation:
            normalized["plain_explanation"] = plain_explanation
        if metaphor:
            normalized["metaphor"] = metaphor
        if visual_scene:
            normalized["visual_scene"] = visual_scene
        if comic_prompt:
            normalized["comic_prompt"] = comic_prompt

    elif block_type == "image_generation_task":
        image_kind = str(payload.get("image_kind", "")).strip()
        tool_targets = _normalize_list(payload.get("tool_targets"))
        prompt = str(payload.get("prompt", "")).strip()
        negative_prompt = str(payload.get("negative_prompt", "")).strip()
        focus_points = _normalize_list(payload.get("focus_points"))
        source_basis = str(payload.get("source_basis", "")).strip()
        if image_kind:
            normalized["image_kind"] = image_kind
        if tool_targets:
            normalized["tool_targets"] = tool_targets
        if prompt:
            normalized["prompt"] = prompt
        if negative_prompt:
            normalized["negative_prompt"] = negative_prompt
        if focus_points:
            normalized["focus_points"] = focus_points
        if source_basis:
            normalized["source_basis"] = source_basis

    elif block_type == "renderable_visual":
        visual_kind = str(payload.get("visual_kind", "")).strip()
        render_format = str(payload.get("render_format", "")).strip().lower()
        title = str(payload.get("title", "")).strip()
        render_goal = str(payload.get("render_goal", "")).strip()
        mermaid_code = format_obsidian_mermaid_code(str(payload.get("mermaid_code", "")).strip())
        ratio_hint = str(payload.get("ratio_hint", "")).strip()
        svg_code = _normalize_svg_code(str(payload.get("svg_code", "")).strip(), ratio_hint)
        caption = str(payload.get("caption", "")).strip()
        notes = _normalize_list(payload.get("notes"))
        if not render_format:
            render_format = "svg" if svg_code else ("mermaid" if mermaid_code else "")
        if visual_kind:
            normalized["visual_kind"] = visual_kind
        if render_format:
            normalized["render_format"] = render_format
        if title:
            normalized["title"] = title
        if render_goal:
            normalized["render_goal"] = render_goal
        if mermaid_code:
            normalized["mermaid_code"] = mermaid_code
        if svg_code:
            normalized["svg_code"] = svg_code
        if ratio_hint:
            normalized["ratio_hint"] = ratio_hint
        if caption:
            normalized["caption"] = caption
        if notes:
            normalized["notes"] = notes

    elif block_type == "background_storyline":
        core_question = str(payload.get("core_question", "")).strip()
        why_introduced = str(payload.get("why_introduced", "")).strip()
        prerequisite = str(payload.get("prerequisite", "")).strip()
        if core_question:
            normalized["core_question"] = core_question
        if why_introduced:
            normalized["why_introduced"] = why_introduced
        if prerequisite:
            normalized["prerequisite"] = prerequisite

    return normalized or None


def _content_from_payload(block_type: str, payload: dict | None) -> str:
    if not payload:
        return ""

    lines = []
    if block_type == "definition":
        if payload.get("concept"):
            lines.append(f"**概念**: {payload['concept']}")
        if payload.get("concise_definition"):
            lines.append(f"**定义**: {payload['concise_definition']}")
        for point in payload.get("key_points", []):
            lines.append(f"- {point}")

    elif block_type == "theorem":
        if payload.get("theorem_name"):
            lines.append(f"**定理名称**: {payload['theorem_name']}")
        if payload.get("assumptions"):
            lines.append("**成立条件**:")
            lines.extend([f"- {item}" for item in payload["assumptions"]])
        if payload.get("conclusion"):
            lines.append(f"**结论**: {payload['conclusion']}")
        if payload.get("significance"):
            lines.append(f"**意义**: {payload['significance']}")

    elif block_type == "formula":
        if payload.get("formula_latex"):
            lines.append(f"**公式**:\n{_repair_latex_escapes(payload['formula_latex'])}")
        if payload.get("variables"):
            lines.append("**变量释义**:")
            lines.extend([f"- `{item['symbol']}`: {item['meaning']}" for item in payload["variables"]])
        if payload.get("conditions"):
            lines.append("**适用条件**:")
            lines.extend([f"- {item}" for item in payload["conditions"]])
        if payload.get("usage"):
            lines.append(f"**使用说明**: {payload['usage']}")

    elif block_type == "intuition_plain_language":
        if payload.get("plain_explanation"):
            lines.append(f"**大白话**: {payload['plain_explanation']}")
        if payload.get("metaphor"):
            lines.append(f"**类比**: {payload['metaphor']}")
        if payload.get("visual_scene"):
            lines.append(f"**画面感**: {payload['visual_scene']}")
        if payload.get("comic_prompt"):
            lines.append(f"**漫画提示词草稿**: {payload['comic_prompt']}")

    elif block_type == "image_generation_task":
        if payload.get("image_kind"):
            lines.append(f"**任务类型**: {payload['image_kind']}")
        if payload.get("tool_targets"):
            lines.append(f"**建议工具**: {', '.join(payload['tool_targets'])}")
        if payload.get("focus_points"):
            lines.append("**重点元素**:")
            lines.extend([f"- {item}" for item in payload["focus_points"]])
        if payload.get("prompt"):
            lines.append(f"**主提示词**: {payload['prompt']}")
        if payload.get("negative_prompt"):
            lines.append(f"**反向提示词**: {payload['negative_prompt']}")
        if payload.get("source_basis"):
            lines.append(f"**知识依据**: {payload['source_basis']}")

    elif block_type == "renderable_visual":
        if payload.get("visual_kind"):
            lines.append(f"**图示类型**: {payload['visual_kind']}")
        if payload.get("render_format"):
            lines.append(f"**渲染格式**: {payload['render_format']}")
        if payload.get("ratio_hint"):
            lines.append(f"**建议比例**: {payload['ratio_hint']}")
        if payload.get("title"):
            lines.append(f"**图示标题**: {payload['title']}")
        if payload.get("render_goal"):
            lines.append(f"**图示目标**: {payload['render_goal']}")
        if payload.get("caption"):
            lines.append(f"**图注**: {payload['caption']}")
        if payload.get("notes"):
            lines.append("**补充说明**:")
            lines.extend([f"- {item}" for item in payload["notes"]])
        if payload.get("svg_code"):
            lines.append("**SVG 图示**:")
            lines.append(payload["svg_code"])
        elif payload.get("mermaid_code"):
            lines.append("**Mermaid 图示**:")
            lines.append("```mermaid")
            lines.append(format_obsidian_mermaid_code(payload["mermaid_code"]))
            lines.append("```")

    elif block_type == "background_storyline":
        if payload.get("core_question"):
            lines.append(f"**核心问题**: {payload['core_question']}")
        if payload.get("why_introduced"):
            lines.append(f"**引入动机**: {payload['why_introduced']}")
        if payload.get("prerequisite"):
            lines.append(f"**前置知识**: {payload['prerequisite']}")

    return "\n".join(lines).strip()


def _stage_schema_text(section_name: str, allowed_block_types: list[str]) -> str:
    type_lines = "\n".join(f"   - {item}" for item in allowed_block_types)
    return f"""你必须输出一个 JSON 对象，且只能输出 JSON，不要输出解释、寒暄、Markdown 代码块标记。

JSON 格式严格如下：
{{
  "section_title": "{section_name}",
  "blocks": [
    {{
      "block_type": "{allowed_block_types[0]}",
      "block_title": "...",
      "content": "...",
      "payload": {{}}
    }}
  ]
}}

输出要求：
1. `section_title` 必须是 `{section_name}`。
2. `blocks` 是数组，按内容逻辑排序。
3. `block_type` 只能从以下值中选择：
{type_lines}
4. 每个 block 都必须包含：
   - `block_type`
   - `block_title`
   - `content`
   - `payload`
5. `content` 使用 Markdown 文本，可包含列表、加粗和数学公式，但不要再嵌套 JSON。
"""


def _repair_note_text(repair_messages: list[str] | None) -> str:
    if not repair_messages:
        return ""
    issue_lines = "\n".join(f"- {item}" for item in repair_messages if item.strip())
    if not issue_lines:
        return ""
    return (
        "\n额外修正要求：\n"
        "你上一版在质量检查中存在问题。请直接输出该阶段的完整新版结构化 JSON，并优先修复以下问题：\n"
        f"{issue_lines}\n"
    )


def _shared_prompt_head(
    chapter_name: str,
    section_name: str,
    notebook_title: str | None = None,
    *,
    section_plan_override: dict | None = None,
) -> tuple[dict, str]:
    section_plan = infer_section_plan(
        notebook_title,
        chapter_name,
        section_name,
        plan_override=section_plan_override,
    )
    learning_mode_note = ""
    if LEARNING_FIRST_MODE:
        learning_mode_note = """
当前任务以“个人学习可读性”为第一优先级，而不是发布展示。
- 优先覆盖：background_storyline、definition、intuition_plain_language、exercise_pattern、pitfall
- 不要输出 `image_generation_task`
- `intuition_plain_language.payload` 中不要填写 `comic_prompt`
- 不要因为追求简洁就省略定义、公式、机制、条件、易错点；如果资料里明确出现了这些内容，必须系统整理出来
- 输出目标是一份“快速学习指南”，强调结构化梳理与高密度提炼，而不是考前口语化速记
"""
    head = f"""你是一位资深学科导师，同时也是学习资料编辑。请基于你拥有的全部资料，为【{chapter_name}】下属的【{section_name}】生成结构化学习内容。
我的习惯：依赖直觉、机制推演和全局大局观；请补充必要的公式，并使用标准 Markdown 数学格式（`$...$` 或 `$$...$$`）。
请牢记：你输出的是“给人直接阅读的学习资料底稿”，不是给数据库看的字段样例。每个 block 的 `content` 必须本身就是自然、顺畅、适合直接放进 Markdown 文档阅读的中文内容。
{learning_mode_note}

本节风格判定：{section_plan['label']}
请按以下侧重点组织内容：
{section_plan['guidance']}

本节是否需要“严谨推导补充”：{'是' if section_plan['derivation_needed'] else '否'}
说明：{section_plan['derivation_guidance']}

本节是否需要“可渲染图示”：{'是' if section_plan['visual_needed'] else '否'}
说明：{section_plan['visual_guidance']}
本节首判图示类型：{section_plan.get('visual_type', 'none')}
本节首判图示比例：{section_plan.get('visual_ratio') or '未指定'}
"""
    return section_plan, head


def get_markdown_prompt(chapter_name: str, section_name: str, notebook_title: str | None = None) -> str:
    """兼容旧调用：默认返回通俗主正文阶段提示词。"""
    return get_stage_prompt("guide", chapter_name, section_name, notebook_title=notebook_title)


def get_stage_prompt(
    stage: str,
    chapter_name: str,
    section_name: str,
    *,
    notebook_title: str | None = None,
    repair_messages: list[str] | None = None,
    section_plan_override: dict | None = None,
) -> str:
    section_plan, head = _shared_prompt_head(
        chapter_name,
        section_name,
        notebook_title=notebook_title,
        section_plan_override=section_plan_override,
    )
    repair_note = _repair_note_text(repair_messages)

    if stage == "guide":
        allowed_block_types = STAGE_BLOCK_TYPES["guide"]
        stage_note = """
当前只生成“快速学习指南”的通俗主正文，不要生成严谨推导补充，也不要生成可渲染图示。
- 重点覆盖：background_storyline、definition、intuition_plain_language、exercise_pattern、pitfall
- 正文要通顺、自然、可一目十行，适合先建立主线和大意
- 如果不得不提到公式，只能轻量点到为止，不要展开长推导
"""
    elif stage == "derivation":
        allowed_block_types = STAGE_BLOCK_TYPES["derivation"]
        stage_note = """
当前只生成“严谨推导补充”层，不要重复生成通俗主正文，也不要生成可渲染图示。
- 只在本节确实需要严谨推导补充时输出内容；如果材料里没有足够的公式/定理/推导，可返回空的 `blocks`
- 重点覆盖：formula、theorem、proof_or_derivation
- 明确写出变量释义、适用条件、关键推导步骤和易混点
- 如果输出 `theorem`，其 `payload` 至少补齐：`theorem_name`、`assumptions`、`conclusion`
- `assumptions` 请用 1 到 3 条短句明确写出成立前提、比较前提或“其他条件不变”等约束
"""
    elif stage == "visual":
        allowed_block_types = STAGE_BLOCK_TYPES["visual"]
        if str(section_plan.get("visual_type", "")).startswith("svg_"):
            stage_note = f"""
当前只生成“可渲染图示”层，不要重复生成通俗主正文，也不要生成严谨推导补充。
- 只在本节确实需要图示时输出内容；如果图示并不能显著降低理解成本，可返回空的 `blocks`
- 本节首判要求优先输出 SVG，而不是 Mermaid 框图
- 图示应服务于理解曲线、坐标轴、均衡点、预算线、无差异曲线或效应分解，不要退化成纯文字框图
- 请在 `payload.svg_code` 中给出完整内联 SVG，包含 `xmlns`、`viewBox`、`width`、`height`、`preserveAspectRatio`
- 建议比例必须服从首判：`{section_plan.get('visual_ratio') or 'landscape_4_3'}`
- 经济学图优先使用标准横纵坐标、短标签、箭头、点位与简洁注释，避免把整段解释塞进图中
- `payload` 至少补齐：`title`、`render_goal`、`render_format`、`visual_kind`、`svg_code`、`ratio_hint`
- `render_format` 固定写 `svg`
- `visual_kind` 建议直接写首判类型：`{section_plan.get('visual_type', 'svg_curve')}`
- `ratio_hint` 直接写：`{section_plan.get('visual_ratio') or 'landscape_4_3'}`
- `render_goal` 需要用一句话明确说明“这张图帮助理解什么关系或什么变化”
"""
        else:
            stage_note = """
当前只生成“可渲染图示”层，不要重复生成通俗主正文，也不要生成严谨推导补充。
- 只在本节确实需要图示时输出内容；如果图示并不能显著降低理解成本，可返回空的 `blocks`
- 只输出 renderable_visual，并确保 Mermaid 可直接渲染
- 图示应服务于理解关系、曲线变化、机制流程或结构框架，不要为了凑形式硬画图
- 图示默认面向 Obsidian 阅读：优先保证版面紧凑、比例稳定、不要生成过宽的大横图
- 机制流程、因果链条、分层结构优先使用 `graph TD` / `flowchart TD`，只有横向对比非常明确且节点很少时才使用 `LR`
- 单张图尽量控制在 5 到 8 个核心节点内；如果关系过多，请拆成多张 `renderable_visual`，不要把所有内容塞进一张图
- 每个节点文字尽量短，优先控制在一行内；如必须换行，请使用 `<br/>` 主动断行，不要让长句撑宽整张图
- 避免多层 `subgraph` 嵌套、超长箭头链和过多交叉连线，避免在 Obsidian 中出现横向过宽或纵向失衡
- 不要输出 Markdown 代码围栏，只在 `payload.mermaid_code` 中给出 Mermaid 正文；正文首行应直接是 Mermaid 指令
- `payload` 至少补齐：`title`、`render_goal`、`render_format`、`visual_kind`、`mermaid_code`
- `render_format` 固定写 `mermaid`
- `ratio_hint` 建议写：`landscape_4_3`
- `render_goal` 需要用一句话明确说明“这张图帮助理解什么关系或什么变化”
"""
    else:
        raise ValueError(f"Unsupported stage: {stage}")

    return (
        f"{head}\n"
        f"当前生成阶段：{stage}\n"
        f"{stage_note}\n"
        f"{repair_note}\n"
        + _stage_schema_text(section_name, allowed_block_types)
    )


def build_stage_prompts(
    chapter_name: str,
    section_name: str,
    *,
    notebook_title: str | None = None,
    repair_messages: list[str] | None = None,
    section_plan_override: dict | None = None,
) -> list[dict]:
    section_plan = infer_section_plan(
        notebook_title,
        chapter_name,
        section_name,
        plan_override=section_plan_override,
    )
    stages = [
        {
            "stage": "guide",
            "required": True,
            "prompt": get_stage_prompt(
                "guide",
                chapter_name,
                section_name,
                notebook_title=notebook_title,
                repair_messages=repair_messages,
                section_plan_override=section_plan_override,
            ),
        }
    ]
    if section_plan["derivation_needed"]:
        stages.append(
            {
                "stage": "derivation",
                "required": False,
                "prompt": get_stage_prompt(
                    "derivation",
                    chapter_name,
                    section_name,
                    notebook_title=notebook_title,
                    repair_messages=repair_messages,
                    section_plan_override=section_plan_override,
                ),
            }
        )
    if section_plan["visual_needed"]:
        stages.append(
            {
                "stage": "visual",
                "required": False,
                "prompt": get_stage_prompt(
                    "visual",
                    chapter_name,
                    section_name,
                    notebook_title=notebook_title,
                    repair_messages=repair_messages,
                    section_plan_override=section_plan_override,
                ),
            }
        )
    return stages


def _extract_json_text(raw_response: str) -> str:
    text = (raw_response or "").strip()
    if not text:
        return ""

    fence_match = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", text, re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1].strip()
    return text


def parse_structured_response(raw_response: str, section_name: str) -> dict:
    """解析模型返回的结构化 JSON，失败时回退为 legacy_markdown。"""
    cleaned = _extract_json_text(raw_response)
    if not cleaned:
        raise ValueError("模型返回为空，无法解析结构化内容。")

    response_obj = json.loads(cleaned)
    if not isinstance(response_obj, dict):
        raise ValueError("结构化响应不是 JSON 对象。")

    blocks = response_obj.get("blocks")
    if not isinstance(blocks, list):
        raise ValueError("结构化响应缺少有效 blocks 数组。")

    normalized_blocks = []
    for idx, block in enumerate(blocks, start=1):
        if not isinstance(block, dict):
            continue

        block_type = str(block.get("block_type", "")).strip()
        block_title = str(block.get("block_title") or BLOCK_TYPE_TITLES.get(block_type, "")).strip()
        content = _repair_latex_escapes(str(block.get("content", "")).strip())
        block_payload = _normalize_payload(block_type, block.get("payload"), content)
        block_payload = _enrich_payload_from_content(block_type, block_payload, content, block_title)
        if block_type == "renderable_visual" and block_payload:
            content = _content_from_payload(block_type, block_payload)
        elif not content:
            content = _content_from_payload(block_type, block_payload)
        if not block_type or not content:
            continue
        if block_type not in BLOCK_TYPE_TITLES:
            continue

        block_title = block_title or BLOCK_TYPE_TITLES[block_type]
        normalized_blocks.append(
            {
                "block_type": block_type,
                "block_order": idx,
                "block_title": block_title,
                "content": content,
                "payload": block_payload,
            }
        )

    section_title = str(response_obj.get("section_title") or section_name).strip() or section_name
    rendered_markdown = render_markdown_from_blocks(section_title, normalized_blocks)

    return {
        "section_title": section_title,
        "blocks": normalized_blocks,
        "rendered_markdown": rendered_markdown,
    }


def merge_stage_blocks(section_name: str, stage_blocks: list[list[dict]]) -> dict:
    merged_blocks = []
    for blocks in stage_blocks:
        merged_blocks.extend(blocks or [])

    for idx, block in enumerate(merged_blocks, start=1):
        block["block_order"] = idx

    merged_blocks.sort(
        key=lambda item: (
            BLOCK_TYPE_ORDER.index(item["block_type"]) if item["block_type"] in BLOCK_TYPE_ORDER else len(BLOCK_TYPE_ORDER),
            item["block_order"],
        )
    )

    return {
        "section_title": section_name,
        "blocks": merged_blocks,
        "rendered_markdown": render_markdown_from_blocks(section_name, merged_blocks),
    }


def render_markdown_from_blocks(section_name: str, blocks: list[dict]) -> str:
    """将结构化内容块重新渲染成兼容现有导出链路的 Markdown。"""
    lines = [f"## {section_name}", ""]

    for block in blocks:
        block_title = (block.get("block_title") or BLOCK_TYPE_TITLES.get(block.get("block_type"), "未命名内容")).strip()
        content = _repair_latex_escapes(str(block.get("content", "")).strip())
        payload = block.get("payload")
        if block.get("block_type") == "renderable_visual" and payload:
            content = _content_from_payload(block.get("block_type"), payload)
        elif not content:
            content = _content_from_payload(block.get("block_type"), payload)
        if not content:
            continue
        lines.append(f"### {block_title}")
        lines.append(content)
        lines.append("")

    return "\n".join(lines).strip()
