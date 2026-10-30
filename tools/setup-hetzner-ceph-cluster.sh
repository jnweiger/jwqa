# !/bin/sh
#
# use hetzner-deploy to prepare hosts for a simple cluster.
# then use Roberts ansible to roll out a cluster.

set -e	# exit, when there is an error.

osd_host_vol_size_gb=20
osds_per_host=4
osd_host_count=4
domain=$HCLOUD_DNS_ZONE
osdhosts=$(echo $(seq 0 $(($osd_host_count - 1)) | sed -e 's/^/ceph/'))
cephhosts="$osdhosts"	# and others ??
cephchef=cephchef	# the user we bootstrap with.

vg_perc=$((100 / $osds_per_host))
diskids=$(echo $(seq $osds_per_host))	# all in one line...

for host in $osdhosts; do
  hetzner_deploy -n $host -v -d debian
  # forget any old host keys, if any. We know, the host is a new one, ...
  ssh-keygen -R $host.$domain -f ~/.ssh/known_hosts
  # and store the now one...
  ssh -o 'StrictHostKeyChecking=accept-new' root@$host.$domain hostname
  # FIXME: both of the above should be done by hetzner_deploy

  # create one volume per host
  hcloud volume describe --quiet $host-osd 2>/dev/null || hcloud volume create --name $host-osd --server $host --size $osd_host_vol_size_gb
  # find the volume device name
  osddisk=$(ssh root@$host.$domain lsblk -r -p -o NAME -n -Q 'SIZE==20G')
  # make one lvm for each osd on the device, if fmissing.
  ssh root@$host.$domain "test -z \"\$(wipefs -n $osddisk)\" && pvcreate $osddisk && vgcreate osd-vg $osddisk && for id in $diskids; do (set -x; lvcreate -l $vg_perc%VG -n data-\$id osd-vg); done; vgchange -ay osd-vg; lsblk -lp $osddisk"
done

KEYDIR="/tmp/ceph-tmp-$$"
mkdir -p "$KEYDIR"
ssh-keygen -t ed25519 -f "$KEYDIR/id_ed25519" -N "" -C "ceph-temp-$$"
for host in $cephhosts; do
  scp -r $KEYDIR/* root@$host.$domain:.ssh/
  ## create user cephchef with sudo and one ssh-key all across the cluster.
  # ssh root@$host.$domain deluser --remove-home $cephchef
  ssh root@$host.$domain "adduser --disabled-password --gecos 'Ceph Chef,,,' $cephchef"
  # inherit .ssh from root user, but also add our own id_ed25519.pub to our authorized_keys
  ssh root@$host.$domain "cp -a /root/.ssh ~$cephchef/; chown -R $cephchef:$cephchef ~$cephchef/.ssh; cat ~$cephchef/.ssh/*.pub >> ~$cephchef/.ssh/authorized_keys"
  # allow passwordless sudo
  ssh root@$host.$domain "echo 'cephchef ALL=(ALL:ALL) NOPASSWD:ALL' > /etc/sudoers.d/cephchef"
done
rm -rf $KEYDIR


if [ ! -d ceph-deployment-jw ]; then
  git clone --recursive git@gitlab.heinlein-support.de:ansible-playbooks/general-ceph-deployment.git ceph-deployment-jw
fi

cd ceph-deployment-jw
python3 -m venv ./venv
. ./venv/bin/activate
pip3 install -U -r requirements.txt
pip3 install --upgrade pip

ansible-galaxy collection install -U -r requirements-galaxy.yml

## configure variables according to the README

## CEPHINSTALL.md says

# TODO:
# irgendwas am inventory.ini unten rausnehmen, damit

ansible all -i inventory.ini -m ping


# Start with 
ansible-playbook -D registry-caches.yaml	# ohne -k -K sosnt fragt der nach passwoertern zu einem unbekannten user.

# Run ansible-playbook-k -K  -D create-apache-proxy.yaml when using the Apache reverse proxy.

# Then run ansible-playbook -k -K -D checkmk-server.yaml. You need to have SSH root access to the monstack host.

# In the end run ansible-playbook -k -K -D new-host.yaml.
# On the admin host (first mon)

# Bootstrap the Ceph cluster with ./ceph-bootstrap.sh.
# On the mgmt host

# Run ansible-playbook -k -K -D deploy-ceph-sshpub.yaml to deploy the generated SSH public key to all nodes.
# ansible-playbook -k -K -D registry-caches.yaml
# ansible-playbook -k -K -D new-host.yaml.
