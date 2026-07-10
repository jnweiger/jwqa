#! /usr/bin/python3
#
# vw_access_check.py - find out which user can access what item how and why.
#
# This uses a mixture of client api and sql access.
# - the client api misses info about user groups
# - the sql database stores all names (except groups) encrypted.
#
# 2026 (C) j.weigert@heinlein-support.de
#

import sys, os, json, subprocess, shlex

server_ssh     = os.environ.get("VW_SERVER_SSH")    # username@host
sqlite_db_path = os.environ.get("VW_DB_PATH", "vaultwarden/data/db.sqlite3")
sqlite_cmd     = [ "ssh", server_ssh, "sqlite3", "-json", sqlite_db_path ]
bw_cli         = os.environ.get("VW_BW_TOOL", "bw")

def vw_sql(query):
    if not server_ssh:
        raise EnvironmentError(f"{sys.argv[0]}: ERROR: env variable VW_SERVER_SSH is not defined")
    proc = subprocess.run( sqlite_cmd + [shlex.quote(query)], check=True, stdout=subprocess.PIPE, universal_newlines=True)
    return json.loads(proc.stdout)


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


collection_list = vw_cli(["list", "collections"])
# [{'object': 'collection', 'id': '389811e6-38db-460b-8eff-bd4a7fc0c8a7', 'organizationId': '9051a55c-e6d0-45bf-843e-7add02ef88b0', 'name': 'Default collection', 'externalId': None},
#  {'object': 'collection', 'id': '8cec38c7-264b-49ff-af97-a8bdef50e146', 'organizationId': '9051a55c-e6d0-45bf-843e-7add02ef88b0', 'name': 'XXXXXXXXXXXXXXXXXXXXXXXX', 'externalId': None},
#  {'object': 'collection', 'id': '1d408c16-43a6-4b13-97f3-74b0bd250b9f', 'organizationId': '9051a55c-e6d0-45bf-843e-7add02ef88b0', 'name': 'YYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY', 'externalId': None},
# ...

user_list = vw_sql("select uuid,email,name from users")
# [{'uuid': 'c4b9047d-f41c-499f-b26b-1caf83ed16cb', 'email': 'j.XXXXXXXXXXXXXXXXXXXXXXXXXXX', 'name': 'j.XXXXXXXXXXXXXXXXXXXXXXXXXXX'},
#  {'uuid': '20d0f8be-2676-4d0b-bb0e-f051cc11072a', 'email': 't.XXXXXXXXXXXXXXXXXXXXXXXXXX', 'name': 't.XXXXXXXXXXXXXXXXXXXXXXXXXX'},
#  {'uuid': '11db9933-aa89-41a4-ae31-c6e3cd1db8c1', 'email': 'testy@XXXXXXXXXXXXXXXXXXX', 'name': 'testy@XXXXXXXXXXXXXXXXXXX'}]
# ...
orguser_list          = vw_sql("select uuid,user_uuid from users_organizations")
group_list            = vw_sql("select uuid,organizations_uuid,name,access_all from groups")
group_orguser_list    = vw_sql("select groups_uuid, users_organizations_uuid from groups_users")
collection_group_list = vw_sql("select collections_uuid,groups_uuid,read_only,hide_passwords from collections_groups")

user_email2uuid    = { item['email']: item['uuid'] for item in user_list }
user_uuid2email    = { item['uuid']: item['email'] for item in user_list }
user_uuid2name     = { item['uuid']: item['name'] for item in user_list }
user_uuid2orguuid  = { item['user_uuid']: item['uuid'] for item in orguser_list }

group_byuuid    = { item['uuid']: item         for item in group_list }

collection_uuid2name = { item['id']: item['name'] for item in collection_list }
collection_name2uuid = { item['name']: item['id'] for item in collection_list }

user_orguuid2groups = {}
for item in group_orguser_list:
  u = item["users_organizations_uuid"]
  if u not in user_orguuid2groups:
    user_orguuid2groups[u] = [ item["groups_uuid"] ]
  else:
    user_orguuid2groups[u].append(item["groups_uuid"])

group_uuid2colls = {}
for item in collection_group_list:
  g = item['groups_uuid']
  if g not in group_uuid2colls:
    group_uuid2colls[g] = [ item ]
  else:
    group_uuid2colls[g].append(item)


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


