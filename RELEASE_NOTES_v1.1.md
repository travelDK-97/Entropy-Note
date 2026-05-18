# Entropy Note v1.1 提交说明

## 版本定位

`v1.1` 重点补强主链路稳定性、正式目录控制和 Obsidian 图示体验，不追求额外扩大战场。

这一版的核心目标：

- 让大纲抽取能区分“核心学习输出”和“按资源正式目录输出”
- 修复认证恢复中的终端交互问题
- 让分章导出和总索引更完整地体现来源与生成说明
- 把 Mermaid / SVG 的图片写回能力拆成独立后处理步骤，便于处理已完成笔记本

## 主要更新

### 1. 大纲模式切换

- 新增大纲模式选择，支持：
  - `core`
  - `official_from_sources`
- 普通学习资料默认仍走核心学习输出
- 法规、教材、目录结构严格的资料可切到正式目录模式
- outline 缓存按模式隔离，避免不同模式互相污染

### 2. 登录恢复修复

- 修复自动登录恢复时吞掉 `notebooklm login` 终端确认的问题
- 登录命令恢复为可见交互，避免浏览器登录后终端无法确认状态

### 3. 导出说明与参考来源补充

- 分章导出文件统一补充“由 NotebookLM 与 Entropy Note 协同生成”的完成说明
- 总索引和分章目录支持写入参考文档来源
- 更适合在 Obsidian 中回看引用出处和判断文档来源

### 4. 独立图示后处理

- 新增 `run_visual_postprocess.py`
- 新增 CLI 入口 `entropy-note-render-visuals`
- 支持对已完成笔记本执行：
  - Mermaid 预渲染为 SVG
  - SVG 资产统一落盘
  - Markdown 图示引用重写
- 支持三种写回模式：
  - `source_code`
  - `rendered_images`
  - `hybrid`

### 5. 总索引状态写回

- 图示后处理完成后，自动更新 `00_总索引.md`
- 总索引会记录：
  - 是否已执行图示后处理
  - 文档写回模式
  - 写入图示资产数
  - 涉及小节数

### 6. 文档与版本同步

- README 更新到 `v1.1` 工作流
- AGENTS / CONTRIBUTING 补充新入口、新验证命令和后处理风险点
- `pyproject.toml` 版本提升到 `1.1.0`

## 影响文件

- `main.py`
- `src/core/client.py`
- `src/db/manager.py`
- `src/utils/exporter.py`
- `src/utils/visual_renderer.py`
- `src/config.py`
- `run_visual_postprocess.py`
- `README.md`
- `AGENTS.md`
- `CONTRIBUTING.md`
- `pyproject.toml`

## 验证情况

已完成以下验证：

- `python -m py_compile main.py login.py run_image_tasks.py run_visual_postprocess.py src\config.py src\core\client.py src\core\quality.py src\db\manager.py src\prompts\markdown_prompts.py src\prompts\section_style.py src\utils\exporter.py src\utils\mermaid.py src\utils\visual_renderer.py`
- `python run_visual_postprocess.py --help`
- 临时数据库样本验证：
  - 可对已完成笔记本执行图示后处理
  - 可生成 `_rendered_visuals/`
  - 可把图示写回 Markdown
  - 可自动更新 `00_总索引.md`

## 建议提交信息

```text
release: prepare v1.1 with outline modes and visual postprocess
```
