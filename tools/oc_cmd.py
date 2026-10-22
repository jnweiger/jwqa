#!/usr/bin/env python3
"""
oc_cmd.py – OpenCloud CLI wrapper using rclone and the Graph API.

Usage examples:
  oc_cmd.py ls
  oc_cmd.py ls oc:
  oc_cmd.py ls https://username@oc.jwqa.de
  oc_cmd.py ls -r          # recursive (max-depth 0 -> no limit)
  oc_cmd.py ls -l          # long format with size and alias
  oc_cmd.py ls -i          # with uuid.
  oc_cmd.py ls -rl         # recursive + long
  oc_cmd.py copy oc:/project/support_team/doc/subfolder .

(C) 2026, j.weigert@heinlein-support.de - Distribute under GPLv2 or later.

2026-10-06, jw:  v1.0:    ls and cp commands done.
2026-10-21, jw:  v1.1:    Added -i option to ls. Improved error handling and usage printing.
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
from pathlib import Path

version="1.0"

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def check_rclone():
    if not shutil.which("rclone"):
        eprint("rclone binary not found in PATH")
        sys.exit(1)


def parse_url_username(url: str) -> str | None:
     """
     Extract username from a URL like https://username@host/...
     Returns None if no username is present. Returns the remaining url without username as second value.
     """
     if url is None:
         return None, None
     if "://" not in url:
         return None, url
     proto, rest = url.split("://", 1)
     if "@" not in rest:
         return None, url
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
        eprint(f"Error calling Graph API: {url=} {e}")
        sys.exit(1)

    return data.get("value", [])


def print_spaces(spaces: list[dict[str, Any]], prefix: str = "", long_format: bool = False, with_id: bool = False, json_format: bool = False):
    """
    Print spaces in tabular form.

    Default columns:
      driveAlias  name  webDavUrl

    With -l / --long:
      driveAlias  name  webDavUrl  size  remoteItem.driveAlias (as symlink target)
    """
    if json_format:
        print(json.dumps(spaces, sort_keys=True, indent=4))
        return

    header = [
        "driveAlias",
        "name",
    ]
    if long_format:
        header.extend([
            "size",
            "remoteItem.driveAlias",
        ])
    if with_id:
        header.append("id")

    col_widths = [len(h) for h in header]

    rows = []
    for item in spaces:
        drive_alias = item.get("driveAlias", "")
        name = item.get("name", "")
        webdav_url = item.get("root", {}).get("webDavUrl", "")

        # size: quota.used or root.remoteItem.size or null
        size = None
        quota = item.get("quota")
        uuid = item.get("id")
        if quota is not None and "used" in quota:
            size = quota["used"]
        else:
            remote_item = item.get("root", {}).get("remoteItem")
            if remote_item is not None and "size" in remote_item:
                size = remote_item["size"]

        remote_item = item.get("root", {}).get("remoteItem") or {}
        ri_drive_alias = remote_item.get("driveAlias", "")

        row = [
            prefix+drive_alias,
            name,
        ]
        if long_format:
            row.extend([
                str(size) if size is not None else "-",
                ri_drive_alias,
            ])
        if with_id:
            row.append(uuid)

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
    spaces: list[dict[str, Any]], path: str
) -> tuple[dict[str, Any], str]:
    """
    Given a path like 'oc:/project/support_team/doc/subfolder',
    resolve the space by matching /project/support_team against
    driveAlias or name.

    Returns (space_dict, remaining_path_in_space)
    where remaining_path_in_space is e.g. '/doc/subfolder'.
    """
    if not path.startswith("oc:"):
        eprint("Path must start with 'oc:'")
        sys.exit(1)
    if path.startswith("oc:/"):
      rest = path[4:]  # remove 'oc:/'
    else:
      rest = path[3:]  # remove 'oc:'

    if not rest:
        eprint("No path provided after 'oc:[/]'")
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


def rclone_obscure(apptoken):
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
    return obsc.stdout.strip()


def rclone_list(webdav_url: str, user: str, apptoken: str, webdav_path: str, flags=None):
    """
    Run:
    rclone ls --max-depth 1 --config /dev/null --webdav-url WEBDAV_URL \\
      --webdav-vendor opencloud \\
      --webdav-user USER --webdav-pass "$(rclone obscure TOKEN)" \\
      :webdav:path

    where WEBDAV_URL is the webdavurl from a space dict.
    """
    webdav_vendor = os.environ.get("OC_WEBDAV_VENDOR", "opencloud")
    obscured_pass = rclone_obscure(apptoken)
    cmd = [ "rclone", "lsjson", "--config", "/dev/null", "--max-depth", "0" if flags and flags.recursive else "1",
        "--webdav-url", webdav_url, "--webdav-vendor", webdav_vendor, "--webdav-user", user,
        "--webdav-pass", obscured_pass, f":webdav:{webdav_path}" ]
    try:
        ls = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        eprint("rclone ls failed:", e.stderr.strip() or e)
        sys.exit(1)
    try:
        text = json.loads(ls.stdout)
    except subprocess.CalledProcessError as e:
        eprint("parsing json failed: from: rclone lsjson:", e.stderr.strip() or e)
        sys.exit(1)

    if flags and flags.json:
        print(json.dumps(text, sort_keys=True, indent=4))
    else:
        for item in sorted(text, key=lambda x: x['Path']):
            # {'Path': 'test.txt', 'Name': 'test.txt', 'Size': 140, 'MimeType': 'text/plain; charset=utf-8', 'ModTime': '2026-08-03T15:56:47Z', 'IsDir': False}
            if flags and flags.long:
              print(f"{item["ModTime"]} {item["Size"]:10} {"D" if item["IsDir"] else " "} {item["Path"]}{"/" if item["IsDir"] else ""}")
            else:
              print(f"{item["Path"]}{"/" if item["IsDir"] else ""}")


def rclone_copy(webdav_url: str, user: str, apptoken: str, src: str, dst: str, recursive: bool = False, overwrite: bool = False):
    """
    Runs:
    rclone copy[to] -P --stats-one-line --config /dev/null --max-depth 0 \\
      --webdav-url WEBDAV_URL \\
      --webdav-vendor opencloud \\
      --webdav-user USER \\
      --webdav-pass "$(rclone obscure TOKEN)" \\
      :webdav:SRC_PATH DST

    We use either copy or copyto, so that we can name a destination file explicitly.
    """
    if not src.startswith(":webdav:") and not dst.startswith(":webdav:"):
      eprint("rclone_copy: one of src or dst must start with :webdav:")
      sys.exit(1)

    webdav_vendor = os.environ.get("OC_WEBDAV_VENDOR", "opencloud")
    obscured_pass = rclone_obscure(apptoken)

    cmd = [ "rclone", "copy", "--create-empty-src-dirs" ]
    if overwrite:   # and Path(src).is_file():
       cmd = [ "rclone", "copyto" ]

    cmd += [
        "-P", "--stats-one-line", "--config", "/dev/null",
        "--max-depth", "-1" if recursive else "1",
        "--webdav-url", webdav_url, "--webdav-vendor", webdav_vendor,
        "--webdav-user", user, "--webdav-pass", obscured_pass,
        src, dst
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
        description=f"oc_cmd version {version} - OpenCloud CLI wrapper using rclone and the Graph API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Environment variables:
  OC_URL            Url of the server, examples: https://oc.example.com  https://username@oc.example.com  https://localhost:9200
  OC_USER           Username to aithenticate at the server. Superceedes a username in OC_URL, if any.
  OC_APPTOKEN       As created at your personal settings page in the opencloud website
  OC_WEBDAV_VENDOR  Default: opencloud

For more detailled usage, try --help with a command, e.g.:
  oc_cmd ls --help
  oc_cmd cp --help
"""
    )
    subparsers = parser.add_subparsers(dest="command")  # required=True
    # ls subcommand
    ls_parser = subparsers.add_parser("ls", help="List spaces or their contents", epilog=parser.epilog)
    ls_parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="Optional target: 'oc:[spacename[/path...]]' or a URL like https://username@oc.example.com:9200",
    )
    ls_parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help=(
            "Recursive listing. For toplevel spaces listing, this has no effect, as spaces are flat."
        ),
    )
    ls_parser.add_argument(
        "-l",
        "--long",
        action="store_true",
        help="Long format: include size and symlink-style alias (remoteItem.driveAlias).",
    )
    ls_parser.add_argument(
        "-i",
        "--id",
        "--uuid",
        action="store_true",
        help="With UUID: include space id. Only effective for a toplevel spaces listing.)",
    )
    ls_parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Output in rclone lsjson format. This includes all available elements (-l, -i ave no effect with -j).",
    )

    # copy subcommand
    copy_parser = subparsers.add_parser("copy", aliases=["cp"], help="Copy from or to OpenCloud", epilog=parser.epilog)
    copy_parser.add_argument(
        "src",
        help="Source path, e.g. oc:/project/support_team/doc/subfolder",
    )
    copy_parser.add_argument(
        "dst",
        help="Destination path",
    )
    copy_parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recursive tree copy. No effect when source is a file."
    )
    copy_parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite a file destiniation using 'rclone copyto'. Use this, if rclone refuses to copy a file to an existing destination file."
    )
    return parser


