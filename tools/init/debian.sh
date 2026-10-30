#! /bin/bash

## HCLOUD_TYPE:  cpx11		# cpx11 2GB, cpx21 4GB, cpx41 8G
# HCLOUD_IMAGE: debian-13

source env.sh
set -- $ARGS

export LC_ALL=C
export DEBIAN_FRONTEND=noninteractive
apt install -y apt-file				# is that obsoleted by apt search ... ???
(set -x; apt-file update 2>&1 >/dev/null) 	# so that we can use: apt-file search ....
(set -x; apt upgrade -y)

if [ -n "$HCLOUD_DNS_ZONE" ]; then
  # add a search domain to resolv.conf, so that short hostnames work. 
  # resolvconf -u also makes 'hostname --fqdn' work. WOW. (domainname does not.)
  domainname "$HCLOUD_DNS_ZONE"
  echo search "$HCLOUD_DNS_ZONE" >> /etc/resolvconf/resolv.conf.d/base
  resolvconf -u
fi

echo
echo "ARGS: $ARGS"

