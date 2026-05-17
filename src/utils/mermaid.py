import re


MERMAID_OBSIDIAN_INIT = (
    '%%{init: {"flowchart": {"useMaxWidth": false, "htmlLabels": true, '
    '"nodeSpacing": 28, "rankSpacing": 36}, "themeVariables": {"fontSize": "16px"}}}%%'
)
MERMAID_START_RE = re.compile(
    r"^(?:graph|flowchart|sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|erDiagram|journey|gantt|pie|mindmap|timeline|gitGraph|quadrantChart|xychart-beta|requirementDiagram|C4Context|C4Container|C4Component|C4Dynamic|C4Deployment)\b",
    re.IGNORECASE,
)
MERMAID_INIT_RE = re.compile(r"^%%\{init:.*\}%%$", re.IGNORECASE)


def _strip_mermaid_list_prefix(line: str) -> str:
    return re.sub(r"^(\s*)(?:>\s*)?(?:[-*+]\s+)?(?:\(?\d+[.)、:：]\)?\s+)+", r"\1", line)


def _normalize_mermaid_style_line(line: str) -> str:
    def _dasharray_repl(match: re.Match[str]) -> str:
        values = [item.strip() for item in match.group(2).split() if item.strip()]
        return f"{match.group(1)}{', '.join(values)}"

    return re.sub(
        r"(stroke-dasharray\s*:\s*)([0-9.]+(?:\s+[0-9.]+)+)",
        _dasharray_repl,
        line,
    )


