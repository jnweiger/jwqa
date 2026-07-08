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

server_ssh     = os.environ.get("VW_SERVER_SSH")    # username@host
sqlite_db_path = os.environ.get("VW_DB_PATH", "vaultwarden/data/db.sqlite3")
sqlite_cmd     = [ "ssh", server_ssh, "sqlite3", "-json", sqlite_db_path ]
bw_cli         = os.environ.get("VW_BW_TOOL", "bw")

import sys, os, json, subprocess, shlex

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

user_list = vw_sql("select uuid,email,name from users")

print(user_list)
print(collection_list)

