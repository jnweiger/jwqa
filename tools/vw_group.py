#! /usr/bin/python3
#
# vw_group.py - list, and edit user groups and their permissions.
#
# This uses a mixture of client api and sql access.
# - the client api misses info about user groups
# - the sql database stores all names (except groups) encrypted.
#
# 2026 (C) j.weigert@heinlein-support.de
#
# Trailing * globbing is supported with user names, emails, uuids and collection names.
# - vw_group.py GROUP add user 'testy*'      # Already added is silently ignored.
# - vw_group.py GROUP del user 'testy*'      # Already not member is silently ignored.
#
# CAUTION, the sqlite db seems to be not locked, when vautwarden runs. We just apply changes to the db
#   without any preparation. It is unclear, if this is really safe while the server runs. It seems so.

import sys, os, json, subprocess, shlex
import argparse, uuid


server_ssh     = os.environ.get("VW_SERVER_SSH")    # username@host
sqlite_db_path = os.environ.get("VW_DB_PATH", "vaultwarden/data/db.sqlite3")
sqlite_cmd     = [ "ssh", server_ssh, "sqlite3", "-json", sqlite_db_path ]
bw_cli         = os.environ.get("VW_BW_TOOL", "bw")

verbose = 1     # 0, 1, 2 babble more ore less while working.

#!/usr/bin/env python3
import argparse


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="vw_group",
        description="Manage VaultWarden groups, their members and collection permissions."
    )
    parser.add_argument( "-j", "--json", action="store_true", help="Emit machine-readable JSON output.")
    parser.add_argument( "-l", "--list", action="store_true", help="List all groups")
    parser.add_argument( "-c", "--create", action="store_true", help="create group if missing")
    parser.add_argument( "-p", "--permission", metavar="PERM", help="permissions, when adding collections to a group: rw, ro,pw, ro,nopw, mgr")
    parser.add_argument("group", metavar="GROUP", nargs="?", help="Group name or group uuid to list or manipulate its users or collections")
    parser.add_argument("kind", metavar="user|col", nargs="?", choices=("u", "user", "users", "c", "col", "coll", "collection", "collections", "l", "list"), help="either 'users' or 'collections'.")
    parser.add_argument("cmd", metavar="add|del", nargs="?", choices=("list", "add", "del"), help="Add or delete users/collections.")
    parser.add_argument("names", metavar="NAMES", nargs="*", help="one or more names (or emails or uuids).")

    args = parser.parse_args(argv)

    ## some business logic
    # if not args.groups: args.list=True
    if args.kind in (None, "l", "list"):
      args.kind="all"
      args.list=True
    if args.cmd in (None, "l", "list"):
      args.list=True

    if args.permission and (args.cmd != "add" or args.kind not in ("c", "col", "coll", "collection")):
      print(f"ERROR: permissions specified: {args.permission} - that only works with: <group> collecion add ...", file=sys.stderr)
      sys.exit(1)

    return args


def parse_permission(p):
  a = p.split(',')
  r = { 'manage': 0 }
  if "mgr"  in a:
    r['manage'] = 1
    r['read_only'] = 0
    r['hide_passwords'] = 0
  if "rw"   in a:
    r['read_only'] = 0
    r['hide_passwords'] = 0
  if "ro"   in a: r['read_only'] = 1
  if "pw"   in a: r['hide_passwords'] = 0
  if "nopw" in a: r['hide_passwords'] = 1
  if len(r) != 3:
    print(f"ERROR: permission '{p}': use one of: 'rw', 'ro,pw', 'ro,nopw', 'mgr'", file=sys.stderr)
    sys.exit(1)

  return (r['read_only'], r['hide_passwords'], r['manage'])


def vw_sql(query):
    if not server_ssh:
        print(f"{sys.argv[0]}: ERROR: env variable VW_SERVER_SSH is not defined", file=sys.stderr)
        sys.exit(1)
    # FIXME: we guard against shell, but we are probably prone to SQL injection.
    proc = subprocess.run( sqlite_cmd + [shlex.quote(query)], check=True, stdout=subprocess.PIPE, universal_newlines=True)
    return json.loads(proc.stdout or "[]")


def vw_cli(cmd):
    vw_session = os.environ.get("VW_SESSION")
    if not vw_session:
        print(f"{sys.argv[0]}: ERROR: env variable VW_SESSION is not defined", file=sys.stderr)
        sys.exit(1)

    vw_cli_home = os.environ.get("VW_CLI_HOME")
    if not vw_cli_home:
        print(f"{sys.argv[0]}: ERROR: env variable VW_CLI_HOME is not defined", file=sys.stderr)
        sys.exit(1)

    env = os.environ.copy()
    env["HOME"] = vw_cli_home
    cli_cmd = [bw_cli, f"--session={vw_session}"] + list(cmd)

    proc = subprocess.run(cli_cmd, env=env, check=True, stdout=subprocess.PIPE, universal_newlines=True)
    return json.loads(proc.stdout)


def is_uuid(text):
  try:
    return str(uuid.UUID(text)) == text.lower()
  except ValueError:
    return False