def _compress_mermaid_label_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    replacements = [
        ("当前价格 P 与均衡价格 Pe 的关系?", "P 与 Pe?"),
        ("是否存在独立的信用中介?", "是否有信用中介?"),
        ("市场价格偏离均衡", "价格偏离均衡"),
        ("初始市场均衡", "初始均衡"),
        ("恢复市场均衡", "恢复均衡"),
        ("市场出现供过于求", "供过于求"),
        ("市场出现供不应求", "供不应求"),
        ("市场供大于求", "供大于求"),
        ("市场供不应求", "供不应求"),
        ("供给者之间发生竞争", "卖方竞争"),
        ("消费者之间发生竞争", "买方竞争"),
        ("降价以清理存货", "降价清库存"),
        ("抬高价格以获得商品", "抬价购买"),
        ("外部因素变化", "外因变化"),
        ("导致需求变动", "需求变动"),
        ("导致供给变动", "供给变动"),
        ("供给保持不变", "供给不变"),
        ("需求保持不变", "需求不变"),
        ("需求曲线向右移动", "需求右移"),
        ("需求曲线向左移动", "需求左移"),
        ("供给曲线向右移动", "供给右移"),
        ("供给曲线向左移动", "供给左移"),
        ("呈现同向变动", "同向"),
        ("呈现反向变动", "反向"),
        ("变动不确定", "方向待定"),
        ("单因素冲击分析", "单因素冲击"),
        ("供求曲线同时变动", "供求同时变动"),
        ("同向移动组合", "同向组合"),
        ("反向移动组合", "反向组合"),
        ("趋向均衡状态", "回归均衡"),
        ("需求增加", "需求增"),
        ("需求减少", "需求减"),
        ("供给增加", "供给增"),
        ("供给减少", "供给减"),
        ("均衡价格", "Pe"),
        ("均衡数量", "Qe"),
        ("供给量 = 需求量", "Qd = Qs"),
        ("资金盈余方", "资金盈余方"),
        ("资金短缺方", "资金短缺方"),
        ("投资者之间相互买卖", "投资者相互买卖"),
        ("投资者直接承担风险", "投资者承担风险"),
        ("中介承担并转换风险", "中介转换风险"),
        ("筹资者首次出售证券", "首次发行证券"),
        ("实现资金筹集", "完成筹资"),
        ("实现证券变现", "证券变现"),
        ("银行吸收存款发放贷款", "吸收存贷"),
        ("金融商品交易程序", "金融交易程序"),
        ("流通中现金发行", "现金发行"),
        ("各项存款", "各项存款"),
        ("准备金与政府存款", "准备金/政府存款"),
        ("垄断全国货币发行权", "垄断发行权"),
        ("创造基础货币", "创造基础货币"),
        ("集中保管存款准备金", "集中保管准备金"),
        ("充当最终贷款人", "最终贷款人"),
        ("代理国库各项收支业务", "代理国库收支"),
        ("制定与执行货币政策", "执行货币政策"),
        ("市场准入与退出监管", "准入与退出监管"),
        ("日常行为与资产负债", "日常行为与资负"),
        ("资质审批/破产清算", "审批/清算"),
        ("防范劣质机构入场", "防劣质入场"),
        ("内控合规要求", "内控合规"),
        ("资金运用比例限制", "资金比例限制"),
        ("资本充足率下限", "资本下限"),
        ("风险预警与压力测试", "预警/压力测试"),
        ("国际收支平衡表", "国际收支表"),
        ("资本与金融账户", "资本金融账户"),
        ("错误与遗漏账户", "误差遗漏账户"),
        ("经常转移", "经常转移"),
        ("单方面支付", "单方支付"),
        ("资本转移/无形资产收买", "资本转移/无形资产"),
        ("直接/证券/其他投资", "直接/证券/其他投资"),
        ("国际收支赤字", "收支赤字"),
        ("央行抛售外汇", "央行售汇"),
        ("国内货币供应下降", "货币供给下降"),
        ("外资流入增加", "外资流入增"),
        ("资本账户改善", "资本账户改善"),
        ("进口需求减", "进口需求减"),
        ("经常账户改善", "经常账户改善"),
        ("出口增加进口减少", "出口增/进口减"),
        ("国际收支调节政策", "收支调节政策"),
        ("外汇缓冲政策", "外汇缓冲"),
        ("动用储备或外部借款", "动储备/外借"),
        ("增减支出/改变税率", "调支出/税率"),
        ("调节贴现率/准备金率", "调贴现率/准备金率"),
        ("货币法定升贬值", "法定升贬值"),
        ("外汇与贸易管制", "外汇/贸易管制"),
        ("汇率决定理论", "汇率理论"),
        ("购买力平价说", "购买力平价"),
        ("取决于相对物价", "看相对物价"),
        ("利率平价说", "利率平价"),
        ("取决于两国利差", "看两国利差"),
        ("国际收支说", "国际收支说"),
        ("取决于外汇供求流量", "看外汇供求"),
        ("资产市场说", "资产市场说"),
        ("取决于资产市场存量均衡", "看资产存量均衡"),
        ("资产组合平衡论", "资产组合论"),
        ("本外币资产不完全替代", "本外币不完全替代"),
        ("弹性价格模型", "弹性价格"),
        ("商品价格随货币供求迅速调整", "价格随货币迅调"),
        ("粘性价格/超调模型", "粘价/超调模型"),
        ("短期价格粘性导致汇率超调", "短期粘价致超调"),
        ("提出要约 / 支付保费", "要约/付保费"),
        ("承担赔偿 / 给付责任", "赔偿/给付责任"),
        ("给付死亡保险金", "给付死亡金"),
        ("必须具有", "必须有"),
        ("指定 / 变更", "指定/变更"),
        ("同意或指定", "同意/指定"),
        ("投保人: 提出要约", "投保人提出要约"),
        ("保险人: 承诺承保", "保险人承保"),
        ("是否附条件/期限?", "附条件/期限?"),
        ("合同成立即生效", "成立即生效"),
        ("条件满足/期限届至生效", "条件满足后生效"),
        ("合同存续及履行期", "存续与履行期"),
        ("期限届满: 自然终止", "届满: 自然终止"),
        ("赔付或给付: 履行完毕", "赔付/给付: 履行完毕"),
        ("保费断交等: 违约失效", "保费断交: 失效"),
        ("法定/约定/任意: 合同解除", "法定/约定/任意解除"),
        ("产生条款争议", "条款争议"),
        ("字面文意是否单一明确?", "文意是否明确?"),
        ("适用: 文义解释原则", "文义解释"),
        ("可否通过逻辑推断真实意图?", "能否推断真实意图?"),
        ("适用: 意图解释原则", "意图解释"),
        ("适用: 有利于被保险人/受益人解释", "有利于被保人解释"),
        ("冲突时优先适用", "冲突时优先"),
        ("批注优于正文", "批注优先"),
        ("手写优于打印", "手写优先"),
    ]
    for source, target in replacements:
        cleaned = cleaned.replace(source, target)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _shorten_mermaid_labels(line: str) -> str:
    def _replace_label(match: re.Match[str]) -> str:
        token = match.group(0)
        if len(token) < 3:
            return token
        opener, inner, closer = token[0], token[1:-1], token[-1]
        segments = re.split(r"(<br\s*/?>)", inner, flags=re.IGNORECASE)
        normalized_segments = []
        for segment in segments:
            if re.fullmatch(r"<br\s*/?>", segment or "", flags=re.IGNORECASE):
                normalized_segments.append("<br/>")
            else:
                normalized_segments.append(_compress_mermaid_label_text(segment))
        return f"{opener}{''.join(normalized_segments)}{closer}"

    return re.sub(r"\[[^\]]+\]|\([^\)]+\)|\{[^}]+\}", _replace_label, line)


