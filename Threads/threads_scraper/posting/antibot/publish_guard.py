from typing import Any, List, Dict


def arm_dom_neuter(page: Any, publish_selector: str) -> bool:
    """Disable publish button by intercepting clicks and disabling interactions.
    Returns True if script injected without exception.
    """
    script = f"""
(() => {{
  const pubSel = `{publish_selector}`;
  try {{
    document.addEventListener('click', function(e) {{
      const target = e.target;
      if (!target) return;
      const el = target.closest(pubSel);
      if (el) {{
        e.preventDefault();
        e.stopImmediatePropagation();
        try {{ console.log('__BLOCK_PUBLISH__'); }} catch(_e){{}}
      }}
    }}, true);
  }} catch (e) {{}}
}})();
"""
    try:
        page.add_init_script(script)
        # 直接將按鈕 disable & 移除 pointer events（若已存在）
        try:
            page.evaluate(
                "(sel) => { const el = document.querySelector(sel); if (el) { el.setAttribute('disabled','true'); el.style.pointerEvents='none'; el.onclick=null; } }",
                publish_selector,
            )
        except Exception:
            pass
        return True
    except Exception:
        return False


def arm_network_abort(context: Any, intercepts: List[Dict]) -> None:
    """Abort publish-like requests as a safety net. Append first intercept info to intercepts list."""
    def handler(route):
        try:
            req = route.request
            url = req.url
            method = req.method
            is_publish = method.upper() == 'POST' and ('graphql' in url or 'instagram' in url)
            if is_publish:
                if len([i for i in intercepts if i.get('url') == url]) == 0:
                    intercepts.append({"url": url, "method": method})
                return route.abort()
        except Exception:
            pass
        return route.continue_()

    try:
        context.route("**/*", handler)
    except Exception:
        pass
