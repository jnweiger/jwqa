#! /bin/bash

## HCLOUD_TYPE:  cpx11		# cpx11 2GB, cpx21 4GB, cpx41 8G
# HCLOUD_IMAGE: debian-13

source env.sh
set -- $ARGS

export LC_ALL=C
export DEBIAN_FRONTEND=noninteractive
apt install -y apt-file
(set -x; apt-file update 2>&1 >/dev/null) 	# so that we can use: apt-file search ....
(set -x; apt upgrade -y)

echo
echo "ARGS: $ARGS"

mkdir -p /mnt/loop
(set -x; dd if=/dev/zero of=/mnt/loop/loop0.img bs=1G count=12)
losetup /dev/loop0 /mnt/loop/loop0.img
pvcreate /dev/loop0
vgcreate loop-vg /dev/loop0
for id in 0 1 2 3; do
  lvcreate -l 25%VG -n data-$id loop-vg
done
lsblk /dev/loop0
vgchange -ay loop-vg	# make /dev/loop-vg/data-* appear.
(set -x; lvs -o vg_name,lv_name,lv_path)

