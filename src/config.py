import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NOTEBOOKLM_HOME = PROJECT_ROOT / ".notebooklm"
NOTEBOOKLM_HOME = Path(os.environ.get("NOTEBOOKLM_HOME", str(DEFAULT_NOTEBOOKLM_HOME))).expanduser().resolve()
os.environ["NOTEBOOKLM_HOME"] = str(NOTEBOOKLM_HOME)

# 全局配置
DB_PATH = str(PROJECT_ROOT / "study_guide.db")
OUTPUT_DIR = str(PROJECT_ROOT / "outputs")
MAX_RETRIES = 4
API_DELAY_SECONDS = 15  # 防止封号的请求间隔（建议不低于 15 秒）
RETRY_BASE_SECONDS = 5
RETRY_MAX_SECONDS = 30
PUBLISH_MIN_AVERAGE_SCORE = 80
PUBLISH_MAX_ERROR_COUNT = 0
PUBLISH_MAX_WARNING_COUNT = 12

# 导出模式
# True: 优先个人学习，只导出核心学习文件；保留发布能力但默认不生成相关文件。
# False: 同时导出漫画提示词、图像任务、可渲染图示与发布闸门等增强文件。
LEARNING_FIRST_MODE = True

# 图示插入模式
# source_code: 保持 Mermaid / SVG 源码块
# rendered_images: 优先插入项目内预渲染图片，失败时回退源码块
# hybrid: 同时插入图片与源码块
RENDERABLE_VISUAL_EMBED_MODE = os.environ.get(
    "ENTROPY_NOTE_VISUAL_EMBED_MODE",
    "rendered_images",
).strip().lower() or "rendered_images"
if RENDERABLE_VISUAL_EMBED_MODE not in {"source_code", "rendered_images", "hybrid"}:
    RENDERABLE_VISUAL_EMBED_MODE = "rendered_images"

RENDERED_VISUALS_DIRNAME = "_rendered_visuals"
MERMAID_RENDER_TIMEOUT_SECONDS = int(os.environ.get("ENTROPY_NOTE_MERMAID_RENDER_TIMEOUT", "25"))

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(NOTEBOOKLM_HOME, exist_ok=True)
