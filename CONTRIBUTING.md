# Contributing

感谢你对 `entropy-note` 的关注。

这份文档只保留最需要的协作约定，目标是让贡献者能快速搭建环境、理解项目边界，并尽量避免把本地状态或一次性产物带进仓库。

## 开发环境

建议使用：

- Python `3.10+`
- `pip`
- `Playwright`

推荐初始化步骤：

```bash
# 1. 创建并激活虚拟环境
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# 2. 安装依赖
pip install -r requirements.txt

# 3. 安装 Playwright 浏览器
python -m playwright install

# 4. 可选：以可编辑模式安装项目
pip install -e .
```

## 本地配置

项目默认会把本地 NotebookLM 状态保存到仓库根目录下的 `.notebooklm/`。

如果你希望使用其他目录，可以通过环境变量覆盖：

```bash
# Windows PowerShell
$env:NOTEBOOKLM_HOME = ".notebooklm"
```

注意：

- 不要把你自己的 `.notebooklm/`、`outputs/`、`study_guide.db` 提交到仓库
- 不要在代码中写死你自己的绝对路径

## 常用命令

登录：

```bash
python login.py
```

或：

```bash
entropy-note-login
```

运行主流程：

```bash
python main.py --notebook-title "<你的笔记本标题>"
```

或：

```bash
entropy-note --notebook-title "<你的笔记本标题>"
```

只跑单章/单节：

```bash
entropy-note --notebook-title "<你的笔记本标题>" --chapter-index 1 --section-index 2 --force-regenerate
```

查看图像任务工具帮助：

```bash
entropy-note-image-tasks --help
```

查看图示后处理工具帮助：

```bash
entropy-note-render-visuals --help
```

## 提交前检查

至少执行以下检查：

```bash
python -m py_compile main.py login.py run_image_tasks.py run_visual_postprocess.py
```

如果你改了 `src/` 下的核心模块，建议再补跑：

```bash
python -m py_compile src/config.py src/core/client.py src/core/quality.py src/db/manager.py src/prompts/markdown_prompts.py src/prompts/section_style.py src/utils/exporter.py src/utils/mermaid.py src/utils/visual_renderer.py
```

如果你修改了打包或 CLI 入口，建议确认这些命令仍然可用：

```bash
entropy-note --help
entropy-note-login --help
entropy-note-image-tasks --help
entropy-note-render-visuals --help
```

## 提交内容建议

欢迎以下类型的改动：

- 修复 NotebookLM 主流程中的稳定性问题
- 改进结构化解析、质量检查与导出链路
- 改进 Obsidian 友好的图示导出，尤其是 SVG / Mermaid
- 改进已完成笔记本的独立后处理链路，例如图片写回与总索引状态更新
- 完善 README、CI、开发文档与发布体验

请尽量避免：

- 顺手混入无关重构
- 提交一次性测试产物
- 提交与你本地账号或环境强绑定的配置
- 在没有验证的情况下大幅改动提示词主链路

## 当前项目约定

提交涉及主流程时，请尽量遵守这些约定：

- 优先服务学习主链路，而不是发布型花活
- 节级首判应尽量前置：优先在大纲阶段判断是否需要推导、是否需要图示、图示类型与比例
- 经济学曲线类内容优先走 `SVG`，不要默认回退成框图
- 导出结果优先考虑 Obsidian 阅读体验
- 长时间等待不应轻易判定为异常，优先保持阶段进度可落库

## Pull Request 建议

如果你提交 PR，建议说明：

- 改动动机
- 影响范围
- 是否改动了数据库结构、提示词结构或导出结构
- 你本地做了哪些验证

一个简洁模板如下：

```text
## 变更内容
- 

## 变更原因
- 

## 验证方式
- 

## 风险与影响
- 
```
