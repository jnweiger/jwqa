#! /bin/bash
#
# requires:
#	export HCLOUD_TOKEN=...
#	export HCLOUD_DNS_ZONE=jwqa.de	# or defaults to finding the zone by suffix match of the fqdn name.

verbose=true	# true,false

if [ -n "$1" -a "$1" != "add" -a "$1" != "del" -a "$1" != "list" ]; then
  cat <<EOF 1>&2
Usage: 

	export HCLOUD_TOKEN=...
	export HCLOUD_DNS_ZONE=...
	$0 [list]		# list all records in the zone
	$0 add NAME IP_ADDR 	# add a new A record. Name can be FQDN or a plain domain name, if HCLOUD_DNS_ZONE is set.
	$0 del NAME|IP_ADDR	# records can be deleted by IP_ADDR or by NAME.
EOF
  exit 0
fi

if [ -z "$HCLOUD_TOKEN" ]; then
  echo 1>&2 "$0 ERROR: env variable HCLOUD_TOKEN is not set."
  echo 1>&2 "	Visit https://console.hetzner.com -> Select your Project -> Security -> API-Tokens -> Add ..."
  exit 1
fi
vers=$(hcloud version 2>/dev/null)
if [ -z "$vers" ]; then
  echo 1>&2 "$0 ERROR: hcloud comand is not installed correctly."
  echo 1>&2 "	Visit https://github.com/hetznercloud/cli/releases/latest"
  echo 1>&2 "	or try:	go install github.com/hetznercloud/cli/cmd/hcloud@latest"
  exit 1
fi

if [ -z "$1" -o "$1" == "list" ]; then
  if [ -z "$HCLOUD_DNS_ZONE" ]; then
    echo 1>&2 "$0 ERROR: env variable HCLOUD_DNS_ZONE is not set, cannot list records without a zone."
    exit 1
  fi
  hcloud zone rrset list $HCLOUD_DNS_ZONE
  if [ -z "$1" ]; then
    echo 1>&2 ""
    echo 1>&2 "use:		$0 add|del [FQDN] [IP_ADDR]"
  fi  
fi  

# sets global variable name and possibly also HCLOUD_DNS_ZONE
set_name_and_check_zone()
{
  name="$1"
  test -z "$name" && return

  if [ -z "$HCLOUD_DNS_ZONE" ]; then
    # we have no explizit zone name, try to match one.
    zones="$(hcloud zone list -o columns=NAME -o noheader)"
    if [ -z "$zones" ]; then
      echo 1>&2 "$0 ERROR: nothing found: hcloud zone list"
      exit 1
    fi
    $verbose && echo 1>&2 "Zones managed here:" $zones
    for z in $zones; do
      if [[ $name = *.$z ]]; then
        HCLOUD_DNS_ZONE="$z"
      fi
    done
    if [ -z "$HCLOUD_DNS_ZONE" ]; then
      echo 1>&2 "$0 ERROR: $name is not an FQDN in:" $zones
      echo 1>&2 "Please give a full qualified domain name, or set HCLOUD_DNS_ZONE."
      exit 1
    fi 
  fi
  name="${name%.$HCLOUD_DNS_ZONE}"	# strip the zone name, if included.
}

if [ "$1" == "add" ]; then
  set_name_and_check_zone "$2"
  ipaddr="$3"
  if [ -z "$name" -o -z "$ipaddr" ]; then
    echo 1>&2 "$0 ERROR: add needs two parameters: NAME IP_ADDR"
    exit 1
  fi
  # set-records is a create_or_update command.
  (set -x; hcloud zone rrset set-records --record $ipaddr $HCLOUD_DNS_ZONE $name A)
  exit 0
fi

if [ "$1" == "del" ]; then
  set_name_and_check_zone "$2"
  ipaddr="$3"

  if [ -z "$name" -a -z "$ipaddr" ]; then
    echo 1>&2 "$0 ERROR: delete needs at least one of NAME or IP_ADDR"
    exit 1
  fi

  if [ -n "$name" -a -n "$ipaddr" ]; then
    (set -x; hcloud zone rrset remove-records --record $ipaddr $HCLOUD_DNS_ZONE $name A)
    exit 0
  fi

  a_records=$(hcloud zone rrset list jwqa.de -o json | jq -r '.[] | select(.type == "A") | "\"\(.name)\"\t\([.records[].value | tostring])"')
  # $verbose && echo "$a_records"
  
  matches=$(echo "$a_records" | grep "\"$name\"" | tr -d '"[]')
  # av      46.62.160.228
  # foo     46.62.160.228
  while read name ipaddr; do
    (set -x; hcloud zone rrset remove-records --record $ipaddr $HCLOUD_DNS_ZONE $name A)
  done <<< $matches
fi
