#!/usr/bin/env python3
from .workflows import read_content
from .service import post_new
from .cli_shared import (
    add_common_args,
    build_runtime_overrides,
    resolve_content_file,
    run_with_error_handling
)
import argparse


def main():
    parser = argparse.ArgumentParser(description="Post a new Threads message using Playwright + storage_state")
    
    # Add common arguments
    add_common_args(parser)
    
    # Add new-post specific arguments
    parser.add_argument("--sel-create", dest="sel_create", help="Override compose button selector", default=None)
    parser.add_argument("--sel-publish", dest="sel_publish", help="Override publish button selector", default=None)
    parser.add_argument("--profile-url", dest="profile_url", default=None, help="Optional: navigate to this profile URL first (will normalize to threads.net)")
    parser.add_argument("--profile-handle", dest="profile_handle", default=None, help="Optional: e.g. @alice or alice; builds https://www.threads.net/@alice if set")
    
    args = parser.parse_args()

    # Resolve content file
    content_file = resolve_content_file(args.text_file, args.content_file)
    content = read_content(content_file)

    # Build runtime overrides
    overrides = build_runtime_overrides(args)

    # Execute post_new
    def execute():
        return post_new(
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
            profile_url=args.profile_url,
            profile_handle=args.profile_handle,
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
            sel_create=args.sel_create,
            sel_editor=args.sel_editor,
            sel_publish=args.sel_publish,
        )
    
    from .cli_shared import output_result
    result = execute()
    output_result(result, args.output)


if __name__ == "__main__":
    run_with_error_handling(main)
