from typing import Any, Dict, Optional, Tuple
import os
from urllib.parse import urlparse, urlunparse

from .init_patches import apply as apply_init_patches


def create_context(
    p,
    persona: Dict,
    storage_state_path: Optional[str],
    headless: bool,
    skip_init_patches: bool = False,
    enable_header_sanitize: bool = True,
    enable_domain_pin: bool = True,
) -> Tuple[Any, Any]:
    browser = p.chromium.launch(headless=headless)
    viewport = persona.get("viewport", {})
    context = browser.new_context(
        storage_state=storage_state_path if storage_state_path and os.path.exists(storage_state_path) else None,
        user_agent=persona.get("user_agent"),
        locale=(persona.get("accept_language", "zh-TW").split(",")[0]).strip(),
        timezone_id=persona.get("timezone_id", "Asia/Taipei"),
        viewport={"width": viewport.get("width", 1200), "height": viewport.get("height", 900)},
        device_scale_factor=viewport.get("device_scale_factor", 2),
    )

    # 僅設定安全的 Accept-Language，避免對所有子資源加上非簡單標頭導致 CORS 預檢失敗
    try:
        context.set_extra_http_headers({
            "Accept-Language": persona.get("accept_language", "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"),
        })
    except Exception:
        pass

    # 注入與 persona 綁定的 init scripts（可透過旗標關閉以做 A/B 診斷）
    if not skip_init_patches:
        apply_init_patches(context, persona)

    # 全域攔截：移除容易觸發 CORS preflight 的 header；並將 threads.com 導航固定到 threads.net
    if enable_header_sanitize or enable_domain_pin:
        def _route_handler(route, request):
            try:
                url = request.url
                rtype = None
                try:
                    rtype = request.resource_type
                except Exception:
                    rtype = None
                headers = None
                try:
                    headers = dict(request.headers)
                except Exception:
                    headers = None

                new_url = None
                if enable_domain_pin:
                    try:
                        u = urlparse(url)
                        host = (u.netloc or "").lower()
                        if host.endswith("threads.com"):
                            # 導航類型或主文檔請求才改寫 URL
                            if getattr(request, "is_navigation_request", lambda: False)():
                                new_netloc = host.replace("threads.com", "threads.net")
                                u2 = u._replace(netloc=new_netloc)
                                new_url = urlunparse(u2)
                    except Exception:
                        new_url = None

                new_headers = None
                if enable_header_sanitize and headers is not None:
                    # 僅在非 document 子資源上移除 upgrade-insecure-requests
                    try:
                        if str(rtype).lower() != "document":
                            for k in list(headers.keys()):
                                if k.lower() == "upgrade-insecure-requests":
                                    headers.pop(k, None)
                        new_headers = headers
                    except Exception:
                        new_headers = headers

                if new_url and new_headers is not None:
                    return route.continue_(url=new_url, headers=new_headers)
                if new_url:
                    return route.continue_(url=new_url)
                if new_headers is not None:
                    return route.continue_(headers=new_headers)
                return route.continue_()
            except Exception:
                return route.continue_()

        try:
            context.route("**/*", _route_handler)
        except Exception:
            pass
    return browser, context
