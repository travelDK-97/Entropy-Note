import argparse
import os
import sys
import subprocess

from src.config import NOTEBOOKLM_HOME
from src.core.diagnostics import diagnose_exception

os.environ["NOTEBOOKLM_HOME"] = str(NOTEBOOKLM_HOME)

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="启动 notebooklm login，并复用当前项目的 NOTEBOOKLM_HOME 配置。"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="等待登录完成的最长秒数，默认 180。",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    print("正在启动登录流程，这可能会打开一个浏览器窗口...")
    print(f"当前 NOTEBOOKLM_HOME: {NOTEBOOKLM_HOME}")
    print("请在浏览器中完成登录，并在终端提示时按回车确认。")
    try:
        result = subprocess.run(
            ["notebooklm", "login"],
            text=True,
            timeout=args.timeout,
        )
    except Exception as e:
        diag = diagnose_exception(e, stage="notebooklm login")
        print(f"\n登录启动失败[{diag.failure_type.value}]: {diag.summary}\n建议: {diag.action}\n详情: {diag.details}")
        sys.exit(1)

    if result.returncode != 0:
        diag = diagnose_exception(
            RuntimeError(f"notebooklm login failed with code {result.returncode}"),
            stage="notebooklm login",
        )
        print(f"\n登录失败[{diag.failure_type.value}]: {diag.summary}\n建议: {diag.action}\n详情: 返回码 {result.returncode}")
        sys.exit(result.returncode)

    print("\n登录成功，后续可以直接运行主流程。")


if __name__ == "__main__":
    main()
