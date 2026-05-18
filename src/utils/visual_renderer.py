from __future__ import annotations

import logging

from src.config import MERMAID_RENDER_TIMEOUT_SECONDS

logger = logging.getLogger("VisualRenderer")

_MERMAID_RENDER_PAGE = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    html, body {
      margin: 0;
      padding: 0;
      background: white;
    }
    #render-root {
      display: inline-block;
      padding: 20px;
      background: white;
    }
  </style>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
</head>
<body>
  <div id="render-root"></div>
  <script>
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "loose",
      theme: "default",
      flowchart: {
        useMaxWidth: false,
        htmlLabels: true,
        nodeSpacing: 28,
        rankSpacing: 36
      }
    });

    window.renderMermaidSvg = async (code) => {
      const renderId = "m" + Date.now() + "_" + Math.floor(Math.random() * 100000);
      const result = await mermaid.render(renderId, code);
      return result.svg;
    };
  </script>
</body>
</html>
"""


class MermaidSvgRenderer:
    def __init__(self, timeout_seconds: int = MERMAID_RENDER_TIMEOUT_SECONDS):
        self.timeout_seconds = timeout_seconds
        self._playwright = None
        self._browser = None
        self._page = None

    def __enter__(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            logger.warning("Mermaid 预渲染不可用：Playwright 未正确安装。详情: %s", exc)
            return self

        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch()
            self._page = self._browser.new_page(viewport={"width": 1600, "height": 1200})
            self._page.set_content(_MERMAID_RENDER_PAGE, wait_until="load")
            self._page.wait_for_function(
                "() => typeof window.renderMermaidSvg === 'function'",
                timeout=self.timeout_seconds * 1000,
            )
        except Exception as exc:
            logger.warning("Mermaid 预渲染初始化失败，将回退源码导出。详情: %s", exc)
            self.close()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def close(self):
        if self._page is not None:
            self._page.close()
            self._page = None
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    @property
    def available(self) -> bool:
        return self._page is not None

    def render_to_svg(self, mermaid_code: str) -> str:
        if not self.available:
            return ""
        try:
            svg = self._page.evaluate(
                "(code) => window.renderMermaidSvg(code)",
                mermaid_code,
            )
            return str(svg or "").strip()
        except Exception as exc:
            logger.warning("Mermaid 预渲染失败，将回退源码导出。详情: %s", exc)
            return ""
