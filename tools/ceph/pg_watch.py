#!/usr/bin/env python3
# 
# pg_watch.py — poll 'ceph pg ls -f json' and report changes to acting/up sets.
# Focuses on OSD movement: which OSD lost/gained data, and how much.
# 
# Usage:
#     python3 pg_watch.py [--interval SECONDS] [--osd OSD_ID] [--pool POOL_ID]
# 
# Options:
#     --interval  Poll interval in seconds (default: 10)
#     --osd       Only report changes involving a specific OSD id
#     --pool      Only report changes for a specific pool id (numeric)
#
# (C) 2026 j.weigert@heinlein-support.de

import subprocess
import json
import time
import argparse
from datetime import datetime


def ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def fmt_bytes(n):
    if n >= 1 << 30:
        return f"{n / (1 << 30):.1f}GiB"
    elif n >= 1 << 20:
        return f"{n / (1 << 20):.1f}MiB"
    elif n >= 1 << 10:
        return f"{n / (1 << 10):.1f}KiB"
    return f"{n}B"


def osd_set_diff(old_set, new_set):
    removed = [o for o in old_set if o not in new_set]
    added   = [o for o in new_set  if o not in old_set]
    return removed, added


def run_ceph_pg_ls():
    try:
        result = subprocess.run(
            ["ceph", "pg", "ls", "-f", "json"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            print(f"[{ts()}] ERROR: ceph pg ls failed: {result.stderr.strip()}")
            return None
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        print(f"[{ts()}] ERROR: ceph pg ls timed out")
        return None
    except json.JSONDecodeError as e:
        print(f"[{ts()}] ERROR: failed to parse JSON: {e}")
        return None


def extract_pg_map(data, filter_osd=None, filter_pool=None):
    pg_map = {}
    for pg in data.get("pg_stats", []):
        pgid   = pg.get("pgid", "")
        up     = pg.get("up", [])
        acting = pg.get("acting", [])
        state  = pg.get("state", "").strip("'")
        nbytes = pg.get("stat_sum", {}).get("num_bytes", 0)

        if filter_pool is not None:
            try:
                if int(pgid.split(".")[0]) != filter_pool:
                    continue
            except ValueError:
                continue

        if filter_osd is not None:
            if filter_osd not in up and filter_osd not in acting:
                continue

        pg_map[pgid] = {"up": up, "acting": acting, "state": state, "bytes": nbytes}
    return pg_map


def osd_list(ol):
    # 2147483647 is 0xFFFF aka -1 is a Dummy placeholder
    return " ".join(f"osd.{x}" if x < 2147483647 else "--" for x in ol)


def diff_pg_maps(old, new):
    changes = []
    for pgid in sorted(set(old.keys()) | set(new.keys())):

        if pgid not in old:
            n = new[pgid]
            changes.append(
                f"  NEW    {fmt_bytes(n['bytes']):>10s}  pg {pgid}"
                f"  acting={n['acting']}  up={n['up']}  state={n['state']}"
            )
            continue

        if pgid not in new:
            o = old[pgid]
            changes.append(
                f"  GONE   {fmt_bytes(o['bytes']):>10s}  pg {pgid}"
                f"  was acting={o['acting']}  up={o['up']}"
            )
            continue

        o, n = old[pgid], new[pgid]
        acting_changed = o["acting"] != n["acting"]
        up_changed     = o["up"]     != n["up"]
        state_changed  = o["state"]  != n["state"]
        if not (acting_changed or up_changed or state_changed):
            continue

        size = fmt_bytes(n["bytes"])
        removed, added = osd_set_diff(o["acting"], n["acting"])

        if removed and added:
            movement = f"{size:>10s}  {osd_list(removed)} -> {osd_list(added)}"
        elif removed:
            movement = f"{size:>10s}  removed from " + osd_list(removed)
        elif added:
            movement = f"{size:>10s}  added to " + osd_list(added)
        else:
            movement = f"{size:>10s}"

        extras = []
        if acting_changed:
            extras.append(f"acting -> {n['acting']}")
        if up_changed and n['up'] != n['acting']:
            extras.append(f"up -> {n['up']}")
        if state_changed:
            extras.append("state -> " + repr(n['state']).strip("'"))
        extra_str = "  " + "  ".join(extras) if extras else ""
        changes.append(f"  {movement}  pg {pgid}{extra_str}")

    return changes


def main():
    parser = argparse.ArgumentParser(description="Watch ceph PG mapping changes")
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--osd",  type=int, default=None)
    parser.add_argument("--pool", type=int, default=None)
    args = parser.parse_args()

    filter_info = []
    if args.osd  is not None: filter_info.append(f"osd.{args.osd}")
    if args.pool is not None: filter_info.append(f"pool {args.pool}")
    filter_str = f" [filter: {', '.join(filter_info)}]" if filter_info else ""

    print(f"[{ts()}] pg_watch starting — interval={args.interval}s{filter_str}")
    print(f"[{ts()}] polling initial state...")

    old_map = {}
    first = True

    while True:
        data = run_ceph_pg_ls()
        if data is not None:
            new_map = extract_pg_map(data, filter_osd=args.osd, filter_pool=args.pool)
            if first:
                print(f"[{ts()}] tracking {len(new_map)} PGs")
                first = False
            else:
                changes = diff_pg_maps(old_map, new_map)
                if changes:
                    for line in changes:
                        print(f"[{ts()}]{line}")
            old_map = new_map

        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n[{ts()}] stopped.")
