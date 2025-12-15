#!/usr/bin/env python3
import os
from .workflows import read_content
from .service import run_reply_flow
from .cli_shared import (
    add_common_args,
    build_runtime_overrides,
    resolve_content_file,
    run_with_error_handling
)
import argparse


def main():
    parser = argparse.ArgumentParser(description="Reply to a specific Threads post (permalink) using Playwright + storage_state")
    
    # Add common arguments
    add_common_args(parser)
    
    # Add reply-specific arguments
    parser.add_argument("--permalink", dest="permalink", required=True, help="Target thread permalink (https://www.threads.net/...) to reply to")
    parser.add_argument("--sel-reply", dest="sel_reply", help="Override reply button selector", default=None)
    parser.add_argument("--sel-submit", dest="sel_submit", help="Override reply submit selector (comma-separated to provide multiple)", default=None)
    # Pre-scroll alias (homepage pre-feed). Alias of --humanize-pre
    parser.add_argument(
        "--pre-scroll",
        dest="pre_scroll",
        default=None,
        help="Alias of --humanize-pre: seconds range like 60-90 for homepage pre-scroll",
    )
    
    args = parser.parse_args()

    # Resolve content file with reply default
    default_reply_path = os.path.join(os.path.dirname(__file__), "config", "reply_post_content.txt")
    content_file = resolve_content_file(args.text_file, args.content_file, default_reply_path)
    content = read_content(content_file)

    # Build runtime overrides
    overrides = build_runtime_overrides(args)
    # Reply-specific overrides for loader
    overrides["reply_permalink"] = args.permalink
    if content_file: 
        overrides["reply_text_file"] = content_file
    # Reply selector overrides
    if args.sel_reply: 
        overrides["reply_selector_reply_icon_svg"] = args.sel_reply
    if args.sel_editor: 
        overrides["reply_selector_editor_input"] = args.sel_editor
    if args.sel_submit: 
        overrides["reply_selector_publish_candidates"] = args.sel_submit

    # Execute run_reply_flow
    def execute():
        return run_reply_flow(
            permalink=args.permalink,
            content=content,
            headless=args.headless,
            timeout_ms=args.timeout,
            dry_run=args.dry_run,
            retries=args.retries,
            verbose=args.verbose,
            account_id=args.account_id,
            selectors_path=args.selectors_file,
            run_mode=args.run_mode,
            ignore_risk_for_check=args.ignore_risk_for_check,
            rate_mode=args.rate_mode,
            min_interval_sec=args.min_interval_sec,
            hour_cap=args.hour_cap,
            day_cap=args.day_cap,
            skip_init_patches=args.skip_init_patches,
            disable_net_guard=args.disable_net_guard,
            disable_domain_pin=args.disable_domain_pin,
            disable_header_sanitize=args.disable_header_sanitize,
            humanize_session=args.humanize_session,
            runtime_overrides=overrides,
            sel_reply=args.sel_reply,
            sel_editor=args.sel_editor,
            sel_submit=args.sel_submit,
        )
    
    from .cli_shared import output_result
    result = execute()
    output_result(result, args.output)


if __name__ == "__main__":
    run_with_error_handling(main)
