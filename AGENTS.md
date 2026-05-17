# AGENTS Guide

这份文档面向后续继续修改本项目的 agent、自动化协作者或未来的新会话。

目标不是重复 README，而是快速说明：

- 这个仓库的定位
- 不应轻易改偏的主线
- 核心模块的职责边界
- 改动时优先检查的风险点
- 最小验证路径

## 项目定位

- 这是一个构建在 `notebooklm-py` 之上的上层学习资料流水线
- 它不是 `notebooklm-py` 的 fork
- 仓库重点不在 SDK 封装，而在：
  - 分阶段提示词生成
  - SQLite 落库与断点续传
  - 结构化 block
  - SVG / Mermaid 图示
  - 质量报告
  - Obsidian 友好导出

## 当前主目标

- 保证学习资料主链路随时可跑通
- 输出优先服务 Obsidian 阅读体验
- 让节级判断尽量前置，而不是后补
- 让长等待场景下的阶段进度可落库、可恢复

不要优先做的方向：

- 与主链路无关的发布型花活
- 炫技但不提升学习体验的 UI
- 过度复杂的规则系统

## 已确定的关键约定

### 1. 节级首判前置

首次大纲提取时就应尽量判定：

- `style`
- `derivation_needed`
- `visual_needed`
- `visual_type`
- `visual_ratio`

不要把这些判断推迟到后面的手写规则里再补。

### 2. 曲线类内容优先 SVG

对于明显依赖坐标轴和曲线关系的内容，优先使用：

- `svg_curve`
- `svg_effect_decomposition`

不要默认退回 Mermaid 框图。

Mermaid 更适合：

- 机制流程
- 分类结构
- 层级框架

### 3. 学习优先模式优先

默认仍以 `LEARNING_FIRST_MODE = True` 为主。

优先产物：

- 快速学习指南
- 章节速查表
- 结构化资料
- 可渲染图示
- 质量报告

### 4. 长等待不轻易判异常

NotebookLM 返回慢是常态，不要因为等待时间长就直接判断为卡死。

优先策略：

- 分阶段生成
- 阶段完成即入库
- `guide-only` 可用于快速验证

### 5. 文档保持去个性化

- 不要在公开文档中保留私有笔记本名称
- 不要在仓库中保留本机绝对路径
- 对外文档优先使用通用示例和占位符

## 核心入口

- `main.py`
  - 主流程入口
  - 支持整本、单章、单节、`guide-only`
- `login.py`
  - 统一登录入口
  - 复用项目内的 `NOTEBOOKLM_HOME`
- `run_image_tasks.py`
  - 图像任务后处理入口

## 核心模块

- `src/core/client.py`
  - NotebookLM 连接、认证恢复、重试、大纲提取
- `src/prompts/section_style.py`
  - 节级首判归一化与 fallback
- `src/prompts/markdown_prompts.py`
  - 分阶段提示词、结构化解析、SVG/Mermaid 载体处理
- `src/db/manager.py`
  - SQLite 结构、落库、读取、断点续传
- `src/core/quality.py`
  - 质量检查、轻校正、图示校验
- `src/utils/exporter.py`
  - 各类 Markdown / 图示 / 质量报告导出
- `src/utils/mermaid.py`
  - Mermaid 清洗与 Obsidian 兼容格式化

## 数据结构

当前数据库主表：

- `outlines`
- `guides`
- `section_runs`
- `section_blocks`

说明：

- `section_runs` / `section_blocks` 是当前结构化主链路
- `guides` 仍保留兼容用途，但长期看应尽量减少对其的核心依赖

## 改功能时优先检查

如果你改动了提示词、导出或首判逻辑，优先检查：

- 是否破坏 `visual_type` / `visual_ratio` 的传递
- 是否让 SVG 被回退成 Mermaid 框图
- 是否让质量报告丢失“首判图示类型/比例”
- 是否让 `guide-only` 再次误报缺失 warning
- 是否把一次性手动提示词误塞进主链路文档
- 是否引入本机绝对路径或私有资料名称

## 最小验证路径

### 基础静态检查

```bash
python -m py_compile main.py login.py run_image_tasks.py src\config.py src\core\client.py src\core\diagnostics.py src\core\image_jobs.py src\core\quality.py src\db\manager.py src\prompts\markdown_prompts.py src\prompts\section_style.py src\utils\exporter.py src\utils\mermaid.py
```

### CLI 检查

```bash
entropy-note --help
entropy-note-login --help
entropy-note-image-tasks --help
```

### 代表性回归样本

至少覆盖以下两类小节：

- 依赖曲线关系的章节
- 依赖机制流程或结构框架的章节

建议确认：

- 首判类型符合预期
- 三阶段链路完整跑通
- 质量报告无错误，警告可解释或已清零

## 修改风格建议

- 优先做小而清楚的改动
- 优先保留已有主线，不要随意扩大战场
- 如果发现仓库里有与你当前目标无关的大范围未提交变化，先停下来确认
- 改完后优先给出“改了什么 / 为什么 / 如何验证”的简洁总结