def group_uuid(name_or_id):
  if is_uuid(name_or_id):
    return name_or_id
  group = vw_sql(f"SELECT uuid FROM groups WHERE name == '{name_or_id}'")
  if not len(group):
    return None
  return group[0]["uuid"]


def cmd_list_groups(args):
    group_list = vw_sql("SELECT uuid, organizations_uuid, name, access_all FROM groups")
    if args.json:
      print(json.dumps(group_list))
    else:
      for g in group_list:
        print(f"{g['uuid']}\t{shlex.quote(g['name'])}")
    return


def cmd_list_collections(args, guuid):
      print(f"Collections:")
      collection_uuid_list = vw_sql(f"SELECT collections_uuid, read_only, hide_passwords, manage FROM collections_groups WHERE groups_uuid == '{guuid}'")
      collection_name_list = vw_cli(["list", "collections"])
      collection_uuid2name = { item['id']: item['name'] for item in collection_name_list }
      if args.json:
        for c in collection_uuid_list:
          c['name'] = collection_uuid2name[c['collections_uuid']] 
        print(json.dumps(collection_uuid_list))
      else:
        for c in collection_uuid_list:
          cu = c['collections_uuid']
          print(f"\t{cu} ro={c['read_only']} pw={1-c['hide_passwords']} mgr={c['manage']} '{collection_uuid2name.get(cu, '-?-')}'")


def cmd_list_users(args, guuid):
      print(f"Users:")
      orguser_list  = vw_sql(f"SELECT users_organizations_uuid FROM groups_users WHERE groups_uuid == '{guuid}'")
      ou_in_list = "', '".join([x["users_organizations_uuid"] for x in orguser_list])
      uu_list = vw_sql(f"SELECT user_uuid FROM users_organizations WHERE uuid IN ('{ou_in_list}')")
      uu_in_list = "', '".join([x["user_uuid"] for x in uu_list])
      user_list = vw_sql(f"SELECT uuid, name, email FROM users WHERE uuid IN ('{uu_in_list}')")
      if args.json:
        print(json.dumps(user_list))
      else:
        for u in user_list:
          print(f"\t{u['uuid']} {u['name']} <{u['email']}>")


def user_lookup_all(names):
  user_list = vw_sql(f"SELECT uuid, name, email FROM users")
  r = []
  for name in names:
    uu = user_lookup(user_list, name)
    if not len(uu):
      return None, f"user not found: {name}"
    r.extend(uu)
  return r, None


def user_lookup(user_list, name):
  r = []
  for u in user_list:
    if name[-1] == '*':     # ends in *, do globbing
      if   u['uuid' ].startswith(name[:-1]): r.append(u['uuid'])
      elif u['email'].startswith(name[:-1]): r.append(u['uuid'])
      elif u['name' ].startswith(name[:-1]): r.append(u['uuid'])
    else:
      if   u['uuid' ] == name: r.append(u['uuid'])
      elif u['email'] == name: r.append(u['uuid'])
      elif u['name' ] == name: r.append(u['uuid'])
  return r


def map_user_uuid2orguuid(uu_list):
  orguser_list = vw_sql("SELECT uuid, user_uuid FROM users_organizations")
  user_uuid2orguuid  = { item['user_uuid']: item['uuid'] for item in orguser_list }
  return [user_uuid2orguuid[uu] for uu in uu_list]


def collection_lookup_all(names):
  collection_name_list = vw_cli(["list", "collections"])
  r = []
  for name in names:
    uu = collection_lookup(collection_name_list, name)
    if not len(uu):
      return None, f"collection not found: {name}"
    r.extend(uu)
  return r, None


def collection_lookup(col_list, name):
  r = []
  for c in col_list:
    if name[-1] == '*':     # ends in *, do globbing
      if   c['id'  ].startswith(name[:-1]): r.append(c['id'])
      elif c['name'].startswith(name[:-1]): r.append(c['id'])
    else:
      if   c['id'  ] == name: r.append(c['id'])
      elif c['name'] == name: r.append(c['id'])
  return r


def assert_group(name):
  if is_uuid(name):
    print(f"ERROR: cannot use --create with a group uuid. Group name needed.", file=sys.stderr)
    sys.exit(1)
  # INSERT OR IGNORE is not sufficient. Duplicate names are apparently permitted.grrr. Must check explicitly.
  grp = vw_sql(f"SELECT uuid FROM groups WHERE name == '{name}'") 
  if len(grp): 
    if verbose: print(f"OK: group {name} already exists")
    return

  org = vw_sql("SELECT uuid FROM organizations") 
  guuid = str(uuid.uuid4())
  cmd = f"INSERT INTO groups (uuid, organizations_uuid, name, access_all, creation_date, revision_date) VALUES ('{guuid}', '{org[0]['uuid']}', '{name}', 0, datetime('now'), datetime('now'))";
  if verbose > 1: print(f"SQL: {cmd};")
  r = vw_sql(cmd)
  if len(r): print(f"ERROR: {cmd}; -> {r}")
  return


