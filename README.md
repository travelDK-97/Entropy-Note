# NotebookLM-py 全自动备考复习流水线

这是一个基于 [Google NotebookLM](https://notebooklm.google.com/) 的全自动化复习资料生成工具。专为“数学背景、依赖直觉和逻辑推演、考前突击”的学习者设计。

本项目将零散的“与大模型对话”过程升级为了**模块化、防封号、可断点续传的生产级工程**。

## 🌟 核心特性

- **一键全自动**：自动读取你在 Google NotebookLM 中的资料，自动提取章节大纲，逐章生成复习指南。
- **极致的稳定性**：采用异步 API (Async) 直连，彻底告别 CLI 调用的阻塞与卡顿。
- **安全防封号**：内置了安全的请求延时与指数退避重试机制（默认每章间隔 10 秒），模拟人类真实操作。
- **断点续传**：所有生成的 Prompt 和 Markdown 均实时存入本地 SQLite 数据库 (`study_guide.db`)。如果网络中断，下次启动会自动跳过已生成的章节。
- **纯净 Markdown 导出**：告别容易排版崩溃的 LaTeX，直接输出标准化、高密度的 Markdown 复习材料，存放在 `outputs/` 目录下。

## 📁 项目结构

```text
notebooklm/
├── main.py                     # [入口] 流程控制中心，直接运行此文件
├── requirements.txt            # [依赖] 项目依赖清单
├── study_guide.db              # [数据] SQLite 数据库 (运行后自动生成)
├── outputs/                    # [产物] 生成的 Markdown 文件存放处 (运行后自动生成)
├── EXAM_PROMPTS_GUIDE.md       # [文档] 备考思路与自定义提示词参考
└── src/
    ├── config.py               # [配置] 全局参数 (延时时间/重试次数等)
    ├── core/
    │   └── client.py           # [核心] 封装了防封号安全延时的 NotebookLM 请求客户端
    ├── db/
    │   └── manager.py          # [数据] 专门负责读写 SQLite 数据库，实现断点续传
    ├── prompts/
    │   └── markdown_prompts.py # [提示词] 存放和管理所有的提示词模板
    └── utils/
        └── exporter.py         # [导出] 负责将数据库内容组装成 Markdown
```

## 🚀 快速开始

### 1. 环境准备

确保你已经安装了 Python 3.10+，并创建了虚拟环境。

```bash
# 激活虚拟环境 (Windows)
.\.venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 授权登录 Google 账号

在首次运行前，你需要通过浏览器授权登录 Google 账号（只需操作一次）：

```bash
notebooklm login
```
*(在弹出的浏览器中登录 Google 账号，直到进入 NotebookLM 首页后关闭或返回终端)*

### 3. 开始自动生成

确保你在 NotebookLM 网页端已经创建了一个包含你教材/习题的笔记本。然后运行：

```bash
python main.py
```

- 脚本会列出你账号下的所有笔记本。
- 输入对应的序号。
- 去喝杯咖啡，等待流水线自动完成。
- 在 `outputs/` 文件夹中收取你的期末速读指南！

## ⚙️ 高级配置

如果你觉得生成速度太慢，或者遇到请求超时，可以打开 `src/config.py` 修改以下全局参数：

```python
# src/config.py
MAX_RETRIES = 3           # 最大重试次数
API_DELAY_SECONDS = 10    # 每次请求间的休眠时间(秒)，建议不要低于 5 秒以免触发风控
```