def oc_get(oc_url, user, apptoken, spaces, src, dst, recursive=False, overwrite=False):

    space, inner_path = resolve_space_for_path(spaces, src)

    webdav_url = space.get("root", {}).get("webDavUrl")
    if not webdav_url:
        eprint(f"Selected space '{space["name"]}' has no root.webDavUrl")
        sys.exit(1)

    webdav_url = webdav_url.rstrip("/")
    rclone_copy(webdav_url, user, apptoken, ":webdav:"+inner_path, dst, recursive=recursive, overwrite=overwrite)


def oc_put(oc_url, user, apptoken, spaces, src, dst, recursive=False, overwrite=False):

    space, inner_path = resolve_space_for_path(spaces, dst)

    webdav_url = space.get("root", {}).get("webDavUrl")
    if not webdav_url:
        eprint(f"Selected space '{space["name"]}' has no root.webDavUrl")
        sys.exit(1)

    webdav_url = webdav_url.rstrip("/")
    rclone_copy(webdav_url, user, apptoken, src, ":webdav:"+inner_path, recursive=recursive, overwrite=overwrite)


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        eprint("\nUsage error: No command given.")
        sys.exit(1)


    check_rclone()

    oc_user_env, oc_url = parse_url_username(os.environ.get("OC_URL"))
    oc_user_env = os.environ.get("OC_USER", oc_user_env)    # explicit OC_USER env var takes precendce over embedded user in OC_URL
    oc_apptoken = os.environ.get("OC_APPTOKEN")
    if not oc_apptoken:
        eprint(f"Environment variable OC_APPTOKEN is missing. Create an apptoken if needed at your personal settings in the opencloud website {os.environ.get("OC_URL", "")}")
        sys.exit(1)

    if args.command == "ls":
        target = args.target

        # Determine effective URL and username
        url_path=""
        if target is None or target.startswith("oc:"):
            # oc_cmd.py ls oc: [-r] [-l]
            if target and target[:3] == "oc:":
              url_path = target
            oc_user = oc_user_env
            target = oc_url
            if not oc_url:
                eprint("Environment variable OC_URL is missing. Alternatively, specify the full server url")
                sys.exit(1)
            if not oc_user:
                eprint("Environment variable OC_USER is missing (and no username in OC_URL)")
                sys.exit(1)
        else:
            # oc_cmd.py ls https://username@oc.jwqa.de [-r] [-l]
            url_user, new_target = parse_url_username(target)
            if url_user:
                oc_user = os.environ.get("OC_USER", url_user)    # explicit OC_USER env var takes precendce over embedded user in OC_URL
                target = new_target
            else:
                oc_user = os.environ.get("OC_USER")
            if not oc_user:
                eprint( "No username found in URL and OC_USER is not set in environment")
                sys.exit(1)

        spaces = get_spaces(target, oc_user, oc_apptoken)
        if url_path in ("", "oc:", "oc:/"):
          print_spaces(spaces, prefix="oc:", long_format=args.long, with_id=args.id, json_format=args.json)
        else:
          # print(f"{url_path}")
          space, path = resolve_space_for_path(spaces, url_path)
          # print(f"space {space}, path {path}")
          rclone_list(space["root"]["webDavUrl"], oc_user, oc_apptoken, path, args)

    elif args.command in ("cp", "copy"):
        if not oc_user_env:
            eprint("Environment variable OC_USER is missing")
            sys.exit(1)
        if not oc_url:
            eprint("Environment variable OC_URL is missing")
            sys.exit(1)
        spaces = get_spaces(oc_url, oc_user_env, oc_apptoken)

        if args.src.startswith("oc:"):
            oc_get(oc_url, oc_user_env, oc_apptoken, spaces, args.src, args.dst, args.recursive, args.force)
        elif args.dst.startswith("oc:"):
            oc_put(oc_url, oc_user_env, oc_apptoken, spaces, args.src, args.dst, args.recursive, args.force)
        else:
            eprint(f"copy: One of src or dest must start with 'oc:'")
            sys.exit(1)

    else:
        eprint(f"Unknown command: {args.command}")
        sys.exit(1)


if __name__ == "__main__":
    main()


