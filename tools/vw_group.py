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
    parser.add_argument( "-p", "--permission", metavar="PERM", help="permissions, when adding collections to a group: comma separated list of: readonly nopass. Default: full edit permissions")
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



def vw_sql(query):
    if not server_ssh:
        raise EnvironmentError(f"{sys.argv[0]}: ERROR: env variable VW_SERVER_SSH is not defined")
    # FIXME: we guard against shell, but we are probably prone to SQL injection.
    proc = subprocess.run( sqlite_cmd + [shlex.quote(query)], check=True, stdout=subprocess.PIPE, universal_newlines=True)
    return json.loads(proc.stdout or "[]")


def vw_cli(cmd):
    vw_session = os.environ.get("VW_SESSION")
    if not vw_session:
        raise EnvironmentError(f"{sys.argv[0]}: ERROR: env variable VW_SESSION is not defined")

    vw_cli_home = os.environ.get("VW_CLI_HOME")
    if not vw_cli_home:
        raise EnvironmentError(f"{sys.argv[0]}: ERROR: env variable VW_CLI_HOME is not defined")

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


def main(argv=None):
  args = parse_args(argv)

  print(args, file=sys.stderr)
  if args.list and args.group is None:
    group_list = vw_sql("select uuid, organizations_uuid, name, access_all from groups")
    if args.json:
      print(json.dumps(group_list))
    else:
      for g in group_list:
        print(f"{g['uuid']}\t{shlex.quote(g['name'])}")
    return

  if args.group:
    if is_uuid(args.group):
      guuid = args.group
    else:
      group = vw_sql(f"select uuid from groups where name == '{args.group}'")
      if not len(group):
         print(f"ERROR: cannot find group name '{args.group}'")
         sys.exit(1)
      guuid = group[0]["uuid"]
  print(guuid)

  if args.list:
    if args.kind == "all" or args.kind.startswith('u'):
      print(f"Group '{guuid}' users:")
      orguser_list  = vw_sql(f"select users_organizations_uuid from groups_users where groups_uuid == '{guuid}'")
      ou_in_list = "', '".join([x["users_organizations_uuid"] for x in orguser_list])
      uu_list = vw_sql(f"select user_uuid from users_organizations where uuid in ('{ou_in_list}')")
      uu_in_list = "', '".join([x["user_uuid"] for x in uu_list])
      user_list = vw_sql(f"select uuid, name, email from users where uuid in ('{uu_in_list}')")
      if args.json:
        print(json.dumps(user_list))
      else:
        for u in user_list:
          print(f"\t{u['uuid']} {u['name']} <{u['email']}>")

    if args.kind == "all" or args.kind.startswith('c'):
      print(f"Group '{guuid}' collections:")
      collection_uuid_list = vw_sql(f"select collections_uuid, read_only, hide_passwords from collections_groups where groups_uuid == '{guuid}'")
      collection_name_list = vw_cli(["list", "collections"])
      collection_uuid2name = { item['id']: item['name'] for item in collection_name_list }
      if args.json:
        for c in collection_uuid_list:
          c['name'] = collection_uuid2name[c['collections_uuid']] 
        print(json.dumps(collection_uuid_list))
      else:
        for c in collection_uuid_list:
          print(f"\t{c['collections_uuid']} ro={c['read_only']} pw={1-c['hide_passwords']} '{collection_uuid2name[c['collections_uuid']]}'")

    return
      
  print("not impl.")

#   collection_list = vw_cli(["list", "collections"])
#   # [{'object': 'collection', 'id': '389811e6-38db-460b-8eff-bd4a7fc0c8a7', 'organizationId': '9051a55c-e6d0-45bf-843e-7add02ef88b0', 'name': 'Default collection', 'externalId': None},
#   #  {'object': 'collection', 'id': '8cec38c7-264b-49ff-af97-a8bdef50e146', 'organizationId': '9051a55c-e6d0-45bf-843e-7add02ef88b0', 'name': 'XXXXXXXXXXXXXXXXXXXXXXXX', 'externalId': None},
#   #  {'object': 'collection', 'id': '1d408c16-43a6-4b13-97f3-74b0bd250b9f', 'organizationId': '9051a55c-e6d0-45bf-843e-7add02ef88b0', 'name': 'YYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY', 'externalId': None},
#   # ...
#   
#   user_list = vw_sql("select uuid, email, name from users")
#   # [{'uuid': 'c4b9047d-f41c-499f-b26b-1caf83ed16cb', 'email': 'j.XXXXXXXXXXXXXXXXXXXXXXXXXXX', 'name': 'j.XXXXXXXXXXXXXXXXXXXXXXXXXXX'},
#   #  {'uuid': '20d0f8be-2676-4d0b-bb0e-f051cc11072a', 'email': 't.XXXXXXXXXXXXXXXXXXXXXXXXXX', 'name': 't.XXXXXXXXXXXXXXXXXXXXXXXXXX'},
#   #  {'uuid': '11db9933-aa89-41a4-ae31-c6e3cd1db8c1', 'email': 'testy@XXXXXXXXXXXXXXXXXXX', 'name': 'testy@XXXXXXXXXXXXXXXXXXX'}]
#   # ...
#   orguser_list          = vw_sql("select uuid, user_uuid from users_organizations")
#   group_list            = vw_sql("select uuid, organizations_uuid, name, access_all from groups")
#   group_orguser_list    = vw_sql("select groups_uuid, users_organizations_uuid from groups_users")
#   collection_group_list = vw_sql("select collections_uuid, groups_uuid, read_only, hide_passwords from collections_groups")
#   
#   user_email2uuid    = { item['email']: item['uuid'] for item in user_list }
#   user_uuid2email    = { item['uuid']: item['email'] for item in user_list }
#   user_uuid2name     = { item['uuid']: item['name'] for item in user_list }
#   user_uuid2orguuid  = { item['user_uuid']: item['uuid'] for item in orguser_list }
#   
#   group_byuuid    = { item['uuid']: item         for item in group_list }
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