def main(argv=None):
  args = parse_args(argv)

  if verbose > 1: print(args, file=sys.stderr)
  if not args.group:
    cmd_list_groups(args)
    return

  # else
  if args.create: assert_group(args.group)

  guuid = group_uuid(args.group)
  if not guuid:
    print(f"ERROR: cannot find group name '{args.group}'", file=sys.stderr)
    sys.exit(1)
  print(f"Group: uuid={guuid}")

  if args.list:
    if args.kind == "all" or args.kind.startswith('u'):
      cmd_list_users(args, guuid)

    if args.kind == "all" or args.kind.startswith('c'):
      cmd_list_collections(args, guuid)
    return

  if args.kind.startswith('u'):
    uu, err = user_lookup_all(args.names)
    if err:
      print(f"ERROR: {err}")
      sys.exit(1)
      
    ouu = map_user_uuid2orguuid(uu)
    if verbose > 1: print([uu, ouu, err], file=sys.stderr)

    if args.cmd == "del":
      if verbose: print(f"deleting user(s) {str(args.names)} from group {args.group}", file=sys.stderr)
      ouu_in_list = "', '".join(ouu)
      cmd = f"DELETE FROM groups_users WHERE groups_uuid == '{guuid}' AND users_organizations_uuid IN ('{ouu_in_list}')"
      if verbose > 1: print(f"SQL: {cmd};", file=sys.stderr)
      r = vw_sql(cmd)
      if len(r): print(f"ERROR: {cmd}; -> {r}", file=sys.stderr)
      return

    if args.cmd == "add":
      # sqlite supports multi value inserts, e.g.:
      # INSERT INTO employees (name, salary) VALUES ('Bob Wilson', 45000), ('Carol White', 60000);
      val_list = [f"('{guuid}', '{u}')" for u in ouu]
      if verbose: print(f"adding user(s) {str(args.names)} to group {args.group}", file=sys.stderr)
      cmd = f"INSERT OR IGNORE INTO groups_users (groups_uuid, users_organizations_uuid) VALUES {', '.join(val_list)}"
      if verbose > 1: print(f"SQL: {cmd};", file=sys.stderr)
      r = vw_sql(cmd)
      if len(r): print(f"ERROR: {r}", file=sys.stderr)
      return

  if args.kind.startswith('c'):
    uu, err = collection_lookup_all(args.names)
    if err:
      print(f"ERROR: {err}")
      sys.exit(1)

    uu_in_list = "', '".join(uu)
    if verbose > 1: print(uu, err, file=sys.stderr)
    if args.cmd == "del":
      if verbose: print(f"deleting collection(s) {str(args.names)} from group {args.group}", file=sys.stderr)
      cmd = f"DELETE FROM collections_groups WHERE groups_uuid == '{guuid}' AND collections_uuid IN ('{uu_in_list}')"
      if verbose > 1: print(f"SQL: {cmd};", file=sys.stderr)
      r = vw_sql(cmd)
      if len(r): print(f"ERROR: {cmd}; -> {r}", file=sys.stderr)
      return

    if args.cmd == "add":
      if not args.permission:
        print(f"ERRPR: no permissions specified with: collection add\nTry using -p ...", file=sys.stderr)
        sys.exit(1)
      r,h,m = parse_permission(args.permission)
      val_list = [f"('{guuid}', '{c}', '{r}', '{h}', '{m}')" for c in uu]
      if verbose: print(f"adding collection(s) {str(args.names)} to group {args.group} ({args.permission})", file=sys.stderr)
      cmd = f"INSERT OR IGNORE INTO collections_groups (groups_uuid, collections_uuid, read_only, hide_passwords, manage) VALUES {', '.join(val_list)}"
      if verbose > 1: print(f"SQL: {cmd};", file=sys.stderr)
      r = vw_sql(cmd)
      if len(r): print(f"ERROR: {cmd}; -> {r}", file=sys.stderr)
      return

  print("not impl.")    # anything else


#   group_orguser_list    = vw_sql("select groups_uuid, users_organizations_uuid from groups_users")
#   collection_group_list = vw_sql("select collections_uuid, groups_uuid, read_only, hide_passwords from collections_groups")
#   
#   user_email2uuid    = { item['email']: item['uuid'] for item in user_list }
#   user_uuid2email    = { item['uuid']: item['email'] for item in user_list }
#   user_uuid2name     = { item['uuid']: item['name'] for item in user_list }
#   
#   
#   collection_uuid2name = { item['id']: item['name'] for item in collection_list }
#   collection_name2uuid = { item['name']: item['id'] for item in collection_list }
#   
#   user_orguuid2groups = {}
#   for item in group_orguser_list:
#     u = item["users_organizations_uuid"]
#     if u not in user_orguuid2groups:
#       user_orguuid2groups[u] = [ item["groups_uuid"] ]
#     else:
#       user_orguuid2groups[u].append(item["groups_uuid"])
#   
#   group_uuid2colls = {}
#   for item in collection_group_list:
#     g = item['groups_uuid']
#     if g not in group_uuid2colls:
#       group_uuid2colls[g] = [ item ]
#     else:
#       group_uuid2colls[g].append(item)


if __name__ == "__main__":
    main()
