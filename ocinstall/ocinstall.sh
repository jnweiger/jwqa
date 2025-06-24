#! /bin/bash
#
# This runs the minimal install script with a pre-defined dns name.
# and a certificate.
#
# Assumptions:
# - port 443 is currently unused.
# - DNS entry exists.


if [ -z "$1" -o "$1" = "-h" -o "$1" = "--help" ]; then
  cat <<EOF

Usage: 
  $0 DNSNAME

  Where DNSNAME should exist and point to this host.

  Environment variables used:
  export OC_BASE_DIR=/opt/oc	# Default: \$HOME/oc-run
  	to set /opt/oc/data and /opt/oc/config as the persisted data and config directories.
  export OC_VERSION=2.0.0	# Default: 3.0.0

  Example: $0 oc.jwqa.de
EOF
  exit 1
fi

github_url="https://github.com/opencloud-eu/opencloud"

dnsname=$1
# oc.jwqa.de has address 65.21.178.225
dns_ip=$(host -4 "$dnsname" | sed -e 's/.* //')
# 65.21.178.225 2a01:4f9:c012:dd1d::1 
my_ip=$(hostname -I | sed -e 's/ .*//')

if [ "$dns_ip" != "$my_ip" ]; then
  echo "ERROR: dns name $dnsname resolves to $dns_ip, but this host is $my_ip"
  exit 2
fi

export OC_HOST="$dnsname"
test -z "$OC_VERSION"  && export OC_VERSION=3.0.0
test -z "$OC_BASE_DIR" && export OC_BASE_DIR=$HOME/oc-run
mkdir -p "$OC_BASE_DIR"		# make sure the directory exists.

if [ ! -d "/etc/letsencrypt/live/$dnsname" ]; then
  type certbot || (apt update; apt install certbot)
  # get a certificate into the ./cert folder.
  ## TODO: assert that no webserver is running "here".
  certbot certonly --standalone -d "$dnsname" --email "cert@$dnsname" --agree-tos --non-interactive
fi

# Successfully received certificate.
# Certificate is saved at: /etc/letsencrypt/live/oc.jwqa.de/fullchain.pem
# Key is saved at:         /etc/letsencrypt/live/oc.jwqa.de/privkey.pem

## documented with OCIS. it may still work with opencloud?
export PROXY_TRANSPORT_TLS_CERT="/etc/letsencrypt/live/$dnsname/fullchain.pem"
export PROXY_TRANSPORT_TLS_KEY="/etc/letsencrypt/live/$dnsname/privkey.pem"

test -d opencloud || git clone --depth 1 "$github_url"
(cd opencloud; git pull --rebase)

init_sh="$(pwd)/opencloud/deployments/examples/bare-metal-simple/install.sh"

cd "$OC_BASE_DIR"	# so that the sandbox ends up in the oc-run folder.

if [ ! -f "$init_sh" ]; then
  echo "OOPS: $init_sh not found in checkout of $github_url"
  exit 3
fi

bash "$init_sh" &
sleep 5


sandboxdir="$(ls -drt opencloud-sandbox-* | tail -1)"
oc_bin="$(cd "$sandboxdir"; ls opencloud-* | tail -1)"

cat <<EOF>ocstop.sh
killall $oc_bin
EOF

cat <<EOF>ocstart.sh
#!/bin/bash
SCRIPT_DIR="\$(dirname "\$(readlink -f "\${0}")")"
set -x

export PROXY_TRANSPORT_TLS_CERT="/etc/letsencrypt/live/$dnsname/fullchain.pem"
export PROXY_TRANSPORT_TLS_KEY="/etc/letsencrypt/live/$dnsname/privkey.pem"

\$SCRIPT_DIR/$sandboxdir/runopencloud.sh & 
EOF

chmod a+x ocstart.sh ocstop.sh
