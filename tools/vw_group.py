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
    parser.add_argument( "-p", "--permission", metavar="PERM", help="permissions, when adding collections to a group: rw, ro,pw, ro,nopw")
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
      print(f"ERROR: permissions specified: {args.permission} - that only works with: <group> collecion add ...")
      sys.exit(1)

    return args


def parse_permission(p):
  a = p.split(',')
  r = {}
  if "rw"   in a:
    r['read_only'] = 0
    r['hide_passwords'] = 0
  if "ro"   in a: r['read_only'] = 1
  if "pw"   in a: r['hide_passwords'] = 0
  if "nopw" in a: r['hide_passwords'] = 1
  if len(r) != 2:
    print(f"ERROR: permission: use one of: 'rw', 'ro,pw', 'ro,nopw'")
    sys.exit(1)

  return (r['read_only'], r['hide_passwords'])


def vw_sql(query):
    if not server_ssh:
        print(f"{sys.argv[0]}: ERROR: env variable VW_SERVER_SSH is not defined")
        sys.exit(1)
    # FIXME: we guard against shell, but we are probably prone to SQL injection.
    proc = subprocess.run( sqlite_cmd + [shlex.quote(query)], check=True, stdout=subprocess.PIPE, universal_newlines=True)
    return json.loads(proc.stdout or "[]")


def vw_cli(cmd):
    vw_session = os.environ.get("VW_SESSION")
    if not vw_session:
        print(f"{sys.argv[0]}: ERROR: env variable VW_SESSION is not defined")
        sys.exit(1)

    vw_cli_home = os.environ.get("VW_CLI_HOME")
    if not vw_cli_home:
        print(f"{sys.argv[0]}: ERROR: env variable VW_CLI_HOME is not defined")
        sys.exit(1)

    env = os.environ.copy()
    env["HOME"] = vw_cli_home
    cli_cmd = [bw_cli, f"--session={vw_session}"] + list(cmd)

    proc = subprocess.run(cli_cmd, env=env, check=True, stdout=subprocess.PIPE, universal_newlines=True)
    return json.loads(proc.stdout)


def cmd_list_all():
  # print(user_email2uuid)
  # print(user_orguuid2groups)
  # print(collection_name2uuid.keys())
  
  for user_email in user_email2uuid.keys():
    user_uuid = user_email2uuid[user_email]
    user_name = user_uuid2name[user_uuid]
    if user_name == user_email:
      user_print = user_email
    else:
      user_print = f"{user_name} <{user_email}>"
  
    o = user_uuid2orguuid.get(user_uuid)
    if not o:
      print(f"user {user_print} not found in sqlite table users_organizations")
      next
  
    gl = user_orguuid2groups.get(o)
    if not gl:
      print(f"user {user_print} orguuid {o} not found in sqlite table groups_users")
      next
  
    # list all groups for this user
    print(f"groups of {user_print}:")
    for g in gl:
      print(f"\t{g} {group_byuuid[g]['name']}")
      # list all collections for this user group
      if g in group_uuid2colls:
        for c in group_uuid2colls[g]:
          # print(f"\t\t{c['collections_uuid']} ro={c['read_only']} h={c['hide_passwords']} {collections_uuid.get(c['collections_uuid'], '-?-')}")
          print(f"\t\t{c['collections_uuid']} {'ro' if c['read_only'] else 'rw' } {'nop' if c['hide_passwords'] else '   '} {collection_uuid2name.get(c['collections_uuid'], '('+c['collections_uuid']+')' )}")


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
      collection_uuid_list = vw_sql(f"SELECT collections_uuid, read_only, hide_passwords FROM collections_groups WHERE groups_uuid == '{guuid}'")
      collection_name_list = vw_cli(["list", "collections"])
      collection_uuid2name = { item['id']: item['name'] for item in collection_name_list }
      if args.json:
        for c in collection_uuid_list:
          c['name'] = collection_uuid2name[c['collections_uuid']] 
        print(json.dumps(collection_uuid_list))
      else:
        for c in collection_uuid_list:
          cu = c['collections_uuid']
          print(f"\t{cu} ro={c['read_only']} pw={1-c['hide_passwords']} '{collection_uuid2name.get(cu, '-?-')}'")


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
      return None, f"user {name} not found"
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
      return None, f"collection {name} not found"
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
    print(f"ERROR: cannot use --create with a group uuid. Group name needed.")
    sys.exit(1)
  # INSERT OR IGNORE is not sufficient. Duplicate names are apparently permitted.grrr. Must check explicitly.
  grp = vw_sql(f"SELECT uuid FROM groups WHERE name == '{name}'") 
  if len(grp): 
    print(f"OK: group {name} already exists")
    return

  org = vw_sql("SELECT uuid FROM organizations") 
  guuid = str(uuid.uuid4())
  cmd = f"INSERT INTO groups (uuid, organizations_uuid, name, access_all, creation_date, revision_date) VALUES ('{guuid}', '{org[0]['uuid']}', '{name}', 0, datetime('now'), datetime('now'))";
  print(f"SQL: {cmd};")
  r = vw_sql(cmd)
  if len(r): print(f"ERROR: {cmd}; -> {r}")
  return


