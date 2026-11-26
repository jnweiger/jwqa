#! /bin/bash

prefix="$1"

if [ -z "$prefix" ]; then
  echo
  echo "Usage: $0 nameprefix"
  echo
  exit 1
fi

echo -n "Searching "
# we want to show the project name, in case the server listing takes a while.
# hcloud cannotprint the project name. But there is a rest API endpoint, that can:
curl -s -H "Authorization: Bearer $HCLOUD_TOKEN"   https://api.hetzner.cloud/v1/_tokens/current | jq -r '"hcloud project " + .token.project.name'
echo "for server names starting with $prefix ..."

hosts=$(hcloud server list -o noheader -o columns=name | grep "^$prefix")
echo $hosts
echo

echo Press ENTER to delete these hosts - CTRL-C to abort
read a

for host in $hosts; do (set -x; hetzner_dns del      $host); done
for host in $hosts; do (set -x; hcloud server delete $host); done
for host in $hosts; do (set -x; hcloud volume delete $host-osd); done
(set -x; hcloud network delete $prefix-cluster)

