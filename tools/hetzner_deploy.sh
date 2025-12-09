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
	export HCLOUD_DNS_ZONE=...		# or derived from DNS_NAME, if that is an FQDN
	export DNS_NAME=...[-DATE]		# default: from script # DNS_NAME: ...
	export HCLOUD_TYPE=...			# default: from script # HCLOUD_TYPE: ... or '$default_hcloud_type'
	export HCLOUD_IMAGE=...			# default: from script # HCLOUD_IMAGE: ... or '$default_hcloud_image'
	export INIT_...				# all env variables starting with INIT_ are passed into env.sh

	$0 [init/]clamav.sh			# start a virus scanner machine
	$0 [init/gitlab.sh			# start a gitlab server

	hcloud server-type list			# study available server types
	hcloud image list  -a x86 | grep '\(debian\|ubuntu\)'	# study available images

	# eventually...
	hcloud server list
	hcloud server create-image --type snapshot SERVER_NAME --description "SERVERNAME-DATE"
	hcloud server delete SERVER_NAME; hetzner_dns del SERVER_NAME
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

if [ -z "$HCLOUD_SSHKEY_NAMES" ]; then
  echo 1>&2 "$0 ERROR: env variable HCLOUD_SSHKEY_NAMES is not set."
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
        export HCLOUD_DNS_ZONE="$z"
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

script="$1"	# TODO: handle multiple scripts and/or parameters...
test -f "$script.sh" && script="$script.sh"

if [ ! -f "$script" ]; then
  mydir="$(dirname "$(readlink -f "$0")")"
  # user may or may not include .sh suffix or init/ prefix in the script name.
  test -f "$mydir/$script"    && script="$mydir/$script"
  test -f "$mydir/$script.sh" && script="$mydir/$script.sh"
  test -f "$mydir/init/$script"    && script="$mydir/init/$script"
  test -f "$mydir/init/$script.sh" && script="$mydir/init/$script.sh"
fi
if [ ! -f "$script" ]; then
  echo 1>&2 "$0 ERROR: could not find $script"
  echo 1>&2 " -- also tried $script.sh and $mydir/[init/]$script[.sh]"
  exit 1
fi

$verbose && echo "using $(readlink -f $script)"

# extract some variables
test -z "$HCLOUD_IMAGE" && HCLOUD_IMAGE="$(sed -ne "s@^#\s*HCLOUD_IMAGE:\s*@@p" $script | sed -e 's@\s.*$@@')"
test -z "$HCLOUD_TYPE"  && HCLOUD_TYPE="$( sed -ne "s@^#\s*HCLOUD_TYPE:\s*@@p"  $script | sed -e 's@\s.*$@@')"
test -z "$DNS_NAMES"    && DNS_NAMES="$(   sed -ne "s@^#\s*DNS_NAME:\s*@@p" -e 's@\s.*$@@' $script)"
ENV_VARS_OPT="$(                           sed -ne "s@^#\s*ENV_VARS_OPT:\s*@@p" -e 's@\s*#.*$@@' $script)"

test -z "$HCLOUD_TYPE" && HCLOUD_TYPE=$default_hcloud_type
test -z "$HCLOUD_IMAGE" && HCLOUD_IMAGE=$default_hcloud_image
test -z "$dns_names" && dns_names=$(echo "$HCLOUD_IMAGE-DATE" | tr '._' '-')
DNS_NAMES="$(echo "$DNS_NAMES" | sed -e "s@DATE@$(date +%Y%m%d)@")"
set_name_and_check_zone "$(echo "$DNS_NAMES" | head -n1)"		# first element, if its a list.

FQDNS="$(echo "$DNS_NAMES" | sed -e "s/$/.$HCLOUD_DNS_ZONE/")"

ssh_key_opts=''
for key in $(echo "$HCLOUD_SSHKEY_NAMES" | tr ',' ' '); do
  ssh_key_opts="$ssh_key_opts --ssh-key $key"
done


origin_label="$(echo "orgin=$(basename $0) $1" | tr ' /:.,;+-' '_')"	# only alpanumeric and _, sigh

if [ -n "$(hcloud server ip "$name" 2>/dev/null)" ]; then
  echo 1>&2 "ERROR: a server named '$name' already exists."
  echo 1>&2 "	Specify a different DNS_NAME or try:"
  echo 1>&2 "	hcloud server delete $name"
  exit 1
fi

set -x
hcloud server create --type "$HCLOUD_TYPE" --label "$origin_label" $ssh_key_opts --image "$HCLOUD_IMAGE" --name "$name" || exit 1
set +x

ssh_opts="-o ConnectTimeout=10 -o CheckHostIP=no -o StrictHostKeyChecking=no -o PasswordAuthentication=no"

IPADDR="$(hcloud server ip "$name")"
test -z "$IPADDR" && exit 1

IPV6ADDR="$(hcloud server ip -6 "$name")"
# inspect server metadata, with a little retry, in case we get "hcloud: (server error)"
describe_json="$(hcloud server describe "$name" -o json || { echo 1>&2 "retrying hcloud describe ..."; sleep 3;  hcloud server describe "$name" -o json; } )"
HCLOUD_DATACENTER="$(   echo "$describe_json" | jq .datacenter.name -r)"
HCLOUD_SERVER_CORES="$( echo "$describe_json" | jq .server_type.cores -r)"
HCLOUD_SERVER_MEMORY="$(echo "$describe_json" | jq .server_type.memory -r)"
HCLOUD_SERVER_DISK="$(  echo "$describe_json" | jq .server_type.disk -r)"

# prepare dns names as early as possible
for dns in $DNS_NAMES; do
  dns="${dns%.$HCLOUD_DNS_ZONE}"	# strip the zone name, if included.
  # create or update
  (set -x; hcloud zone rrset set-records --record $IPADDR $HCLOUD_DNS_ZONE $dns A)
done

ssh-keygen -f ~/.ssh/known_hosts -R $IPADDR     # needed to make life easier later.
# StrictHostKeyChecking=no automatically adds new host keys and accepts changed host keys.
# maybe 'ssh -o UserKnownHostsFile=/dev/null' helps?

# It may take a while, until the server is ready for ssh connections. Poll that.
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

export DNS_NAME="$(echo "$FQDNS" | head -n1)"	# first of all names, if multiple

# generate env.sh
env_sh="$(cat <<EOF
# generated by $0 $1
export IPADDR=$IPADDR
export IPV6ADDR=$IPV6ADDR
export NAME=$name
export FQDNS="$FQDNS"
export DNS_NAME=$DNS_NAME
export HCLOUD_DNS_ZONE=$HCLOUD_DNS_ZONE
export HCLOUD_IMAGE=$HCLOUD_IMAGE
export HCLOUD_TYPE=$HCLOUD_TYPE
export HCLOUD_DATACENTER=$HCLOUD_DATACENTER
export HCLOUD_SERVER_CORES=$HCLOUD_SERVER_CORES
export HCLOUD_SERVER_MEMORY=$HCLOUD_SERVER_MEMORY
export HCLOUD_SERVER_DISK=$HCLOUD_SERVER_DISK
EOF
)"

