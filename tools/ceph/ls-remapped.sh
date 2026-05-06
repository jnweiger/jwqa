#! /bin/bash
#

osd="$1"
# set -x

if [ -z "$osd" ]; then
  ceph pg ls remapped -f json 
else
  ceph pg ls-by-osd "$osd" remapped -f json 
fi |\
 jq -c '.pg_stats[]? | { pgid, acting, up, state }' | sed -e 's/,"/	"/g' | tr -d '{}"'


