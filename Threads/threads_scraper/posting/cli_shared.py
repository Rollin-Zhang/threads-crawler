#!/usr/bin/env python3
"""
Shared CLI infrastructure for posting modes.
Reduces duplication between post_new.py and post_reply.py.
"""
import argparse
import json
import os
import sys
from typing import Dict, Any, Optional, Callable


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments common to both new post and reply modes."""
    # Content input
    parser.add_argument("--content-file", dest="content_file", help="Path to text file for content", default=None)
    parser.add_argument("--text-file", dest="text_file", help="Alias of --content-file; overrides if set", default=None)
    
    # Selectors
    parser.add_argument("--selectors-file", dest="selectors_file", help="Path to selectors.yaml", default=None)
    parser.add_argument("--sel-editor", dest="sel_editor", help="Override editor selector", default=None)
    
    # Browser
    parser.add_argument("--headless", dest="headless", action="store_true", help="Run headless browser")
    parser.add_argument("--no-headless", dest="headless", action="store_false", help="Run with a visible browser window")
    parser.set_defaults(headless=True)
    
    # Modes and safety
    parser.add_argument("--timeout", dest="timeout", type=int, default=5000)
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", help="Run until before submit and exit OK")
    parser.add_argument("--verbose", dest="verbose", action="store_true", help="Verbose logs to stdout")
    parser.add_argument("--retries", dest="retries", type=int, default=1, help="Retry count for unstable actions")
    parser.add_argument("--account-id", dest="account_id", default="default", help="Persona/account id for sticky fingerprint")
    parser.add_argument("--rate-mode", dest="rate_mode", choices=["off","observe","enforce"], default="observe")
    parser.add_argument("--run-mode", dest="run_mode", choices=["check","rehearsal","dress","live"], default="rehearsal", help="Safety modes: no real posting unless 'live'")
    parser.add_argument("--ignore-risk-for-check", dest="ignore_risk_for_check", action="store_true", help="Only in run-mode=check: still record risk but continue selector checks without clicking/typing")
    
    # Humanize session
    parser.add_argument("--humanize-session", dest="humanize_session", choices=["on","off"], default=None, help="Human-like pre/post browsing: default off in check; on otherwise")
    parser.add_argument("--humanize-pre", dest="humanize_pre", default=None, help="Seconds range like 60-90 for pre-browse")
    parser.add_argument("--humanize-post", dest="humanize_post", default=None, help="Seconds range like 30-60 for post-browse")
    parser.add_argument("--initial-idle", dest="initial_idle", default=None, help="Seconds range to stay idle before any scroll, e.g. 2-5")
    
    # Risk behavior
    parser.add_argument("--risk-mode", dest="risk_mode", choices=["warn","stop"], default=None, help="warn: R1/R2 only warnings; stop: stop on R1/R2")
    parser.add_argument("--stop-on-r3-live", dest="stop_on_r3_live", choices=["0","1"], default=None, help="Whether to stop on R3 in live mode (default 1)")
    parser.add_argument("--risk-ceiling", dest="risk_ceiling", choices=["R1","R2","R3"], default=None, help="Upper bound risk to allow this run")
    parser.add_argument("--enforce-cooldown-on-r3", dest="enforce_cooldown_on_r3", choices=["0","1"], default=None, help="If last run detected R3, enforce a cooldown before proceeding")
    parser.add_argument("--cooldown-on-r3-s", dest="cooldown_on_r3_s", default=None, help="Cooldown seconds when last run was R3")
    
    # Optional timeout overrides
    parser.add_argument("--selector-timeout", dest="selector_timeout", default=None, help="Override selector timeout in ms")
    parser.add_argument("--goto-home-ms", dest="goto_home_ms", default=None, help="Override goto home timeout in ms")
    parser.add_argument("--goto-profile-ms", dest="goto_profile_ms", default=None, help="Override goto profile timeout in ms")
    
    # Typing and extraction tuning
    parser.add_argument("--per-char-ms", dest="per_char_ms", default=None, help="Typing delay range per char in ms, e.g. 400-900")
    parser.add_argument("--editor-para-selector", dest="editor_para_selector", default=None, help="CSS to extract paragraphs under editor, default p[class]")
    
    # Feature module toggles (1/0)
    parser.add_argument("--enable-scroll", dest="enable_scroll", default=None, help="Enable pre/post scroll: 1 or 0")
    parser.add_argument("--enable-composer", dest="enable_composer", default=None, help="Enable composer module: 1 or 0")
    parser.add_argument("--enable-typing", dest="enable_typing", default=None, help="Enable typing module: 1 or 0")
    
    # Navigation
    parser.add_argument("--repin-after-spa", dest="repin_after_spa", default=None, help="Force replaceState back to threads.net after SPA rewrites: 1 or 0")
    parser.add_argument("--suppress-media", dest="suppress_media", default=None, help="Pause/mute media tags in rehearsal: 1 or 0")
    
    # Scroll step caps (optional)
    parser.add_argument("--max-pre-steps", dest="max_pre_steps", default=None, help="Maximum wheel steps during pre-scroll (e.g. 60)")
    parser.add_argument("--max-post-steps", dest="max_post_steps", default=None, help="Maximum wheel steps during post-scroll (e.g. 40)")
    
    # A/B 診斷開關
    parser.add_argument("--skip-init-patches", dest="skip_init_patches", action="store_true", help="Disable init patches for diagnostics")
    parser.add_argument("--disable-net-guard", dest="disable_net_guard", action="store_true", help="Disable network interception guard (even in dress mode)")
    parser.add_argument("--disable-domain-pin", dest="disable_domain_pin", action="store_true", help="Do not rewrite threads.com → threads.net on navigation requests")
    parser.add_argument("--disable-header-sanitize", dest="disable_header_sanitize", action="store_true", help="Do not remove non-simple headers on subresources (diagnostics)")
    parser.add_argument("--min-interval-sec", dest="min_interval_sec", type=int, default=None)
    parser.add_argument("--hour-cap", dest="hour_cap", type=int, default=None)
    parser.add_argument("--day-cap", dest="day_cap", type=int, default=None)
    parser.add_argument("--output", dest="output", default=None, help="Write JSON result to file (single line)")


def build_runtime_overrides(args: argparse.Namespace) -> Dict[str, Any]:
    """Build runtime overrides dict from parsed args."""
    overrides = {}
    
    # Humanize
    if hasattr(args, 'pre_scroll') and args.pre_scroll:
        overrides["humanize_pre"] = args.pre_scroll
    elif args.humanize_pre:
        overrides["humanize_pre"] = args.humanize_pre
    if args.humanize_post:
        overrides["humanize_post"] = args.humanize_post
    if args.initial_idle:
        overrides["initial_idle"] = args.initial_idle
    
    # Risk
    if args.risk_mode:
        overrides["risk_mode"] = args.risk_mode
    if args.stop_on_r3_live is not None:
        overrides["stop_on_r3_live"] = args.stop_on_r3_live
    if args.risk_ceiling:
        overrides["risk_ceiling"] = args.risk_ceiling
    if args.enforce_cooldown_on_r3 is not None:
        overrides["enforce_cooldown_on_r3"] = args.enforce_cooldown_on_r3
    if args.cooldown_on_r3_s is not None:
        overrides["cooldown_on_r3_s"] = args.cooldown_on_r3_s
    
    # Timeouts
    if args.selector_timeout:
        overrides["selector_timeout"] = args.selector_timeout
    if args.goto_home_ms:
        overrides["goto_home_ms"] = args.goto_home_ms
    if args.goto_profile_ms:
        overrides["goto_profile_ms"] = args.goto_profile_ms
    
    # Typing
    if args.per_char_ms:
        overrides["per_char_ms"] = args.per_char_ms
    if args.editor_para_selector:
        overrides["editor_para_selector"] = args.editor_para_selector
    
    # Modules
    if args.enable_scroll is not None:
        overrides["enable_scroll"] = args.enable_scroll
    if args.enable_composer is not None:
        overrides["enable_composer"] = args.enable_composer
    if args.enable_typing is not None:
        overrides["enable_typing"] = args.enable_typing
    
    # Navigation
    if args.repin_after_spa is not None:
        overrides["repin_after_spa"] = args.repin_after_spa
    if args.suppress_media is not None:
        overrides["suppress_media"] = args.suppress_media
    
    # Scroll caps
    if args.max_pre_steps is not None:
        overrides["max_pre_steps"] = args.max_pre_steps
    if args.max_post_steps is not None:
        overrides["max_post_steps"] = args.max_post_steps
    
    return overrides


def resolve_content_file(
    text_file: Optional[str],
    content_file: Optional[str],
    default_file: Optional[str] = None
) -> str:
    """Resolve content file path with priority: text_file > content_file > default_file."""
    return text_file or content_file or default_file


def output_result(result: Dict[str, Any], output_path: Optional[str] = None) -> None:
    """Output JSON result to stdout and optionally to file."""
    line = json.dumps(result, ensure_ascii=False)
    print(line)
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(line + "\n")


def run_with_error_handling(main_func: Callable[[], Dict[str, Any]]) -> None:
    """Run main function with standardized error handling."""
    try:
        result = main_func()
        output_result(result)
    except Exception as e:
        error_result = {"ok": False, "code": 99, "message": str(e)}
        print(json.dumps(error_result, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)