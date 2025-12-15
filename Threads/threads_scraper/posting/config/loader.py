import os
import yaml
from typing import Any, Dict, Optional

_DEFAULT_RUNTIME = os.path.join(os.path.dirname(__file__), "runtime.yaml")


def _as_range(val, fallback):
    try:
        if isinstance(val, (list, tuple)) and len(val) == 2:
            return (int(val[0]), int(val[1]))
        if isinstance(val, str) and "-" in val:
            a, b = val.split("-", 1)
            return (int(a), int(b))
    except Exception:
        pass
    return fallback


def load_runtime_cfg(path: Optional[str] = None, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    path = path or _DEFAULT_RUNTIME
    data: Dict[str, Any] = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    # humanize
    hz = data.get("humanize", {})
    pre_rng = _as_range(hz.get("pre_feed_seconds"), (60, 90))
    post_rng = _as_range(hz.get("post_feed_seconds"), (30, 60))
    step_rng = _as_range(hz.get("scroll_step_px"), (180, 420))
    pause_rng = _as_range(hz.get("scroll_pause_ms"), (120, 360))
    micro_mouse = bool(hz.get("micro_mouse", True))
    initial_idle_rng = _as_range(hz.get("initial_idle_seconds"), (2, 5))

    # timeouts
    to = data.get("timeouts", {})
    to_home = int(to.get("goto_home_ms", 30000))
    to_profile = int(to.get("goto_profile_ms", 30000))
    to_selector = int(to.get("selector_ms", 8000))

    # typing
    ty = data.get("typing", {})
    per_char_rng = _as_range(ty.get("per_char_ms"), (50, 120))
    para_selector = str(ty.get("para_selector", "p[class]"))

    # retry
    rt = data.get("retry", {})
    max_retries = int(rt.get("max_retries", 1))

    # risk
    rk = data.get("risk", {})
    risk_mode = rk.get("mode", "warn")
    stop_on_r3_live = bool(rk.get("stop_on_r3_live", True))
    risk_ceiling = rk.get("ceiling", None)  # e.g., "R1"/"R2"/"R3" or None
    enforce_cooldown_on_r3 = bool(rk.get("enforce_cooldown_on_r3", False))
    cooldown_on_r3_s = int(rk.get("cooldown_on_r3_s", 3600))

    # modules (feature toggles)
    md = data.get("modules", {})
    mod_scroll = bool(md.get("scroll", True))
    mod_composer = bool(md.get("composer", True))
    mod_typing = bool(md.get("typing", True))

    # navigation options
    nv = data.get("nav", {})
    repin_after_spa = bool(nv.get("repin_after_spa", True))
    suppress_media = bool(nv.get("suppress_media", False))

    cfg = {
        "humanize": {
            "pre_feed_seconds": pre_rng,
            "post_feed_seconds": post_rng,
            "scroll_step_px": step_rng,
            "scroll_pause_ms": pause_rng,
            "micro_mouse": micro_mouse,
            "initial_idle_seconds": initial_idle_rng,
        },
        "timeouts": {
            "goto_home_ms": to_home,
            "goto_profile_ms": to_profile,
            "selector_ms": to_selector,
        },
        "typing": {
            "per_char_ms": per_char_rng,
            "para_selector": para_selector,
        },
        "retry": {
            "max_retries": max_retries,
        },
        "risk": {
            "mode": risk_mode,
            "stop_on_r3_live": stop_on_r3_live,
            "ceiling": risk_ceiling,
            "enforce_cooldown_on_r3": enforce_cooldown_on_r3,
            "cooldown_on_r3_s": cooldown_on_r3_s,
        },
        "modules": {
            "scroll": mod_scroll,
            "composer": mod_composer,
            "typing": mod_typing,
        },
        "nav": {
            "repin_after_spa": repin_after_spa,
            "suppress_media": suppress_media,
        },
        # mode 2 (reply) config block
        "reply": {
            "permalink": (data.get("reply", {}) or {}).get("permalink"),
            "text": (data.get("reply", {}) or {}).get("text"),
            "text_file": (data.get("reply", {}) or {}).get("text_file"),
            "selectors": {
                # primary + fallbacks combined; adapter will use first-hit
                "reply_icon_svg": ((data.get("reply", {}) or {}).get("selectors", {}) or {}).get(
                    "reply_icon_svg",
                    "div.x6s0dn4.x78zum5.xl56j7k.xezivpi div.x6s0dn4.x17zd0t2.x78zum5.xl56j7k svg.x1lliihq.x2lah0s.x1n2onr6.x16ye13r.x5lhr3w.x1i0azm7.xbh8q5q.x73je2i.x1f6yumg.xvlca1e, svg[aria-label*='回覆' i], svg[aria-label*='Reply' i]",
                ),
                "composer_open_check": ((data.get("reply", {}) or {}).get("selectors", {}) or {}).get(
                    "composer_open_check",
                    "div[contenteditable='true']",
                ),
                "editor_input": ((data.get("reply", {}) or {}).get("selectors", {}) or {}).get(
                    "editor_input",
                    "div[contenteditable='true'], div.x78zum5.xdt5ytf.x1iyjqo2.x6ikm8r div.x1n2onr6 div.xzsf02u.xw2csxc.x1odjw0f.x1n2onr6.x1hnll1o.xpqswwc.notranslate",
                ),
                # only publish candidates are used for merge in service
                "publish_candidates": ((data.get("reply", {}) or {}).get("selectors", {}) or {}).get(
                    "publish_candidates",
                    [
                        "div.x6s0dn4.x9f619.x78zum5.x15zctf7.x18r3tyq.x1qughib.x1p5oq8j.x64bnmy.xwxc41k.x13jy36j.xh8yej3 div.x2lah0s div.xc26acl.x6s0dn4.x78zum5.xl56j7k.x6ikm8r.x10wlt62.xf7dkkf.xv54qhq.xlyipyv.xp07o12",
                    ],
                ),
            },
        },
    }

    # apply overrides from CLI strings
    overrides = overrides or {}
    # humanize ranges via "60-90" like strings
    if "humanize_pre" in overrides:
        cfg["humanize"]["pre_feed_seconds"] = _as_range(overrides["humanize_pre"], cfg["humanize"]["pre_feed_seconds"])
    if "humanize_post" in overrides:
        cfg["humanize"]["post_feed_seconds"] = _as_range(overrides["humanize_post"], cfg["humanize"]["post_feed_seconds"])
    if "initial_idle" in overrides:
        cfg["humanize"]["initial_idle_seconds"] = _as_range(overrides["initial_idle"], cfg["humanize"]["initial_idle_seconds"])

    if "risk_mode" in overrides:
        cfg["risk"]["mode"] = str(overrides["risk_mode"]).strip().lower()
    if "stop_on_r3_live" in overrides:
        cfg["risk"]["stop_on_r3_live"] = bool(int(overrides["stop_on_r3_live"]))
    if "risk_ceiling" in overrides and overrides["risk_ceiling"]:
        cfg["risk"]["ceiling"] = str(overrides["risk_ceiling"]).strip().upper()
    if "enforce_cooldown_on_r3" in overrides:
        cfg["risk"]["enforce_cooldown_on_r3"] = bool(int(overrides["enforce_cooldown_on_r3"]))
    if "cooldown_on_r3_s" in overrides:
        cfg["risk"]["cooldown_on_r3_s"] = int(overrides["cooldown_on_r3_s"])

    # optional timeout overrides
    if "selector_timeout" in overrides:
        cfg["timeouts"]["selector_ms"] = int(overrides["selector_timeout"])
    if "goto_home_ms" in overrides:
        cfg["timeouts"]["goto_home_ms"] = int(overrides["goto_home_ms"])
    if "goto_profile_ms" in overrides:
        cfg["timeouts"]["goto_profile_ms"] = int(overrides["goto_profile_ms"])

    # typing overrides
    if "per_char_ms" in overrides:
        cfg["typing"]["per_char_ms"] = _as_range(overrides["per_char_ms"], cfg["typing"]["per_char_ms"])
    if "editor_para_selector" in overrides:
        cfg["typing"]["para_selector"] = str(overrides["editor_para_selector"]) or cfg["typing"]["para_selector"]

    # module toggles
    if "enable_scroll" in overrides:
        cfg["modules"]["scroll"] = bool(int(overrides["enable_scroll"]))
    if "enable_composer" in overrides:
        cfg["modules"]["composer"] = bool(int(overrides["enable_composer"]))
    if "enable_typing" in overrides:
        cfg["modules"]["typing"] = bool(int(overrides["enable_typing"]))

    # navigation override
    if "repin_after_spa" in overrides:
        cfg["nav"]["repin_after_spa"] = bool(int(overrides["repin_after_spa"]))
    if "suppress_media" in overrides:
        cfg["nav"]["suppress_media"] = bool(int(overrides["suppress_media"]))

    # reply overrides
    if "reply_permalink" in overrides and overrides["reply_permalink"]:
        cfg["reply"]["permalink"] = str(overrides["reply_permalink"]).strip()
    if "reply_text" in overrides and overrides["reply_text"]:
        cfg["reply"]["text"] = str(overrides["reply_text"]).rstrip()
    if "reply_text_file" in overrides and overrides["reply_text_file"]:
        cfg["reply"]["text_file"] = str(overrides["reply_text_file"]).strip()

    # reply selector overrides (string or comma-separated for publish_candidates)
    if "reply_selector_reply_icon_svg" in overrides and overrides["reply_selector_reply_icon_svg"]:
        cfg["reply"]["selectors"]["reply_icon_svg"] = str(overrides["reply_selector_reply_icon_svg"]).strip()
    if "reply_selector_composer_open_check" in overrides and overrides["reply_selector_composer_open_check"]:
        cfg["reply"]["selectors"]["composer_open_check"] = str(overrides["reply_selector_composer_open_check"]).strip()
    if "reply_selector_editor_input" in overrides and overrides["reply_selector_editor_input"]:
        cfg["reply"]["selectors"]["editor_input"] = str(overrides["reply_selector_editor_input"]).strip()
    if "reply_selector_publish_candidates" in overrides and overrides["reply_selector_publish_candidates"]:
        raw = str(overrides["reply_selector_publish_candidates"]).strip()
        if raw:
            cfg["reply"]["selectors"]["publish_candidates"] = [s.strip() for s in raw.split(',') if s.strip()]

    return cfg