def main(argv=None):
  args = parse_args(argv)

  print(args, file=sys.stderr)
  if not args.group:
    cmd_list_groups(args)
    return

  # else
  if args.create: assert_group(args.group)

  guuid = group_uuid(args.group)
  if not guuid:
    print(f"ERROR: cannot find group name '{args.group}'")
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
    ouu = map_user_uuid2orguuid(uu)
    print([uu, ouu, err])

    if args.cmd == "del":
      print(f"deleting user(s) {str(args.names)} from group {guuid}")
      ouu_in_list = "', '".join(ouu)
      cmd = f"DELETE FROM groups_users WHERE groups_uuid == '{guuid}' AND users_organizations_uuid IN ('{ouu_in_list}')"
      print(f"SQL: {cmd};")
      r = vw_sql(cmd)
      if len(r): print(f"ERROR: {cmd}; -> {r}")
      return

    if args.cmd == "add":
      # sqlite supports multi value inserts:
      # INSERT INTO employees (name, salary) VALUES ('Bob Wilson', 45000), ('Carol White', 60000);
      val_list = [f"('{guuid}', '{u}')" for u in ouu]
      cmd = f"INSERT OR IGNORE INTO groups_users (groups_uuid, users_organizations_uuid) VALUES {', '.join(val_list)}"
      print(f"SQL: {cmd};")
      r = vw_sql(cmd)
      if len(r): print(f"ERROR: {r}")
      return

  if args.kind.startswith('c'):
    uu, err = collection_lookup_all(args.names)
    uu_in_list = "', '".join(uu)
    print(uu, err)
    if args.cmd == "del":
      print(f"deleting collection(s) {str(args.names)} from group {guuid}")
      cmd = f"DELETE FROM collections_groups WHERE groups_uuid == '{guuid}' AND collections_uuid IN ('{uu_in_list}')"
      print(f"SQL: {cmd};")
      r = vw_sql(cmd)
      if len(r): print(f"ERROR: {cmd}; -> {r}")
      return

    if args.cmd == "add":
      if not args.permission:
        print(f"ERRPR: no permissions specified with: collection add\nTry using -p ...")
        sys.exit(1)
      r,h = parse_permission(args.permission)
      val_list = [f"('{guuid}', '{c}', '{r}', '{h}')" for c in uu]
      print(f"adding collection(s) {str(args.names)} to group {guuid}")
      cmd = f"INSERT OR IGNORE INTO collections_groups (groups_uuid, collections_uuid, read_only, hide_passwords) VALUES {', '.join(val_list)}"
      print(f"SQL: {cmd};")
      r = vw_sql(cmd)
      if len(r): print(f"ERROR: {cmd}; -> {r}")
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
# 
#   cmd_list_all()


if __name__ == "__main__":
    main()
