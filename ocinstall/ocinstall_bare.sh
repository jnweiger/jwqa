#! /bin/bash
#
# This runs the minimal OpenCloud install script with a pre-defined dns name.
# and a certificate.
#
# Assumptions:
# - we run as root.
# - port 443 is unused.
# - DNS entry exists.
#
# (C) 2025 j.weigert@heinlein-support.de - distribute under MIT License.
#
# 2025-06-24, v1.0 jw  - initial draught
# 2025-06-30, v1.1 jw  - more flexiility with certificates and natted IP addresses
# 2025-09-06, v1.2 jw  - fixed dns response 127.0.1.1
#

set -e

if [ -z "$1" -o "$1" = "-h" -o "$1" = "--help" ]; then
  cat <<EOF

Usage:
  $0 DNSNAME

  Where DNSNAME should exist and point to this host.

Environment variables used:
  export OC_BASE_DIR=/opt/oc    # To set \$OC_BASE_DIR/data and \$OC_BASE_DIR/config as data and configuration directories.
                                # Default: \$HOME/oc-run
  export OC_CERT_DIR=/var/snap/.../certs/certbot/config/
                                # Location of the files fullchain.pem and privkey.pem
                                # /live/ or /live/DNSNAME are appended if the folders exists.
                                # Default: /etc/letsencrypt
  export OC_VERSION=3.0.0	# Default: 3.4.0, see https://docs.opencloud.eu/docs/admin/resources/lifecycle

Simple example:
  $0 oc.jwqa.de    # from within a newly started machine with DNS name oc.jwqa.de

Detailled example:
  https://console.hetzner.cloud -> click PROJECTNAME -> Server -> Add Server
  https://dns.hetzner.com -> click ZONENAME -> Add record -> Name oc.jwqa.de
  scp ./ocinstall_bare.sh oc.jwqa.de:
  ssh root@oc.jwqa.de bash ./ocinstall_bare.sh oc.jwqa.de

EOF
  exit 1
fi

github_url="https://github.com/opencloud-eu/opencloud"

dnsname=$1
# oc.jwqa.de has address 65.21.178.225
dns_ip=$(host -4 "$dnsname" | sed -e 's/.* //')
# 65.21.178.225 2a01:4f9:c012:dd1d::1
# this is unreliable, it may just say 127.0.X.1, in this cas ask an authorative name server
case "$dns_ip" in
  127.* )
    # host -d includes the SOA record, which has a nameserver next to the word SOA. E.g.
    # jwqa.de. 3295 IN SOA hydrogen.ns.hetzner.com. dns.hetzner.com. 2025090701 86400 10800 3600000 3600
    ns=$(host -d oc.jwqa.de | sed -ne 's/.*\sSOA\s*//p' | sed -e 's/\.\?\s.*//')
    echo "... using DNS server: $ns"
    dns_ip=$(host -4 "$dnsname" "$ns" | sed -ne 's/.*\shas address\s//p')
    ;;
esac


my_ip=$(hostname -I | sed -e 's/ .*//')

if [ "$dns_ip" != "$my_ip" ]; then
  echo "WARNING: dns name $dnsname resolves to $dns_ip, but this host is $my_ip"
  echo "         Press ENTER to continue, CTRL-C to abort"
  read a
fi

export OC_HOST="$dnsname"
test -z "$OC_VERSION"  && export OC_VERSION=3.4.0
test -z "$OC_BASE_DIR" && export OC_BASE_DIR=$HOME/oc-run
mkdir -p "$OC_BASE_DIR"		# make sure the directory exists.

if [ ! -z "$OC_CERT_DIR" ]; then

  # make OC_CERT_DIR work with /live, /live/$dnsname suffix, or without.
  test -d "$OC_CERT_DIR/live" && exort OC_CERT_DIR="$OC_CERT_DIR/live"
  test -d "$OC_CERT_DIR/$dnsname" && exort OC_CERT_DIR="$OC_CERT_DIR/$dnsname"

  export PROXY_TRANSPORT_TLS_CERT="$OC_CERT_DIR/fullchain.pem"
  export PROXY_TRANSPORT_TLS_KEY="$OC_CERT_DIR/privkey.pem"

else

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

  echo sleep 10
  sleep 10
fi

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
