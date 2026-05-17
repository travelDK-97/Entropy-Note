from __future__ import annotations


FORMULA_KEYWORDS = {
    "统计": 3,
    "卫生统计": 4,
    "流行病学": 4,
    "计量": 4,
    "概率": 3,
    "分布": 3,
    "抽样": 3,
    "回归": 4,
    "方差": 3,
    "协方差": 3,
    "假设检验": 4,
    "模型": 3,
    "均衡": 3,
    "效用": 3,
    "成本": 2,
    "收益": 2,
    "利率": 2,
    "弹性": 3,
    "乘数": 3,
    "is-lm": 4,
    "as-ad": 4,
    "财务报表": 2,
    "会计": 2,
    "金融": 2,
    "保险精算": 4,
    "方程": 3,
    "公式": 4,
    "定理": 4,
    "推导": 4,
}

TEXT_KEYWORDS = {
    "政策": 4,
    "法规": 4,
    "制度": 4,
    "管理": 3,
    "社会医学": 5,
    "卫生政策": 5,
    "卫生服务": 4,
    "公共卫生": 2,
    "伦理": 4,
    "法学": 4,
    "组织": 3,
    "历史": 2,
    "改革": 3,
    "治理": 4,
    "项目": 2,
    "监管": 3,
    "评价": 3,
    "概论": 2,
    "理论基础": 2,
    "体制": 3,
}

MIXED_KEYWORDS = {
    "微观经济学": 3,
    "宏观经济学": 3,
    "金融学": 3,
    "保险学": 3,
    "会计与财务": 3,
    "公共卫生": 3,
}

VISUAL_YES_KEYWORDS = {
    "模型": 4,
    "均衡": 4,
    "曲线": 5,
    "供给": 4,
    "需求": 4,
    "is-lm": 5,
    "as-ad": 5,
    "流程": 4,
    "机制": 3,
    "传导": 4,
    "路径": 3,
    "框架": 3,
    "结构": 3,
    "分类": 3,
    "关系": 3,
    "研究设计": 5,
    "队列": 5,
    "病例对照": 5,
    "责任": 3,
    "监管": 3,
    "调节": 4,
}

VISUAL_NO_KEYWORDS = {
    "证明": 4,
    "纯证明": 5,
    "代数": 4,
    "极限": 4,
    "微分": 4,
    "积分": 4,
    "级数": 4,
    "矩阵": 3,
    "变换": 3,
    "推导": 2,
    "计算": 2,
}


def _score_keywords(text: str, keyword_weights: dict[str, int]) -> int:
    score = 0
    for keyword, weight in keyword_weights.items():
        if keyword in text:
            score += weight
    return score


def _matched_keywords(text: str, keyword_weights: dict[str, int]) -> list[str]:
    matches = [
        (keyword, weight)
        for keyword, weight in keyword_weights.items()
        if keyword in text
    ]
    matches.sort(key=lambda item: (-item[1], item[0]))
    return [keyword for keyword, _ in matches]


def _merge_reason_parts(*parts: str) -> str:
    return "；".join([part for part in parts if part])


def _copy_plan(plan: dict) -> dict:
    copied = {}
    for key, value in (plan or {}).items():
        copied[key] = list(value) if isinstance(value, list) else value
    return copied


STYLE_LABELS = {
    "formula_heavy": "公式推导型",
    "text_heavy": "文字推理型",
    "mixed": "混合型",
}

VISUAL_TYPE_LABELS = {
    "none": "不出图",
    "svg_curve": "SVG 坐标曲线图",
    "svg_effect_decomposition": "SVG 效应分解图",
    "mermaid_flowchart": "Mermaid 机制流程图",
    "mermaid_structure": "Mermaid 结构框图",
}

VISUAL_RATIO_LABELS = {
    "square": "1:1",
    "landscape_4_3": "4:3 横向",
    "landscape_16_9": "16:9 横向",
}


