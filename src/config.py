import os
import sys

# 强制指定 NotebookLM 的存储目录
os.environ["NOTEBOOKLM_HOME"] = r"C:\Users\84322\code\notebooklm\.notebooklm"

# 全局配置
DB_PATH = "study_guide.db"
OUTPUT_DIR = "outputs"
MAX_RETRIES = 3
API_DELAY_SECONDS = 10  # 防止封号的请求间隔

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)