for var in $(echo "$ENV_VARS_OPT" | tr ',' ' '); do
  if  [ -n "${!var}" ]; then
    echo 1>&2 "ENV_VARS_OPT: importing $var"
    env_sh="$env_sh
export $var=\"${!var}\""
  fi
done


extra_pkg="screen git vim less curl wget certbot python3-certbot-apache apache2 xtail"

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
    *) echo 1>&2 "$0 WARNING: platform installer not implemented for $HCLOUD_IMAGE. Skipping package installation of $extra_pkg"
        ;;
  esac
fi

# enable apache ssl, so that certbot can install a cert
ssh -t root@$IPADDR bash -x -c "'a2enmod ssl setenvif; a2ensite default-ssl; systemctl restart apache2'"

# infuse all dns names into the default-ssl.conf so that certbot does not ask questions.
ssh root@$IPADDR sed -i "'/<VirtualHost /a\		ServerAlias $(echo $FQDNS)'" /etc/apache2/sites-available/default-ssl.conf
ssh root@$IPADDR sed -i "'/<VirtualHost /a\		ServerName $DNS_NAME'" /etc/apache2/sites-available/default-ssl.conf

le_backup="le-backup-$(echo "$DNS_NAME" | tr . -).tar.gz"
if [ -z "$(find . -maxdepth 1 -type f -name "$le_backup" -mtime -2)" ]; then
   # we need a fresh certificate

   ## THIS DOES NOT WORK: certbot choooses a new name ...0001.conf, if that conf alread exists.
   ## prepare renewal config, so that certbot won't ask questions.
   ## The name of the config derives from the first domain. That is what certbot does, we do that too.
   # cat <<EOF | ssh root@$IPADDR "cat > '/etc/letsencrypt/renewal/$DNS_NAME.conf'"
   # [renewalparams]
   # installer = apache
   # apache_vhost_config = /etc/apache2/sites-available/default-ssl.conf
   # EOF

   # install a letsencrypt certificate (with retry, DNS may not yet be ready...)
   # TODO: this install only works partially, when we have multiple domains in d_opts.
   d_opts="$(echo \ $FQDNS | sed -e 's/\s\b/ -d /g')"
   certbot_opts="--non-interactive -m qa@jwqa.de --no-eff-email --agree-tos --redirect --apache $d_opts"
   echo "+ certbot $certbot_opts"
   ssh root@$IPADDR certbot $certbot_opts || {
     echo "Oh, certbot failed?, let's wait 30sec and try again"
     sleep 5; echo .; sleep 5; echo .; sleep 5; echo .; sleep 5; echo .; sleep 5; echo .; sleep 5
     ssh root@$IPADDR certbot $certbot_opts || {
       echo "Oh, certbot failed again?, let's try with certonly, without installing into apache"
       ssh root@$IPADDR certbot certonly $certbot_opts
     }
   }

   # save the certificate for re-use...
   ssh root@$IPADDR tar zcf - /etc/letsencrypt > $le_backup
else
   # we have a saved certificate for this name that we want to use.
   echo "Restoring cert from $le_backup ..."
   ssh root@$IPADDR tar zxf - -C / < $le_backup
   ssh root@$IPADDR "certbot certificates; certbot --apache install --cert-name $DNS_NAME; systemctl reload apache2"
fi

# transfer and run the intialization script on the target host.
echo "$env_sh" | ssh root@$IPADDR "cat > env.sh"
ssh root@$IPADDR "echo 'source env.sh' >> .bashrc"
scp $script root@$IPADDR:INIT.bashrc
asset_dir="$(echo $script | sed -e 's/\.sh//')"
if [ -d "$asset_dir" ]; then
  ssh root@$IPADDR "mkdir init"
  scp -r $asset_dir root@$IPADDR:init
fi
ssh -t root@$IPADDR screen -L -m "bash -c 'source INIT.bashrc; exec bash'"

echo ""
echo "Hint: When you no longer need this server, you can remove it with:"
echo "	hcloud server delete $name"
