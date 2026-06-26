#! /bin/sh
#
# (C) 2026, j.weigert@heinlein-support.de
#
# requires: sh, sed, jq, getfattr, ceph


act_up="up"
# act_up="acting"

# prefix is the inode number as a lower case hexadecimal string.
path_to_prefix() { printf "%x\n" $(stat -c "%i" "$1"); }

path_to_pool()
{
  # stripe_unit=4194304 stripe_count=1 object_size=4194304 pool=jw_cephfs_data_ec
  getfattr --only-values -n ceph.file.layout "$1" 2>/dev/null | sed -e 's@.*pool=@@' -e 's@ .*@@'
}

path_to_unit()
{
  # stripe_unit=4194304 stripe_count=1 object_size=4194304 pool=jw_cephfs_data_ec
  getfattr --only-values -n ceph.file.layout "$1" 2>/dev/null | sed -e 's@.*stripe_unit=@@' -e 's@ .*@@'
}

max_index()
{
   length="$(stat -c '%s' "$1")"
   unit="$(path_to_unit "$1")"
   echo "$(expr $length / $unit)"
}

if [ -z "$1" -o "$1" = "--help" ]; then
  cat <<EOF
Usage:
	$0 path-to-file
EOF
  exit 1
fi

if [ ! -e "$1" ]; then
  echo "ERROR: file not found: $1"
  exit 1
fi

# set -x

pool="$(path_to_pool "$1")"

if [ -z "$pool" ]; then
  echo "ERROR: could not find pool. Not inside a cephfs mount? $1"
  exit 2
fi

obj_prefix="$(path_to_prefix "$1")"


# "ceph osd find" is slow. multiple "ceph osd find" are very slow.
# loading all of ceph osd tree into a nicely formatted json and using multiple jq calls to do the lookups is fast.

# generate a json dictionary. Aeh. bash dictionary? python?
tree_parents="$(echo "{"; ceph osd tree -f json | jq -r '.nodes[] | select(.children?)  | .name as $name | .children[] | "\"\(. )\": \"\($name)\","'; echo '"-":"" }')"

# lookup method.
get_parent_of()
{
  echo "$tree_parents" | jq -r ".[\"$1\"]"
}


for idx in $(seq 0 "$(max_index "$1")"); do
  object="$(printf "$obj_prefix.%08d\n" $idx)"
  map="$(ceph osd map "$pool" "$object" -f json)"
  pgid="$(echo "$map" | jq -r '.pgid')"
  primary="$(echo "$map" | jq -r ".${act_up}_primary")"
  echo $object pool=$pool pgi=$pgid

  for osd in $(echo "$map" | jq ".$act_up[]"); do
    # printf "    $(ceph osd find "$osd" -f json | jq -r '.host') osd.$osd\n"
    ispri=""
    test "$osd" = "$primary" && ispri="\t*"
    echo "\t$(get_parent_of "$osd")\tosd.$osd$ispri"
  done
done


