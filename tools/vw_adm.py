#! /usr/bin/python3
#
# vw_adm.py - list, and edit user groups and their permissions. Add or delete users.
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
import argparse, uuid, requests


server_ssh     = os.environ.get("VW_SERVER_SSH")    # username@host
sqlite_db_path = os.environ.get("VW_DB_PATH", "vaultwarden/data/db.sqlite3")
sqlite_cmd     = [ "ssh", server_ssh, "sqlite3", "-json", sqlite_db_path ]
bw_cli         = os.environ.get("VW_BW_TOOL", "bw")

verbose = 1     # 0, 1, 2 babble more ore less while working.

import argparse


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="vw_adm",
        description="Manage VaultWarden groups, their members and collection permissions. Also some basic user operations."
    )
    parser.add_argument( "-j", "--json", action="store_true", help="Emit machine-readable JSON output.")
    parser.add_argument( "-l", "--list", action="store_true", help="List all groups")
    parser.add_argument( "-c", "--create", action="store_true", help="create group if missing")
    parser.add_argument( "-p", "--permission", metavar="PERM", help="permissions, when adding collections to a group: rw, ro,pw, ro,nopw, mgr")
    subparsers = parser.add_subparsers(dest="object")

    group_parser = subparsers.add_parser("group", aliases=["g"], help="Group operations. Try: group --help for details")
    group_parser.add_argument("group", metavar="GROUP", nargs="?", help="Group name or group uuid to list or manipulate its users or collections")
    group_parser.add_argument("kind", metavar="user|col", nargs="?", choices=("u", "user", "users", "c", "col", "coll", "collection", "collections", "l", "list"), help="either 'users' or 'collections'.")
    group_parser.add_argument("cmd", metavar="add|del", nargs="?", choices=("list", "add", "del"), help="Add or delete users/collections.")
    group_parser.add_argument("names", metavar="NAMES", nargs="*", help="one or more names (or emails or uuids).")

    user_parser = subparsers.add_parser("user", aliases=["u"], help="User operations. Try: user --help for details")
    user_parser.add_argument("cmd", metavar="add|list|invite|del", choices=("add", "del", "list", "invite", "confirm"))
    user_parser.add_argument("email", metavar="EMAIL", nargs="?", help="E-Mail address or uuid to list or manipulate")
    user_parser.add_argument("names", metavar="NAMES", nargs="*", help="optional: Firstname Lastname ...")

    args = parser.parse_args(argv)

    if args.object is None:     # add_subparsers(..., required=True) in modern python.
      parser.print_help()
      parser.exit(2)

    elif args.object.startswith("g"):
      ## some business logic for groups
      # if not args.groups: args.list=True
      if args.kind in (None, "l", "list"):
        args.kind="all"
        args.list=True
      if args.cmd in (None, "l", "list"):
        args.list=True

      if args.permission and (args.cmd != "add" or args.kind not in ("c", "col", "coll", "collection")):
        print(f"ERROR: permissions specified: {args.permission} - that only works with: <group> collecion add ...", file=sys.stderr)
        sys.exit(1)

    elif args.object.startswith("u"):
        pass

    else:
        print(f"ERROR: object category {args.object} unknown. Try: group or user")
        sys.exit(1)

    return args, user_parser, group_parser


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


def cmd_list_group_collections(args, guuid):
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


def cmd_list_group_users(args, guuid):
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
  # CAUTION: This probably messes up when we have multiple organizations
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

####

