#! /bin/bash
#
# requires:
#	export HCLOUD_TOKEN=...
#	export HCLOUD_DNS_ZONE=jwqa.de	# or defaults to finding the zone by suffix match of the fqdn name.
#       know th eavailable types from hcloud server-type list

verbose=true	# true,false

default_hcloud_image=ubuntu-24.04
default_hcloud_type=cpx21

if [ -z "$1" -o "$1" == "--help" -o "$1" == "-h" ]; then
  cat <<EOF 1>&2
Usage: 

	export HCLOUD_TOKEN=...
	export HCLOUD_DNS_ZONE=...
	$0 ./oc/clamav.sh			# start a virus scanner machine

	hcloud server-type list			# study available server types
	hcloud image list  -a x86 | grep '\(debian\|ubuntu\)'	# study available images

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

if [ -z "$HCLOUD_SSH_KEYS" ]; then
  echo 1>&2 "$0 ERROR: env variable HCLOUD_SSH_KEYS is not set."
  echo 1>&2 "see available keys with: hcloud ssh-key list"
  exit 1
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

script="$1"
test -f "$script.sh" && script="$script.sh" 

if [ ! -f "$script" ]; then
  mydir="$(dirname "$(readlink -f "$0")")"
  test -f "$mydir/$script"    && script="$mydir/$script" 
  test -f "$mydir/$script.sh" && script="$mydir/$script.sh" 
fi
if [ ! -f "$script" ]; then
  echo 1>&2 "$0 ERROR: could not find $script"
  echo 1>&2 " -- also tried $script.sh and $mydir/$script[.sh]"
  exit 1
fi

$verbose && echo "using $(readlink -f $script)"

# extract some variables
HCLOUD_IMAGE="$(sed -ne "s@^#\s*HCLOUD_IMAGE:\s*@@p" $script | sed -e 's@\s.*$@@')"
HCLOUD_TYPE="$( sed -ne "s@^#\s*HCLOUD_TYPE:\s*@@p"  $script | sed -e 's@\s.*$@@')"
name="$(sed -ne "s@^#\s*DNS_NAME:\s*@@p" -e 's@\s.*$@@' $script)"

test -z "$HCLOUD_TYPE" && HCLOUD_TYPE=$default_hcloud_type
test -z "$HCLOUD_IMAGE" && HCLOUD_IMAGE=$default_hcloud_image
test -z "$name" && name=$(echo "$HCLOUD_IMAGE-DATE" | tr '._' '-')
name=$(echo "$name" | sed -e "s@DATE@$(date +%Y%m%d)@")

ssh_key_opts=''
for key in $(echo "$HCLOUD_SSH_KEYS" | tr ',' ' '); do
  ssh_key_opts="$ssh_key_opts --ssh-key $key"
done

(set -x; hcloud server create --type "$HCLOUD_TYPE" $ssh_key_opts --image "$HCLOUD_IMAGE" --name "$name")
