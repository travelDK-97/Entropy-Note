from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class FailureType(str, Enum):
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    NETWORK = "network"
    SERVICE = "service"
    STORAGE = "storage"
    BROWSER = "browser"
    DEPENDENCY = "dependency"
    CONFIG = "config"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FailureDiagnosis:
    failure_type: FailureType
    summary: str
    action: str
    retryable: bool
    wait_seconds: Optional[int] = None
    stage: Optional[str] = None
    details: Optional[str] = None


def _flatten_exception_messages(exc: BaseException) -> str:
    parts: list[str] = []
    seen: set[int] = set()
    cur: Optional[BaseException] = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        msg = str(cur).strip()
        if msg:
            parts.append(msg)
        cur = cur.__cause__ or cur.__context__
    return " | ".join(parts)


def _exc_details(exc: BaseException) -> str:
    return f"{exc.__class__.__module__}.{exc.__class__.__name__}: {exc}"


def diagnose_exception(exc: BaseException, *, stage: Optional[str] = None) -> FailureDiagnosis:
    msg = _flatten_exception_messages(exc)
    msg_l = msg.lower()
    details = _exc_details(exc)

    notebooklm_home = os.environ.get("NOTEBOOKLM_HOME")
    notebooklm_home_l = (notebooklm_home or "").lower()

    def storage_action() -> str:
        base = "请先运行 `python login.py` 或 `notebooklm login` 完成授权。"
        if notebooklm_home:
            base += f" 当前 NOTEBOOKLM_HOME={notebooklm_home}。"
        return base

    try:
        import httpx  # type: ignore
    except Exception:
        httpx = None  # type: ignore

    if isinstance(exc, FileNotFoundError) and ("notebooklm" in msg_l or "[winerror 2]" in msg_l):
        return FailureDiagnosis(
            failure_type=FailureType.DEPENDENCY,
            summary="未找到 notebooklm 命令或可执行文件。",
            action="确认已安装依赖并且 notebooklm 在 PATH 中（建议先运行 `pip install -r requirements.txt`）。",
            retryable=False,
            stage=stage,
            details=details,
        )

    if isinstance(exc, (PermissionError, OSError)) and notebooklm_home_l and notebooklm_home_l in msg_l:
        return FailureDiagnosis(
            failure_type=FailureType.STORAGE,
            summary="NotebookLM 本地存储目录不可读/不可写。",
            action=f"检查 {notebooklm_home} 的权限，或把 NOTEBOOKLM_HOME 指向一个可写目录后重新登录。",
            retryable=False,
            stage=stage,
            details=details,
        )

    if "notebooklm_home" in msg_l and ("not set" in msg_l or "missing" in msg_l):
        return FailureDiagnosis(
            failure_type=FailureType.CONFIG,
            summary="NOTEBOOKLM_HOME 未正确配置。",
            action="请先运行 `python login.py` 或手动设置 NOTEBOOKLM_HOME 指向可写目录后再试。",
            retryable=False,
            stage=stage,
            details=details,
        )

    if any(
        k in msg_l
        for k in [
            "authentication expired",
            "unauthorized",
            "unauthenticated",
            "not logged in",
            "login required",
            "status code 16",
        ]
    ):
        return FailureDiagnosis(
            failure_type=FailureType.AUTH,
            summary="认证已过期或未登录。",
            action=storage_action(),
            retryable=False,
            stage=stage,
            details=details,
        )

    if any(k in msg_l for k in ["captcha", "verify you are human", "unusual traffic", "robot", "blocked", "access denied"]):
        return FailureDiagnosis(
            failure_type=FailureType.BROWSER,
            summary="疑似触发风控/验证码拦截，NotebookLM 返回了人机校验页面或被阻断。",
            action="请在网页端打开 NotebookLM，完成验证码/确认后再重试；同时适当增大请求间隔（API_DELAY_SECONDS）。",
            retryable=False,
            stage=stage,
            details=details,
        )

    if any(k in msg_l for k in ["executable doesn't exist", "failed to launch", "browser has been closed", "browser type", "playwright"]):
        return FailureDiagnosis(
            failure_type=FailureType.BROWSER,
            summary="浏览器/Playwright 启动失败或浏览器可执行文件缺失。",
            action="尝试运行 `python -m playwright install` 安装浏览器，或检查系统是否禁止自动拉起浏览器。",
            retryable=False,
            stage=stage,
            details=details,
        )

    if httpx is not None:
        if isinstance(exc, httpx.HTTPStatusError):
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (401, 403):
                return FailureDiagnosis(
                    failure_type=FailureType.AUTH,
                    summary=f"服务返回 {status}，认证无效或权限不足。",
                    action=storage_action(),
                    retryable=False,
                    stage=stage,
                    details=details,
                )
            if status == 429:
                return FailureDiagnosis(
                    failure_type=FailureType.RATE_LIMIT,
                    summary="服务返回 429，请求过于频繁或触发限流。",
                    action="请等待更久再试，并适当增大请求间隔（API_DELAY_SECONDS）。",
                    retryable=True,
                    wait_seconds=90,
                    stage=stage,
                    details=details,
                )
            if status is not None and status >= 500:
                return FailureDiagnosis(
                    failure_type=FailureType.SERVICE,
                    summary=f"服务返回 {status}，上游服务暂时不可用。",
                    action="稍后重试；如果持续出现，可能是服务端变更或故障。",
                    retryable=True,
                wait_seconds=20,
                    stage=stage,
                    details=details,
                )
            return FailureDiagnosis(
                failure_type=FailureType.SERVICE,
                summary=f"服务返回 {status}，请求被拒绝或参数不合法。",
                action="如果是刚升级依赖/服务端变更导致，建议贴出完整报错信息以便适配。",
                retryable=False,
                stage=stage,
                details=details,
            )

        if isinstance(
            exc,
            (
                httpx.TimeoutException,
                httpx.ConnectError,
                httpx.ReadError,
                httpx.RemoteProtocolError,
                httpx.NetworkError,
                httpx.RequestError,
            ),
        ):
            return FailureDiagnosis(
                failure_type=FailureType.NETWORK,
                summary="网络连接失败/超时（可能与代理、TLS、公司网络策略有关）。",
                action="检查网络与代理设置，确认能正常访问 Google/NotebookLM；必要时更换网络环境后重试。",
                retryable=True,
                wait_seconds=10,
                stage=stage,
                details=details,
            )

    if any(k in msg_l for k in ["connection", "timeout", "timed out", "econnreset", "reset by peer", "tls", "ssl"]):
        return FailureDiagnosis(
            failure_type=FailureType.NETWORK,
            summary="网络连接失败/超时。",
            action="检查网络与代理设置；确认能正常打开 NotebookLM 网页端后再试。",
            retryable=True,
            wait_seconds=10,
            stage=stage,
            details=details,
        )

    if notebooklm_home and any(k in msg_l for k in [notebooklm_home_l, "storage", "token", "credentials"]):
        return FailureDiagnosis(
            failure_type=FailureType.STORAGE,
            summary="读取本地登录信息失败（可能未登录或登录信息损坏）。",
            action=storage_action(),
            retryable=False,
            stage=stage,
            details=details,
        )

    return FailureDiagnosis(
        failure_type=FailureType.UNKNOWN,
        summary="未知错误，暂无法自动归类。",
        action="请把终端里的完整报错（包含 traceback）贴出来，我会补充更精确的检测规则。",
        retryable=True,
        wait_seconds=10,
        stage=stage,
        details=details,
    )
