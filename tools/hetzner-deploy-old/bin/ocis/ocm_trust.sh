#! /bin/bash
#
# FIXME: make this a loop to wok with n >= 2 arguments...

ssh_user=root

if [ -z "$1" -o -z "$2" -o "$1" = "-h" -o "$1" = "--help" ]; then
  echo "ocm_trust.sh usage:"
  echo ""
  echo "	$0 host1 host2 ..."
  exit 1
fi

declare -a hosts

for arg in "$@"; do
  host=$(echo "$arg" | sed -e 's@^https://@@' -e 's@/.*$@@')
  hosts+=($host)
done

# set -x	# we want to see what is going on.
for host in "${hosts[@]}"; do 
  for trustee in "${hosts[@]}"; do 
    if [ "$host" != "$trustee" ]; then
      echo + ssh $ssh_user@$host ocmproviders.sh add https://$trustee
      ssh $ssh_user@$host ocmproviders.sh add https://$trustee
    fi
  done
  # FIXME: ocmproviders.sh should return nonzero status, if nothing to do.
  #        so that we can do restarts only when needed.
  echo + ssh $ssh_user@$host service ocis restart
  ssh $ssh_user@$host service ocis restart
done