def cmd_user_add(email, username):
  if username == "": username = email
  print(f"useradd <{email}> {username}")
  u = vw_sql(f"SELECT uuid FROM users WHERE email == '{email}'")
  if len(u) > 0:
    print(f"OK: user <{email}> already exists. uuid={u[0]['uuid']}")
    return
  org = vw_sql("SELECT uuid, name FROM organizations")
  cli_status = vw_cli(["status"])
  # {"serverUrl":"https://vw...","lastSync":"2026-07-06T20:43:58.991Z","userEmail":"j.weigert@...","userId":"c4b9047d-...","status":"unlocked"}

  user_uuid = str(uuid.uuid4())
  member_uuid = str(uuid.uuid4())
  stamp = str(uuid.uuid4())
  cols = "uuid, created_at, updated_at, email, name, password_hash, salt, password_iterations, akey, security_stamp, equivalent_domains, excluded_globals"
  vals = f"'{user_uuid}',datetime('now'), datetime('now'),'{email}','{username}','',X'{os.urandom(64).hex()}',600000,'','{stamp}','[]','[]'"
  cmd = f"INSERT INTO users ({cols}) VALUES ({vals})"
  if verbose > 1: print(f"SQL: {cmd};", file=sys.stderr)
  r = vw_sql(cmd)
  if len(r): print(f"ERROR: {r}", file=sys.stderr)

  status = 0    # -1=Revoked, 0=Invited, 1=Accepted, 2=Confirmed
  atype = 2     # 0=Owner, 1=Admin, 2=User, 3=Manager, 4=Custom
  inviter = "vw_adm+" + cli_status.get("userEmail", '')
  cols = "uuid, user_uuid, org_uuid, access_all, akey, status, atype, invited_by_email"
  vals = f"'{member_uuid}', '{user_uuid}', '{org[0]['uuid']}', 0, '', {status}, {atype}, '{inviter}'"
  cmd = f"INSERT INTO users_organizations ({cols}) VALUES ({vals})"
  if verbose > 1: print(f"SQL: {cmd};", file=sys.stderr)
  r = vw_sql(cmd)
  if len(r): print(f"ERROR: {r}", file=sys.stderr)

  return


def api_org_user_invite(base_url, org_uuid, user_uuid):
  # curl 'https://vw-test.heinlein-support.de/api/organizations/9051a55c-e6d0-45bf-843e-7add02ef88b0/users/d2b52a02-9d41-4578-ad5b-1d4ed8364c5d/reinvite'   -X POST   -H "authorization: Bearer $VW_BEARER_TOKEN"
  token = os.environ.get("VW_BEARER_TOKEN")    # from
  if not token:
    print("VW_BEARER_TOKEN environment variable is not set. Open Network Tab in browser console, right click a request and try 'Copy as Curl' ", file=sys.stderr)
    return
  url = f"{base_url}/api/organizations/{org_uuid}/users/{user_uuid}/reinvite"
  headers = { "Authorization": f"Bearer {token}" }

  if verbose > 0: print(f"POST {url};", file=sys.stderr)
  response = requests.post(url, headers=headers)
  response.raise_for_status()

  # Return JSON if present, otherwise raw text
  if response.headers.get("Content-Type", "").startswith("application/json"):
    return response.json()
  return response.text


def api_org_user_confirm(base_url, org_uuid, user_uuid):
  # curl 'https://vw-test.heinlein-support.de/api/organizations/9051a55c-e6d0-45bf-843e-7add02ef88b0/users/d2b52a02-9d41-4578-ad5b-1d4ed8364c5d/confirm' -X POST -H 'authorization: Bearer $VW_BEARER_TOKEN" --data-raw '{"key":"4.es6/XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX==","defaultUserCollectionName":"2.02fJu7cBFUzX/trIsdiIWg==|sCZ2r2BMCAVa9Czo1ik9iw==|bzqy/fPiR8nEv7NMpc8dS/+QGORSLC71zHKiNrC6BXM="}'
  #
  # This should probably remain a manual step, for mutual identity verification.
  print("not impl.")


# def api_invite_resend(base_url, admin_token, id):
#   # DRAFT... need the admin token from
#   # /admin/ -> General Settings -> Admin token/Argon2 PHC -> Show (or something else?
#   post_url = f"{base_url}/admin/users/{id}/invite/resend"
#   headers = {
#     "Content-Type": "application/json",
#   }
#   cookies = {
#     "VW_ADMIN": admin_token,  # admin session cookie
#   }
#   response = requests.post(post_url, headers=headers, cookies=cookies)
#   response.raise_for_status()
#   return response


