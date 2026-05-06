#! /bin/bash
#

osd="$1"

set -x
if [ -z "$osd" ]; then
  ceph pg ls remapped -f json | jq -c '.pg_stats[]? | { pgid, acting, up, state }'
else
  ceph pg ls-by-osd "$osd" remapped -f json | jq -c '.pg_stats[]? | { pgid, acting, up, state }'
fi
