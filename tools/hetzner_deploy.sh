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

	# eventually...
	hcloud server delete SERVER_NAME
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
DNS_NAMES="$(sed -ne "s@^#\s*DNS_NAME:\s*@@p" -e 's@\s.*$@@' $script)"

test -z "$HCLOUD_TYPE" && HCLOUD_TYPE=$default_hcloud_type
test -z "$HCLOUD_IMAGE" && HCLOUD_IMAGE=$default_hcloud_image
test -z "$dns_names" && dns_names=$(echo "$HCLOUD_IMAGE-DATE" | tr '._' '-')
DNS_NAMES="$(echo "$DNS_NAMES" | sed -e "s@DATE@$(date +%Y%m%d)@")"
set_name_and_check_zone "$(echo "$DNS_NAMES" | head -n1)"		# first element, if its a list.

FQDNS="$(echo "$DNS_NAMES" | sed -e "s/$/.$HCLOUD_DNS_ZONE/")"

ssh_key_opts=''
for key in $(echo "$HCLOUD_SSH_KEYS" | tr ',' ' '); do
  ssh_key_opts="$ssh_key_opts --ssh-key $key"
done

origin_label="$(echo "orgin=$(basename $0) $1" | tr ' /:.,;+-' '_')"	# only alpanumeric and _, sigh

set -x
hcloud server create --type "$HCLOUD_TYPE" --label "$origin_label" $ssh_key_opts --image "$HCLOUD_IMAGE" --name "$name" || exit 1
set +x

ssh_opts="-o ConnectTimeout=10 -o CheckHostIP=no -o StrictHostKeyChecking=no -o PasswordAuthentication=no"

IPADDR="$(hcloud server ip "$name")"
test -z "$IPADDR" && exit 1

IPV6ADDR="$(hcloud server ip -6 "$name")"
describe_json="$(hcloud server describe av -o json)"
HCLOUD_DATACENTER="$(   echo "$describe_json" | jq .datacenter.name -r)"
HCLOUD_DATACENTER="$(   echo "$describe_json" | jq .server_type.cores -r)"
HCLOUD_SERVER_CORES="$( echo "$describe_json" | jq .server_type.cores -r)"
HCLOUD_SERVER_MEMORY="$(echo "$describe_json" | jq .server_type.memory -r)"
HCLOUD_SERVER_DISK="$(  echo "$describe_json" | jq .server_type.disk -r)"


ssh-keygen -f ~/.ssh/known_hosts -R $IPADDR     # needed to make life easier later.
# StrictHostKeyChecking=no automatically adds new host keys and accepts changed host keys.
# maybe 'ssh -o UserKnownHostsFile=/dev/null' helps?

for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 last; do
  to=5
  test "$i" -gt 10 && to=15
  sleep $to
  echo -n .
  timeout $to ssh $ssh_opts root@$IPADDR uptime && break
  if [ $i = last ]; then
    echo "$0 ERROR: cannot ssh into machine at $IPADDR -- tried multiple times."
    set -x
    hcloud server describe -o json "$name" | jq .status
    exit 1
  fi
done

$verbose && echo "$IPADDR is ready."

# obtain dns names
for dns in $DNS_NAMES; do
  dns="${dns%.$HCLOUD_DNS_ZONE}"	# strip the zone name, if included.
  # create or update
  (set -x; hcloud zone rrset set-records --record $IPADDR $HCLOUD_DNS_ZONE $dns A)
done

# generate env.sh
env_sh="$(cat <<EOF
# generated by $0 $1
export IPADDR=$IPADDR
export IPV6ADDR=$IPV6ADDR
export NAME=$name
export FQDNS="$FQDNS"
export HCLOUD_DNS_ZONE=$HCLOUD_DNS_ZONE
export HCLOUD_IMAGE=$HCLOUD_IMAGE
export HCLOUD_TYPE=$HCLOUD_TYPE
export HCLOUD_DATACENTER=$HCLOUD_DATACENTER
export HCLOUD_SERVER_CORES=$HCLOUD_SERVER_CORES
export HCLOUD_SERVER_MEMORY=$HCLOUD_SERVER_MEMORY
export HCLOUD_SERVER_DISK=$HCLOUD_SERVER_DISK
EOF
)"

extra_pkg="screen git vim less certbot python3-certbot-apache apache2"

noclutter() { grep -E -v "^(Preparing to|Get:|Selecting previously unselected|Setting up|Creating config|Created symlink|Processing triggers|)"; }

if [ -n "$extra_pkg" ]; then
  case "$HCLOUD_IMAGE" in
    ubuntu*|debian*)
      ssh root@$IPADDR sh -x -s <<END | noclutter
        export LC_ALL=C
        export DEBIAN_FRONTEND=noninteractive
        apt-get update
        apt-get upgrade -y
        apt-get install -y $extra_pkg
END
        ;;
    fedora*|centos*)
      ssh root@$IPADDR sh -x -s <<END
        export LC_ALL=C
        yum install -y $extra_pkg
END
        ;;
    *) echo "$0 WARNING: platform installer not implemented for $HCLOUD_IMAGE. Skipping package installation of $extra_pkg"
        ;;
  esac
fi

# install a letsencrypt certificate
d_opts="$(echo \ $FQDNS | sed -e 's/\s\b/ -d /g')"
ssh root@$IPADDR certbot -m qa@jwqa.de --no-eff-email --agree-tos --redirect --apache --deploy-hooks $d_opts

# transfer and run the intialization script on the target host.
echo "$env_sh" | ssh root@$IPADDR "cat > env.sh"
scp $script root@$IPADDR:INIT.bashrc
ssh -t root@$IPADDR screen -m "bash -c 'source INIT.bashrc; exec bash'"

echo ""
echo "Hint: When you no longer need this server, you can remove it with:"
echo "	hcloud server delete $name"

