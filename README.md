# Entropy Note

一个构建在 [Google NotebookLM](https://notebooklm.google.com/) 与 `notebooklm-py` 之上的学习资料自动化流水线，支持分阶段生成、SQLite 断点续传、SVG/Mermaid 图示、质量报告，以及面向 Obsidian 的导出体验。

本项目面向“依赖直觉、机制推演和结构化主线学习”的使用场景，目标是把零散的“与大模型对话”过程收敛为**模块化、可恢复、可扩展的学习工程**。

> TL;DR: `entropy-note` 是本仓库自己的学习资料流水线入口，不是对上游 `notebooklm` / `notebooklm-py` 命令的重复包装。

如果你是后续继续接手此仓库的 agent 或自动化协作者，建议优先阅读 [AGENTS.md](AGENTS.md)。

## 🌟 核心特性

- **一键全自动**：自动读取 NotebookLM 中的资料，提取章节大纲，按章逐节生成学习资料。
- **认证恢复与失败诊断**：支持登录预检、自动拉起登录、失败原因分类与认证恢复，减少中途掉线后整批中断。
- **安全延时与重试**：内置安全等待、指数退避与质量重生成机制，优先保证稳定可跑。
- **断点续传**：所有 Prompt、结构化响应和渲染结果都会实时写入 SQLite 数据库 (`study_guide.db`)。
- **结构化知识资产**：除主文档外，还会保存结构化 block、质量报告、章节速查表与可渲染图示。
- **学习优先模式**：默认优先导出快速学习指南、章节速查表、结构化资料、质量报告与可渲染图示；漫画、图像任务和发布功能默认保留但不启用。

## 🔗 与 `notebooklm-py` 的关系

- 本项目**依赖** [`notebooklm-py`](https://pypi.org/project/notebooklm-py/)，并复用其登录、会话与 Notebook 访问能力。
- 本项目**不是** `notebooklm-py` 的 fork，也不是对其 API 的一层轻量包装。
- 本项目更接近一个上层应用：在 `notebooklm-py` 之上补了提示词分阶段生成、SQLite 落库、断点续传、SVG/Mermaid 图示、质量报告、Obsidian 友好导出与 CLI/CI。
- 如果未来确实需要长期维护 `notebooklm-py` 的源码级改动，建议再单独 fork 上游；在当前阶段，保持“独立应用仓库 + 上游依赖”的结构更清晰。

## 🧰 本项目命令和上游命令的区别

如果你第一次看到 `entropy-note`，很容易误以为它只是重复调用了上游已有命令。实际上不是。

- `notebooklm` / `notebooklm-py` 更偏向底层访问能力：登录、会话、列出笔记本、发送请求等
- `python main.py` 是本仓库的主流程脚本入口
- `entropy-note` 是把 `python main.py` 封装成一个可安装、可分发、可在 CI 或其他机器上直接调用的命令行入口

可以把它们理解为两个层级：

- 上游命令负责“连接和访问 NotebookLM”
- 本项目命令负责“把访问能力组织成完整的学习资料流水线”

`entropy-note` 对应的不是一个单独的 API 调用，而是整套流程，包括：

- 选择笔记本
- 提取或读取大纲
- 节级首判与 `section_plan`
- 按整本 / 单章 / 单节运行
- 分阶段生成 `guide` / `derivation` / `visual`
- SQLite 落库、断点续传与重跑
- 导出快速学习指南、章节速查表、结构化资料、可渲染图示和质量报告

因此，`entropy-note` 的价值不在于“代替上游命令”，而在于把上游能力包装成一个可直接使用的上层产品入口。

## 🧭 当前设计决策

这是当前项目的主链路与近期讨论后确定的设计取舍，后续继续迭代时请优先遵守这些原则。

### 1. 学习主链路优先

- 主目标是“学习资料主链路随时可跑通”，而不是优先做发布型花活。
- 输出形态以 Markdown 为主，优先兼容 Obsidian 阅读。
- 学习资料命名统一使用“快速学习指南”，不再使用“期末复习”类表述。

### 2. 资料分层，而不是一份文档包打天下

当前导出已经分为多层：

- `快速学习指南`：通顺、可一目十行，优先帮助建立主线和大意。
- `章节速查表`：按章汇总定义、定理、公式、推导和易错点，方便检索。
- `结构化资料`：保留结构化 block，适合后续加工。
- `可渲染图示`：集中输出 Mermaid 或 SVG 图示。
- `质量报告`：汇总错误、警告、自动修复与图示人工检查项。

### 3. 分阶段提示词链路

为降低单次提示词复杂度，当前生成逻辑已拆为三段：

- `guide`：只生成通俗主正文。
- `derivation`：只生成严谨推导补充。
- `visual`：只生成可渲染图示。

三段结果会在落库前合并回同一小节。这样做的目的是：

- 保证主正文更通顺。
- 严谨推导不挤占正文篇幅。
- 图示只在确实需要时单独生成。

### 4. 二值判定，而不是中间态堆 warning

当前章节判定只保留两个独立的“是/否”决策：

- 是否需要严谨推导补充
- 是否需要可渲染图示

不再使用“可选出图”这类中间态，以减少含糊规则和无效 warning。

### 5. 图示判断看认知结构，不看学科标签

图示是否需要，不按“经济学/数学/政策”粗暴划分，而看这一节是否存在：

- 曲线关系
- 变量联动
- 机制流程
- 分类框架
- 结构路径

例如：

- 某些经济学模型和公式推导非常需要图示。
- 某些抽象数学推导则更适合文字推导补充，不一定需要图示。

### 6. 单章测试优先

为了避免整本重跑过慢，`main.py` 已支持单章模式：

```bash
python main.py --notebook-title "<你的笔记本标题>" --chapter-title "<章节标题>" --force-regenerate
```

也可按序号选择章节：

```bash
python main.py --notebook-title "<你的笔记本标题>" --chapter-index 3 --force-regenerate
```

单章测试模式只处理目标章节，并跳过整本级自动补救，适合快速迭代提示词和导出链路。

## 📁 项目结构

```text
entropy-note/
├── main.py                     # [入口] 流程控制中心，支持整本/单章/强制重生成
├── run_image_tasks.py          # [工具] 读取图像任务 JSONL，生成可批量执行的提示词包
├── requirements.txt            # [依赖] 项目依赖清单
├── study_guide.db              # [数据] SQLite 数据库 (运行后自动生成)
├── outputs/                    # [产物] 生成的 Markdown 文件存放处 (运行后自动生成)
├── EXAM_PROMPTS_GUIDE.md       # [文档] 可选的手动提示词参考，不是主流程必需文件
└── src/
    ├── config.py               # [配置] 全局参数 (延时时间/重试次数等)
    ├── core/
│   └── client.py           # [核心] NotebookLM 客户端，含认证恢复、重试与失败诊断
    ├── db/
    │   └── manager.py          # [数据] 专门负责读写 SQLite 数据库，实现断点续传
    ├── prompts/
│   ├── markdown_prompts.py # [提示词] 分阶段提示词、结构化解析与 block 合并
│   └── section_style.py    # [判定] 判断小节偏文字/推导，以及是否需要图示
    └── utils/
│   └── exporter.py         # [导出] 负责导出快速学习指南、速查表、结构化资料与图示
```

## 🚀 快速开始

### 1. 环境准备

确保你已经安装了 Python 3.10+，并创建了虚拟环境。

```bash
# 激活虚拟环境 (Windows)
.\.venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 首次使用时安装 Playwright 浏览器
python -m playwright install

# 可选：以可编辑模式安装本项目，启用命令行入口
pip install -e .
```

如需自定义 NotebookLM 的本地缓存目录，可在运行前设置环境变量：

```bash
# Windows PowerShell
$env:NOTEBOOKLM_HOME = ".notebooklm"
```

如果不设置，项目默认会使用仓库根目录下的 `.notebooklm/`。

完成 `pip install -e .` 后，也可以直接使用这些命令：

```bash
entropy-note-login
entropy-note --notebook-title "<你的笔记本标题>"
entropy-note-image-tasks --dry-run
```

### 2. 授权登录 Google 账号

在首次运行前，你需要通过浏览器授权登录 Google 账号（只需操作一次）：

```bash
notebooklm login
# 或
python login.py
# 或（已通过 pip install -e . 安装时）
entropy-note-login
```

*(在弹出的浏览器中登录 Google 账号，直到进入 NotebookLM 首页后关闭或返回终端)*

### 3. 开始自动生成

确保你在 NotebookLM 网页端已经创建了一个包含你教材/习题的笔记本。然后运行：

```bash
python main.py
# 或（已通过 pip install -e . 安装时）
entropy-note
```

- 脚本会列出你账号下的所有笔记本。
- 输入对应的序号。
- 去喝杯咖啡，等待流水线自动完成。
- 在 `outputs/<笔记本名>/` 文件夹中收取你的快速学习指南、章节速查表、结构化资料、质量报告与可渲染图示。

默认情况下，项目运行在“学习优先模式”，只生成最核心的学习文件，并保留可直接在 Obsidian 中阅读的 Mermaid / SVG 图示。
图示会嵌入 `快速学习指南.md` 和 `结构化资料.md` 中对应小节附近，同时也会单独导出为 `可渲染图示.md`。
此外，系统还会额外导出 `章节速查表.md`，方便按章快速检索定义、公式、定理和易错点。
如果你后续想重新开启漫画提示词、图像任务与发布闸门，请修改 `src/config.py`：

```python
LEARNING_FIRST_MODE = False
```

### 4. 批量准备图像任务

只有在你关闭学习优先模式、重新启用发布增强导出后，才会生成 `*_图像任务.jsonl`。
此时你可以继续运行：

```bash
python run_image_tasks.py --dry-run
# 或
entropy-note-image-tasks --dry-run
```

这会自动扫描 `outputs/` 下最新的 `*_图像任务.jsonl`，并打印各工具的任务数。

如果确认没问题，再生成真正的批处理提示词包：

```bash
python run_image_tasks.py
```

也可以按工具或章节过滤：

```bash
python run_image_tasks.py --tool lovart --chapter 极限
```

运行后会在 `outputs/<笔记本名>/图像执行任务/<时间戳>/` 下生成：

- `00_manifest.json`：本次批处理清单
- `<tool>/00_batch_prompts.md`：该工具的批量提示词汇总
- `<tool>/*.json`：单任务结构化载荷
- `<tool>/*.md`：单任务人工复核/复制粘贴版

## ⚙️ 高级配置

如果你觉得生成速度太慢，或者遇到请求超时，可以打开 `src/config.py` 修改以下全局参数：

```python
# src/config.py
MAX_RETRIES = 3           # 最大重试次数
API_DELAY_SECONDS = 10    # 每次请求间的基础休眠时间(秒)，建议不要低于 5 秒以免触发风控
```

如果遇到登录失效或浏览器环境异常，建议先执行：

```bash
notebooklm doctor
python login.py
```

## 🧪 常用命令

### 整本正常生成

```bash
python main.py --notebook-title "<你的笔记本标题>"
```

### 整本强制重生成

```bash
python main.py --notebook-title "<你的笔记本标题>" --force-regenerate
```

### 单章强制重生成

```bash
python main.py --notebook-title "<你的笔记本标题>" --chapter-title "<章节标题>" --force-regenerate
```

### 按章节序号测试

```bash
python main.py --notebook-title "<你的笔记本标题>" --chapter-index 3 --force-regenerate
```

## 📝 当前已落地功能清单

- 登录预检、失败分类、自动重登与重连恢复
- 按笔记本 ID / 标题 / 序号直接选择
- 完成度检测与断点续传
- 历史结构化回退修复
- 结构化 block 入库与按章导出
- Mermaid 质量检查、自动修复与人工检查汇总
- 质量报告驱动的小节重生成（当前包含 warning）
- 小节风格判定：文字推理 / 公式推导 / 混合
- 二值判定：是否需要严谨推导补充 / 是否需要可渲染图示
- 分阶段提示词链路：`guide` / `derivation` / `visual`
- `快速学习指南`、`章节速查表`、`结构化资料`、`可渲染图示`、`质量报告` 导出

## 📘 `EXAM_PROMPTS_GUIDE.md` 的用途

`EXAM_PROMPTS_GUIDE.md` 现在定位为一份**可选的手动提示词参考**，主要用于：

- 在 NotebookLM 网页端临时试探某类提问方式
- 在修改主提示词前，先快速验证某个表达方向
- 为特殊学科或特殊章节补一条一次性的手动提问模板

它不是主流程入口，也不是使用本仓库的必读文档。正常使用时，优先运行 `main.py` 或 `entropy-note` 即可。

## 🙏 致谢

- 感谢 [Google NotebookLM](https://notebooklm.google.com/) 提供底层产品能力与交互体验启发
- 感谢 [`notebooklm-py`](https://pypi.org/project/notebooklm-py/) 提供 Python 侧登录、会话与访问能力
- 感谢 NotebookLM、`notebooklm-py` 及相关生态中的贡献者，为这一类学习自动化工作流提供基础设施与思路

## ⚠️ 声明

- 本项目是基于 NotebookLM 与 `notebooklm-py` 构建的独立上层应用，与 Google 或 `notebooklm-py` 官方维护者无隶属关系
- `NotebookLM`、`Google` 及相关名称均属于其各自权利人
- 使用者应自行遵守相关服务条款、账号规范以及资料版权要求
- 本仓库聚焦学习资料整理与导出流程，不对第三方服务的可用性、接口稳定性或政策变化作保证

更多许可与声明说明可见 [LICENSE](LICENSE) 与 [NOTICE.md](NOTICE.md)。