def _infer_visual_plan(chapter_name: str, section_name: str, combined: str, visual_needed: bool) -> dict:
    if not visual_needed:
        return {
            "visual_type": "none",
            "visual_ratio": "",
            "visual_type_label": VISUAL_TYPE_LABELS["none"],
        }

    effect_keywords = (
        "替代效应",
        "收入效应",
        "斯勒茨基",
        "希克斯",
        "补偿预算线",
        "价格消费曲线",
    )
    curve_keywords = (
        "需求",
        "供给",
        "均衡",
        "弹性",
        "预算线",
        "无差异曲线",
        "边际替代率",
        "生产函数",
        "成本曲线",
        "收益曲线",
        "is-lm",
        "as-ad",
        "菲利普斯",
        "总需求",
        "总供给",
        "宏观经济学",
        "微观经济学",
    )
    structure_keywords = ("结构", "框架", "分类", "关系", "体系")
    flow_keywords = ("机制", "流程", "传导", "路径", "调节", "监管", "责任")

    text = f"{chapter_name} {section_name} {combined}".lower()
    if any(keyword.lower() in text for keyword in effect_keywords):
        visual_type = "svg_effect_decomposition"
        visual_ratio = "landscape_16_9"
    elif any(keyword.lower() in text for keyword in curve_keywords):
        visual_type = "svg_curve"
        visual_ratio = "landscape_4_3"
    elif any(keyword.lower() in text for keyword in structure_keywords):
        visual_type = "mermaid_structure"
        visual_ratio = "landscape_4_3"
    elif any(keyword.lower() in text for keyword in flow_keywords):
        visual_type = "mermaid_flowchart"
        visual_ratio = "landscape_4_3"
    else:
        visual_type = "svg_curve"
        visual_ratio = "landscape_4_3"

    return {
        "visual_type": visual_type,
        "visual_ratio": visual_ratio,
        "visual_type_label": VISUAL_TYPE_LABELS.get(visual_type, visual_type),
    }


def _style_guidance(style: str) -> str:
    if style == "formula_heavy":
        return (
            "- 本节更偏公式推导型：优先完整输出 definition、formula，必要时补 theorem 或 proof_or_derivation。\n"
            "- 如果资料里有公式、模型、约束条件、变量释义、判断标准，不要只讲直觉，必须显式写出。\n"
            "- 大白话可以保留，但不能替代公式、定义和推导。"
        )
    if style == "text_heavy":
        return (
            "- 本节更偏文字推理型：优先讲清背景主线、制度逻辑、概念边界、机制链条、易错点。\n"
            "- 只有当资料里明确存在公式、比例、阈值、定量关系时，才补 formula；不要为凑结构强写空公式。\n"
            "- 重点把判断标准、适用场景、政策逻辑和常见误区梳理清楚。"
        )
    return (
        "- 本节属于混合型：既要讲清背景与机制，也要保留必要的公式、模型、变量和约束条件。\n"
        "- 如果资料里存在核心公式或模型，请务必显式整理；如果存在制度逻辑或文字规则，也不要压缩成只剩公式。"
    )


def _derivation_guidance(derivation_needed: bool) -> str:
    return (
        "需要提供独立的严谨推导补充，正文先保证通顺总结，推导、条件、变量、关键步骤放在补充层。"
        if derivation_needed
        else "不强制提供严谨推导补充，除非原资料本身明确包含关键公式、定理或严格证明。"
    )


def _visual_guidance(visual_needed: bool, visual_type: str = "none", visual_ratio: str = "") -> str:
    if not visual_needed:
        return "不需要强制输出可渲染图示；如果图示不能显著降低理解成本，就不要为了凑结构硬画图。"
    if visual_type == "svg_curve":
        return (
            "需要输出 SVG 坐标曲线图，优先用标准坐标轴、曲线/直线、均衡点与必要标注来降低理解成本。"
            + (f" 建议比例：{VISUAL_RATIO_LABELS.get(visual_ratio, visual_ratio)}。" if visual_ratio else "")
        )
    if visual_type == "svg_effect_decomposition":
        return (
            "需要输出 SVG 效应分解图，适合展示预算线、无差异曲线、初始点/补偿点/最终点，以及替代效应和收入效应。"
            + (f" 建议比例：{VISUAL_RATIO_LABELS.get(visual_ratio, visual_ratio)}。" if visual_ratio else "")
        )
    if visual_type == "mermaid_structure":
        return (
            "需要输出 Mermaid 结构框图，因为本节更适合展示分类、框架和静态关系。"
            + (f" 建议比例：{VISUAL_RATIO_LABELS.get(visual_ratio, visual_ratio)}。" if visual_ratio else "")
        )
    return (
        "需要输出 Mermaid 机制流程图，因为本节存在流程链条、因果传导或动态调节结构。"
        + (f" 建议比例：{VISUAL_RATIO_LABELS.get(visual_ratio, visual_ratio)}。" if visual_ratio else "")
    )


