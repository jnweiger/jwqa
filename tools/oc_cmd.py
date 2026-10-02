#!/usr/bin/env python3
"""
oc_cmd.py – OpenCloud CLI wrapper using rclone and the Graph API.

Usage examples:
  oc_cmd.py ls
  oc_cmd.py ls oc:
  oc_cmd.py ls https://username@oc.jwqa.de
  oc_cmd.py ls -r          # recursive (max-depth 0 -> no limit)
  oc_cmd.py ls -l          # long format with size and alias
  oc_cmd.py ls -rl         # recursive + long
  oc_cmd.py copy oc:/project/support_team/doc/subfolder .
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def check_env_vars():
    required = ["OC_URL", "OC_APPTOKEN"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        eprint(f"Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)
    # OC_USER is optional if provided via URL username
    return os.environ.get("OC_USER")


def check_rclone():
    if not shutil.which("rclone"):
        eprint("rclone binary not found in PATH")
        sys.exit(1)


def parse_url_username(url: str) -> str | None:
    """
    Extract username from a URL like https://username@host/...
    Returns None if no username is present.
    """
    if "://" not in url:
        return None
    _, rest = url.split("://", 1)
    if "@" not in rest:
        return None
    user_host, _ = rest.split("@", 1)
    return user_host.split(":", 1)[0] or None

ef parse_url_username(url: str) -> str | None:
     """ 
     Extract username from a URL like https://username@host/...
     Returns None if no username is present.
     """     
     if "://" not in url:
         return None
     proto, rest = url.split("://", 1)
     if "@" not in rest:
         return None
     user_host, rem = rest.split("@", 1)
     return user_host.split(":", 1)[0] or None, proto + '://' + rem


def get_spaces(oc_url: str, oc_user: str, oc_apptoken: str) -> list[dict[str, Any]]:
    """
    Call Graph API and return list of drives (spaces).
    """
    url = f"{oc_url.rstrip('/')}/graph/v1.0/me/drives"
    auth = f"{oc_user}:{oc_apptoken}"
    auth_b64 = base64.b64encode(auth.encode("utf-8")).decode("ascii")

    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Basic {auth_b64}")
    req.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        eprint(f"HTTP error calling Graph API: {e.code} {e.reason}")
        try:
            body = e.read().decode("utf-8", errors="replace")
            eprint("Response:", body)
        except Exception:
            pass
        sys.exit(1)
    except Exception as e:
        eprint(f"Error calling Graph API: {e}")
        sys.exit(1)

    return data.get("value", [])


def print_spaces(spaces: list[dict[str, Any]], long_format: bool):
    """
    Print spaces in tabular form.

    Default columns:
      driveAlias  name  webDavUrl

    With -l / --long:
      driveAlias  name  webDavUrl  size  remoteItem.driveAlias (as symlink target)
    """
    if long_format:
        header = [
            "driveAlias",
            "name",
            "webDavUrl",
            "size",
            "remoteItem.driveAlias",
        ]
    else:
        header = [
            "driveAlias",
            "name",
            "webDavUrl",
        ]

    col_widths = [len(h) for h in header]

    rows = []
    for item in spaces:
        drive_alias = item.get("driveAlias", "")
        name = item.get("name", "")
        webdav_url = item.get("root", {}).get("webDavUrl", "")

        # size: quota.used or root.remoteItem.size or null
        size = None
        quota = item.get("quota")
        if quota is not None and "used" in quota:
            size = quota["used"]
        else:
            remote_item = item.get("root", {}).get("remoteItem")
            if remote_item is not None and "size" in remote_item:
                size = remote_item["size"]

        remote_item = item.get("root", {}).get("remoteItem") or {}
        ri_drive_alias = remote_item.get("driveAlias", "")

        if long_format:
            row = [
                drive_alias,
                name,
                webdav_url,
                str(size) if size is not None else "null",
                ri_drive_alias,
            ]
        else:
            row = [
                drive_alias,
                name,
                webdav_url,
            ]

        rows.append(row)
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(val))

    # Print header
    header_line = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(header))
    eprint(header_line)
    eprint("-" * len(header_line))

    # Print rows
    for row in rows:
        line = "  ".join(val.ljust(col_widths[i]) for i, val in enumerate(row))
        print(line)


def resolve_space_for_path(
    path: str, spaces: list[dict[str, Any]]
) -> tuple[dict[str, Any], str]:
    """
    Given a path like 'oc:/project/support_team/doc/subfolder',
    resolve the space by matching /project/support_team against
    driveAlias or name.

    Returns (space_dict, remaining_path_in_space)
    where remaining_path_in_space is e.g. '/doc/subfolder'.
    """
    if not path.startswith("oc:/"):
        eprint("Path must start with 'oc:/'")
        sys.exit(1)

    rest = path[4:]  # remove 'oc:/'
    if not rest:
        eprint("No path provided after 'oc:/'")
        sys.exit(1)

    parts = rest.split("/")
    space = None
    matched_prefix = ""
    inner_path = ""

    for i in range(1, len(parts) + 1):
        candidate = "/" + "/".join(parts[:i])
        for sp in spaces:
            da = sp.get("driveAlias", "")
            nm = sp.get("name", "")
            if da == candidate.lstrip("/") or nm == candidate.lstrip("/"):
                space = sp
                matched_prefix = candidate
                inner_path = "/" + "/".join(parts[i:]) if i < len(parts) else "/"
                break
        if space:
            break

    if not space:
        eprint(f"Could not resolve space for path prefix in: {path}")
        eprint("Available spaces (driveAlias / name):")
        for sp in spaces:
            eprint(f"  {sp.get('driveAlias', '')} / {sp.get('name', '')}")
        sys.exit(1)

    if not inner_path.startswith("/"):
        inner_path = "/" + inner_path
    if inner_path == "/":
        inner_path = ""

    return space, inner_path


def rclone_copy(webdav_url: str, user: str, apptoken: str, src_path: str, dst: str):
    """
    Run:
    rclone copy -P --stats-one-line --config /dev/null --max-depth 0 \\
      --webdav-url WEBDAV_URL \\
      --webdav-vendor opencloud \\
      --webdav-user USER \\
      --webdav-pass "$(rclone obscure TOKEN)" \\
      :webdav:SRC_PATH DST
    """
    try:
        obsc = subprocess.run(
            ["rclone", "obscure", apptoken],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        eprint("rclone obscure failed:", e.stderr.strip() or e)
        sys.exit(1)

    obscured_pass = obsc.stdout.strip()

    cmd = [
        "rclone",
        "copy",
        "-P",
        "--stats-one-line",
        "--config",
        "/dev/null",
        "--max-depth",
        "0",
        "--webdav-url",
        webdav_url,
        "--webdav-vendor",
        "opencloud",
        "--webdav-user",
        user,
        "--webdav-pass",
        obscured_pass,
        f":webdav:{src_path}",
        dst,
    ]

    try:
        ret = subprocess.run(cmd)
        sys.exit(ret.returncode)
    except FileNotFoundError:
        eprint("rclone binary not found (should have been checked earlier)")
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oc_cmd",
        description="OpenCloud CLI wrapper using rclone and the Graph API.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ls subcommand
    ls_parser = subparsers.add_parser("ls", help="List spaces")
    ls_parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="Optional target: 'oc:' or a URL like https://username@oc.jwqa.de",
    )
    ls_parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help=(
            "Recursive listing. For spaces, this currently has no extra effect "
            "since we always list all spaces; reserved for future per-space recursion."
        ),
    )
    ls_parser.add_argument(
        "-l",
        "--long",
        action="store_true",
        help="Long format: include size and symlink-style alias (remoteItem.driveAlias).",
    )

    # copy subcommand
    copy_parser = subparsers.add_parser("copy", help="Copy from OpenCloud to local")
    copy_parser.add_argument(
        "src",
        help="Source path, e.g. oc:/project/support_team/doc/subfolder",
    )
    copy_parser.add_argument(
        "dst",
        help="Destination path",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    check_rclone()

    oc_url = os.environ.get("OC_URL")
    oc_apptoken = os.environ.get("OC_APPTOKEN")
    oc_user_env = os.environ.get("OC_USER")

    # if not oc_url:
    #     eprint("Environment variable OC_URL is missing")
    #     sys.exit(1)
    # if not oc_apptoken:
    #     eprint("Environment variable OC_APPTOKEN is missing")
    #     sys.exit(1)

    if args.command == "ls":
        target = args.target

        # Determine effective URL and username
        if target is None:
            # oc_cmd.py ls [-r] [-l]
            oc_user = oc_user_env
            effective_url = oc_url
            if not oc_user:
                eprint("Environment variable OC_USER is missing (no username in URL)")
                sys.exit(1)
        elif target == "oc:":
            # oc_cmd.py ls oc: [-r] [-l]
            oc_user = oc_user_env
            effective_url = oc_url
            if not oc_url:
                eprint("Environment variable OC_URL is missing. Alternatively, specify the full server url instead of 'oc:'")
                sys.exit(1)
            if not oc_user:
                eprint("Environment variable OC_USER is missing (no username in URL)")
                sys.exit(1)
        else:
            # oc_cmd.py ls https://username@oc.jwqa.de [-r] [-l]
            effective_url = target
            url_user, new_target = parse_url_username(target)
            if url_user:
                oc_user = url_user
                target = new_target
            else:
                oc_user = oc_user_env
            if not oc_user:
                eprint( "No username found in URL and OC_USER is not set in environment")
                sys.exit(1)

        spaces = get_spaces(effective_url, oc_user, oc_apptoken)
        print_spaces(spaces, long_format=args.long)

    elif args.command == "copy":
        src_path = args.src
        dst = args.dst

        if not src_path.startswith("oc:/"):
            eprint("Source path must start with 'oc:/'")
            sys.exit(1)

        oc_user = oc_user_env
        if not oc_user:
            eprint("Environment variable OC_USER is missing")
            sys.exit(1)

        spaces = get_spaces(oc_url, oc_user, oc_apptoken)
        space, inner_path = resolve_space_for_path(src_path, spaces)

        webdav_url = space.get("root", {}).get("webDavUrl")
        if not webdav_url:
            eprint("Selected space has no root.webDavUrl")
            sys.exit(1)

        webdav_url = webdav_url.rstrip("/")
        rclone_copy(webdav_url, oc_user, oc_apptoken, inner_path, dst)

    else:
        eprint(f"Unknown command: {args.command}")
        sys.exit(1)


if __name__ == "__main__":
    main()


