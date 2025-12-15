def _build_script(persona: dict) -> str:
    languages = persona.get("languages", ["zh-TW", "zh", "en-US"])  # list -> JS array
    platform = persona.get("platform", "MacIntel")
    webgl_vendor = persona.get("webgl_vendor", "Apple")
    webgl_renderer = persona.get("webgl_renderer", "ANGLE (Apple MTL, Apple M2)")
    seed = int(persona.get("fingerprint_noise_seed", 12345))

    langs_js = ",".join([f"'{l}'" for l in languages])

    return f"""
// webdriver 痕跡
Object.defineProperty(navigator, 'webdriver', {{get: () => false}});

// languages 與 platform
Object.defineProperty(navigator, 'languages', {{get: () => [{langs_js}]}});
Object.defineProperty(navigator, 'platform', {{get: () => '{platform}'}});

// plugins 偽裝
Object.defineProperty(navigator, 'plugins', {{get: () => [1,2,3,4,5]}});

// window.chrome 存在
if (!window.chrome) {{ window.chrome = {{ runtime: {{}} }}; }}

// WebGL 覆寫
const _getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {{
  if (parameter === 37445) return '{webgl_vendor}';
  if (parameter === 37446) return '{webgl_renderer}';
  return _getParameter.call(this, parameter);
}};

// Canvas 微噪（可重現，依 seed 決定）
(function() {{
  const seed = {seed};
  function mulberry32(a) {{
    return function() {{
      var t = a += 0x6D2B79F5;
      t = Math.imul(t ^ t >>> 15, t | 1);
      t ^= t + Math.imul(t ^ t >>> 7, t | 61);
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    }}
  }}
  const rand = mulberry32(seed);
  const toDataURL = HTMLCanvasElement.prototype.toDataURL;
  HTMLCanvasElement.prototype.toDataURL = function() {{
    try {{
      const ctx = this.getContext('2d');
      if (ctx) {{
        const w = Math.min(this.width, 64), h = Math.min(this.height, 64);
        const imageData = ctx.getImageData(0, 0, w, h);
        const data = imageData.data;
        for (let i = 0; i < data.length; i += 4) {{
          data[i]   = (data[i]   + Math.floor(rand()*2)) & 0xFF;
          data[i+1] = (data[i+1] + Math.floor(rand()*2)) & 0xFF;
          data[i+2] = (data[i+2] + Math.floor(rand()*2)) & 0xFF;
        }}
        ctx.putImageData(imageData, 0, 0);
      }}
    }} catch (e) {{}}
    return toDataURL.apply(this, arguments);
  }};
}})();

// Permissions query fallback（僅避免報錯）
if (navigator.permissions && navigator.permissions.query) {{
  const _q = navigator.permissions.query.bind(navigator.permissions);
  navigator.permissions.query = (p) => {{
    if (p && p.name === 'notifications') {{
      return Promise.resolve({{ state: 'default' }});
    }}
    return _q(p);
  }};
}}
"""


def apply(context, persona: dict) -> None:
    try:
        script = _build_script(persona)
        # 對所有新頁面生效
        context.add_init_script(script)
    except Exception:
        pass