def _fallback_section_plan(notebook_title: str | None, chapter_name: str, section_name: str) -> dict:
    style_info = infer_section_style(notebook_title, chapter_name, section_name)
    combined = " ".join(part for part in [notebook_title or "", chapter_name or "", section_name or ""] if part).lower()
    visual_yes_hits = _matched_keywords(combined, {k.lower(): v for k, v in VISUAL_YES_KEYWORDS.items()})
    visual_no_hits = _matched_keywords(combined, {k.lower(): v for k, v in VISUAL_NO_KEYWORDS.items()})
    visual_yes_score = _score_keywords(combined, {k.lower(): v for k, v in VISUAL_YES_KEYWORDS.items()})
    visual_no_score = _score_keywords(combined, {k.lower(): v for k, v in VISUAL_NO_KEYWORDS.items()})

    derivation_needed = style_info["style"] in {"formula_heavy", "mixed"}
    visual_needed = visual_yes_score >= max(4, visual_no_score + 2)
    visual_plan = _infer_visual_plan(chapter_name, section_name, combined, visual_needed)
    visual_reason_parts = []
    if visual_yes_hits[:3]:
        visual_reason_parts.append("支持出图: " + "、".join(visual_yes_hits[:3]))
    if visual_no_hits[:3]:
        visual_reason_parts.append("抑制出图: " + "、".join(visual_no_hits[:3]))
    if visual_needed:
        visual_reason_parts.append(
            f"建议图示类型: {visual_plan['visual_type_label']}"
            + (f"；建议比例: {VISUAL_RATIO_LABELS.get(visual_plan['visual_ratio'], visual_plan['visual_ratio'])}" if visual_plan["visual_ratio"] else "")
        )
    visual_reason = "；".join(visual_reason_parts) if visual_reason_parts else "当前主要按章节标题与小节标题关键词判定图示需求。"

    return {
        **style_info,
        "derivation_needed": derivation_needed,
        "visual_needed": visual_needed,
        "visual_type": visual_plan["visual_type"],
        "visual_ratio": visual_plan["visual_ratio"],
        "visual_yes_score": visual_yes_score,
        "visual_no_score": visual_no_score,
        "derivation_guidance": _derivation_guidance(derivation_needed),
        "visual_guidance": _visual_guidance(visual_needed, visual_plan["visual_type"], visual_plan["visual_ratio"]),
        "visual_reason": visual_reason,
    }


def normalize_section_plan_override(
    raw_plan: dict | None,
    notebook_title: str | None,
    chapter_name: str,
    section_name: str,
) -> dict:
    base = _fallback_section_plan(notebook_title, chapter_name, section_name)
    if not isinstance(raw_plan, dict):
        return base

    style = str(raw_plan.get("style", "")).strip().lower()
    if style in {"公式推导型", "公式型"}:
        style = "formula_heavy"
    elif style in {"文字推理型", "文字型"}:
        style = "text_heavy"
    elif style in {"混合型"}:
        style = "mixed"
    if style not in STYLE_LABELS:
        style = base["style"]

    derivation_raw = raw_plan.get("derivation_needed")
    visual_raw = raw_plan.get("visual_needed")
    derivation_needed = derivation_raw if isinstance(derivation_raw, bool) else base["derivation_needed"]
    visual_needed = visual_raw if isinstance(visual_raw, bool) else base["visual_needed"]
    visual_type = str(raw_plan.get("visual_type", "")).strip() or base.get("visual_type", "none")
    visual_ratio = str(raw_plan.get("visual_ratio", "")).strip() or base.get("visual_ratio", "")
    if visual_type not in VISUAL_TYPE_LABELS:
        visual_type = base.get("visual_type", "none")
    if visual_ratio and visual_ratio not in VISUAL_RATIO_LABELS:
        visual_ratio = base.get("visual_ratio", "")
    if not visual_needed:
        visual_type = "none"
        visual_ratio = ""

    normalized = {
        **base,
        "style": style,
        "label": STYLE_LABELS[style],
        "guidance": _style_guidance(style),
        "derivation_needed": derivation_needed,
        "visual_needed": visual_needed,
        "visual_type": visual_type,
        "visual_ratio": visual_ratio,
        "derivation_guidance": _derivation_guidance(derivation_needed),
        "visual_guidance": _visual_guidance(visual_needed, visual_type, visual_ratio),
    }
    style_reason = str(raw_plan.get("style_reason", "")).strip()
    visual_reason = str(raw_plan.get("visual_reason", "")).strip()
    if style_reason:
        normalized["style_reason"] = style_reason
    if visual_reason:
        normalized["visual_reason"] = visual_reason
    return normalized


