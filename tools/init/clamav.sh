#! /bin/bash
#
# DNS_NAME:     av
# DNS_NAME:     icap
# HCLOUD_IMAGE: ubuntu-22.04
# HCLOUD_TYPE:  cpx21		# cpx11 2GB, cpx21 4GB, cpx41 8G
#

source env.sh	# not really needed here.

export LC_ALL=C
export DEBIAN_FRONTEND=noninteractive
apt install -y git screen podman-docker xtail

topdir=$(pwd -P)
mkdir -p $topdir/log/c-icap
mkdir -p $topdir/log/clamav
chmod -R 777 $topdir/log

# pull and build only when needed.
test -d container-clamav-icap || git clone https://github.com/opencloud-eu/container-clamav-icap.git
cd container-clamav-icap
test -z "$(docker images -q clamav-c-icap)" && docker build -t clamav-c-icap .

# we expect, that we already run inside a screen session... if not, we create a screen session.
# use a trailing exec bash to enforce zombie mode
# use -ti so that CTRL-C can be used.
screen bash -x -c "docker run -ti --name clamav-icap --replace -p 11344:1344 -v $topdir/log:/var/log localhost/clamav-c-icap; exec bash"

# if we are indeed inside a screen session, then show logs in the other window.
# otherwise the screen command above would block this shell. Running commands afterwards would be confusing.
if [ -n "$STY" ]; then
  sleep 6
  screen -X select 0	# screen shows the docker startup, switch back to "this shell"
  (set -x; xtail $topdir/log/clamav/{clamav,freshclam}.log $topdir/log/c-icap/{access,server}.log)
fi