def sanitize_mermaid_code(raw_code: str) -> str:
    text = (raw_code or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""

    fence_match = re.search(r"```mermaid\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()

    prepared_lines = []
    for raw_line in text.split("\n"):
        line = raw_line.expandtabs(4).rstrip()
        if line.strip().startswith("```"):
            continue
        line = _strip_mermaid_list_prefix(line)
        line = _normalize_mermaid_style_line(line)
        line = _shorten_mermaid_labels(line)
        prepared_lines.append(line)

    start_index = next(
        (idx for idx, line in enumerate(prepared_lines) if MERMAID_START_RE.match(line.strip())),
        None,
    )
    if start_index is not None:
        init_lines = [
            line
            for line in prepared_lines[:start_index]
            if MERMAID_INIT_RE.match(line.strip())
        ]
        prepared_lines = init_lines + prepared_lines[start_index:]

    return "\n".join(prepared_lines).strip()


def format_obsidian_mermaid_code(raw_code: str) -> str:
    sanitized = sanitize_mermaid_code(raw_code)
    if not sanitized:
        return ""
    if sanitized.lstrip().startswith("%%{init:"):
        return sanitized
    return f"{MERMAID_OBSIDIAN_INIT}\n{sanitized}"


def inspect_mermaid_code(raw_code: str) -> dict:
    raw_text = (raw_code or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    sanitized = sanitize_mermaid_code(raw_code)

    issues: list[dict] = []
    auto_fixes: list[str] = []

    if not raw_text:
        return {
            "sanitized_code": "",
            "issues": issues,
            "auto_fixes": auto_fixes,
            "has_code": False,
        }

    if "```mermaid" in raw_text.lower():
        auto_fixes.append("已自动提取 Mermaid 代码块正文。")

    raw_lines = raw_text.split("\n")
    if any(re.match(r"^\s*(?:>\s*)?(?:[-*+]\s+)?(?:\(?\d+[.)、:：]\)?\s+)+", line) for line in raw_lines):
        auto_fixes.append("已自动移除 Mermaid 行首的列表序号或 Markdown 列表前缀。")

    if re.search(r"stroke-dasharray\s*:\s*[0-9.]+(?:\s+[0-9.]+)+", raw_text):
        auto_fixes.append("已自动修正 `stroke-dasharray` 为 Mermaid 兼容格式。")

    if sanitized and sanitized != raw_text:
        raw_start = next((idx for idx, line in enumerate(raw_lines) if MERMAID_START_RE.match(line.strip())), None)
        if raw_start not in (None, 0):
            auto_fixes.append("已自动截取 Mermaid 主体代码，忽略图前说明文字。")

    if not sanitized:
        issues.append({"level": "warning", "message": "可渲染图示块存在内容，但未能提取出有效 Mermaid 代码。"})
        return {
            "sanitized_code": "",
            "issues": issues,
            "auto_fixes": auto_fixes,
            "has_code": True,
        }

    sanitized_lines = [line for line in sanitized.split("\n") if line.strip()]
    chart_start_line = next(
        (
            line for line in sanitized_lines
            if not MERMAID_INIT_RE.match(line.strip())
        ),
        "",
    )
    if not sanitized_lines:
        issues.append({"level": "warning", "message": "Mermaid 代码清洗后为空，暂时无法渲染。"})
    elif not chart_start_line:
        issues.append({"level": "warning", "message": "Mermaid 代码缺少合法的图类型起始行，例如 `graph TD` 或 `sequenceDiagram`。"})
    elif not MERMAID_START_RE.match(chart_start_line.strip()):
        issues.append({"level": "warning", "message": "Mermaid 代码缺少合法的图类型起始行，例如 `graph TD` 或 `sequenceDiagram`。"})

    if any(re.match(r"^\s*\d+[.)、:：]\s+", line) for line in sanitized_lines):
        issues.append({"level": "warning", "message": "Mermaid 代码中仍残留行首序号，可能继续影响渲染。"})

    return {
        "sanitized_code": sanitized,
        "issues": issues,
        "auto_fixes": auto_fixes,
        "has_code": True,
    }