def cmd_user_invite(email):
  uu, err = user_lookup_all([email])
  if err:
    print(f"ERROR: {err} - try: user add ... ")
    sys.exit(1)
  ouu = map_user_uuid2orguuid(uu)
  org = vw_sql("SELECT uuid FROM organizations")
  cli_status = vw_cli(["status"])
  api_org_user_invite(cli_status['serverUrl'], org[0]['uuid'], ouu[0])


def cmd_user_delete(email):
  uu, err = user_lookup_all([email])
  if err:
    print(f"ERROR: {err} - try: user add ... ")
    sys.exit(1)
  ouu = map_user_uuid2orguuid(uu)
  cmd = f"DELETE FROM groups_users WHERE users_organizations_uuid == '{ouu[0]}'"
  if verbose > 1: print(f"SQL: {cmd};", file=sys.stderr)
  r = vw_sql(cmd)
  if len(r): print(f"ERROR: {r}", file=sys.stderr)

  cmd = f"DELETE FROM users_collections WHERE user_uuid == '{ouu[0]}'"
  if verbose > 1: print(f"SQL: {cmd};", file=sys.stderr)
  r = vw_sql(cmd)
  if len(r): print(f"ERROR: {r}", file=sys.stderr)

  cmd = f"DELETE FROM users_organizations WHERE uuid == '{ouu[0]}'"
  if verbose > 1: print(f"SQL: {cmd};", file=sys.stderr)
  r = vw_sql(cmd)
  if len(r): print(f"ERROR: {r}", file=sys.stderr)

  cmd = f"DELETE FROM users WHERE uuid == '{uu[0]}'"
  if verbose > 1: print(f"SQL: {cmd};", file=sys.stderr)
  r = vw_sql(cmd)
  if len(r): print(f"ERROR: {r}", file=sys.stderr)

  return


def user_ops(user_parser, args):
  if verbose > 1: print("user_ops:", args, file=sys.stderr)
  # ./vw_adm.py user add juergen@fabmail.org Jürgen Weigert
  # -> (cmd='add', create=False, email='juergen@fabmail.org', json=False, list=False, names=['Jürgen', 'Weigert'], object='u', permission=None)
  if args.cmd == "add":
    if args.email is None or not "@" in args.email:
      print(f"ERROR: user add needs an email address. not {args.email}", file=sys.stderr)
      user_parser.print_help()
      user_parser.exit(3)
    return cmd_user_add(args.email, " ".join(args.names))

  if args.cmd == "invite":
    if args.email is None:
      print(f"ERROR: specify email address of an added user", file=sys.stderr)
      sys.exit(1)
    return cmd_user_invite(args.email)

  if args.cmd == "del":
    if args.email is None:
      print(f"ERROR: specify email address of an added user", file=sys.stderr)
      sys.exit(1)
    return cmd_user_delete(args.email)

  if args.cmd == "list":
    user_list = vw_sql(f"SELECT uuid, name, email FROM users")
    orguser_list = vw_sql("SELECT uuid, user_uuid FROM users_organizations")
    user_uuid2orguuid  = { item['user_uuid']: item['uuid'] for item in orguser_list }
    for u in user_list:
      if u["uuid"] in user_uuid2orguuid:
        u["member_uuid"] = user_uuid2orguuid[u["uuid"]]

    if args.json:
      print(json.dumps(user_list))
    else:
      for u in user_list:
        print(f"\t{u['uuid']} {u['name']} <{u['email']}>")
    return

  print(f"ERROR: user_ops(cmd={args.cmd}) not impl.", file=sys.stderr)
  return


def main(argv=None):
  args, user_parser, group_parser = parse_args(argv)

  if verbose > 1: print(args, file=sys.stderr)

  if args.object.startswith("u"):
    user_ops(user_parser, args)
    return

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
      cmd_list_group_users(args, guuid)

    if args.kind == "all" or args.kind.startswith('c'):
      cmd_list_group_collections(args, guuid)
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