def infer_section_style(notebook_title: str | None, chapter_name: str, section_name: str) -> dict:
    combined = " ".join(part for part in [notebook_title or "", chapter_name or "", section_name or ""] if part).lower()
    formula_hits = _matched_keywords(combined, {k.lower(): v for k, v in FORMULA_KEYWORDS.items()})
    text_hits = _matched_keywords(combined, {k.lower(): v for k, v in TEXT_KEYWORDS.items()})
    mixed_hits = _matched_keywords(combined, {k.lower(): v for k, v in MIXED_KEYWORDS.items()})

    formula_score = _score_keywords(combined, {k.lower(): v for k, v in FORMULA_KEYWORDS.items()})
    text_score = _score_keywords(combined, {k.lower(): v for k, v in TEXT_KEYWORDS.items()})
    mixed_score = _score_keywords(combined, {k.lower(): v for k, v in MIXED_KEYWORDS.items()})

    if formula_score >= text_score + 2 and formula_score >= mixed_score:
        style = "formula_heavy"
        label = STYLE_LABELS[style]
    elif text_score >= formula_score + 2 and text_score >= mixed_score:
        style = "text_heavy"
        label = STYLE_LABELS[style]
    else:
        style = "mixed"
        label = STYLE_LABELS[style]

    reason_parts = []
    if formula_hits[:3]:
        reason_parts.append("公式信号: " + "、".join(formula_hits[:3]))
    if text_hits[:3]:
        reason_parts.append("文字信号: " + "、".join(text_hits[:3]))
    if mixed_hits[:3]:
        reason_parts.append("混合信号: " + "、".join(mixed_hits[:3]))
    style_reason = "；".join(reason_parts) if reason_parts else "当前主要按章节标题与小节标题关键词判定。"

    return {
        "style": style,
        "label": label,
        "formula_score": formula_score,
        "text_score": text_score,
        "mixed_score": mixed_score,
        "guidance": _style_guidance(style),
        "style_reason": style_reason,
    }


def infer_section_plan(
    notebook_title: str | None,
    chapter_name: str,
    section_name: str,
    *,
    plan_override: dict | None = None,
) -> dict:
    if plan_override:
        return normalize_section_plan_override(plan_override, notebook_title, chapter_name, section_name)
    return _fallback_section_plan(notebook_title, chapter_name, section_name)


def enrich_outline_with_section_plans(outline: list, notebook_title: str | None = None) -> list:
    enriched = []
    for part in outline or []:
        chapter_name = part.get("chapter", "")
        sections = []
        section_plans = {}
        raw_section_plans = part.get("section_plans") if isinstance(part.get("section_plans"), dict) else {}
        for item in (part.get("sections", []) or []):
            section_name = str(item.get("title") if isinstance(item, dict) else item).strip()
            if not section_name:
                continue
            raw_plan = raw_section_plans.get(section_name)
            if isinstance(item, dict) and isinstance(item.get("section_plan"), dict):
                raw_plan = item.get("section_plan")
            plan = normalize_section_plan_override(raw_plan, notebook_title, chapter_name, section_name)
            sections.append(section_name)
            section_plans[section_name] = plan
        enriched.append(
            {
                **part,
                "chapter": chapter_name,
                "sections": sections,
                "section_plans": section_plans,
            }
        )
    return enriched


def get_outline_section_plan(outline: list, chapter_name: str, section_name: str) -> dict | None:
    for part in outline or []:
        if part.get("chapter") != chapter_name:
            continue
        plan = (part.get("section_plans") or {}).get(section_name)
        if plan:
            return _copy_plan(plan)
    return None
