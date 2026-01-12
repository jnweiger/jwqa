#! /bin/bash

## HCLOUD_TYPE:  cpx11		# cpx11 2GB, cpx21 4GB, cpx41 8G
# HCLOUD_IMAGE: debian-13

source env.sh
set -- $ARGS

export LC_ALL=C
export DEBIAN_FRONTEND=noninteractive
apt install -y apt-file
apt-file update	# so that we can use: apt-file search ....
