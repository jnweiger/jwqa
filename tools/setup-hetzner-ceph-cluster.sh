# !/bin/bash
#
# use hetzner-deploy to prepare hosts for a simple cluster.
# then use Roberts ansible to roll out a cluster.

set -e	# exit, when there is an error.

osd_host_vol_size_gb=20
osds_per_host=4
osd_host_count=4
domain=$HCLOUD_DNS_ZONE
nameprefix=${CEPH_NAME_PREFIX:-ceph}
osdhosts="$(echo $(seq 1 $osd_host_count | sed -e "s/^/$nameprefix/"))"
adminhost=${nameprefix}0
allhosts="$adminhost $osdhosts"
checkmkhost=$adminhost		# currently not used.
cephchef=cephchef		# the user we bootstrap with.
gen_label=2026

hcloud_network_zone="eu-central"				# eu-central includes hel, nbg, fsn, ...
ansible_dir_name=ceph-deployment-hcloud-$nameprefix		# a local directory, where checkout and patch ansible files

mon_host_count=5
if [ $mon_host_count -gt $osd_host_count ]; then
  mon_host_count=3
fi

monhosts=""
for mon in $(seq 0 $(($mon_host_count - 1))); do
  monhosts="$monhosts$nameprefix$mon
"
done

mgr_host_count=3
mgrhosts=""
for mgr in $(seq 0 $(($mgr_host_count - 1))); do
  mgrhosts="$mgrhosts$nameprefix$mgr
"
done

sshr ()
{
  # an ssh wrapper with retry, in case dns fails.
  # that happens, when recreating a host with the same dns name, but hetzner chooeses a new ip address and our local dns is behind.
  # Assumption: first parameter has username@hostname
  sshlog=/tmp/ssh-err.$$.log
  rm -f $sshlog

  echo "|+ ssh $@" 1>&2
  ssh -v -o ConnectionAttempts=3 -o ConnectTimeout=10 -E $sshlog "$@"
  if [ -s "$sshlog" ]; then
    cat $sshlog 1>&2
  fi
  if grep -q ': Connection timed out' $sshlog; then
    servername=$(echo "$1" | sed -ne 's/.*@//p')
    username=$(echo "$1" | sed -ne 's/@.*//p')
    if [ -z "$servername" ]; then
      echo "sshr retry ERROR: could not find a servername in first parameter: $1" 1>&2
      exit 2
    fi
    # try with full servername (fqdn?)
    ipaddr=$(hcloud server describe $servername -o json 2>/dev/null| jq -r .public_net.ipv4.ip)
    if [ -z "$ipaddr" ]; then
      # retry with short name
      shortname=$(echo "$servername" | sed -e 's/\..*//')
      ipaddr=$(hcloud server describe $shortname -o json 2>/dev/null| jq -r .public_net.ipv4.ip)
    fi
    if [ -z "$ipaddr" ]; then
      echo "sshr retry ERROR: could could get ipaddr for $servername or $shortname from hcloud." 1>&2
      exit 3
    fi
    shift
    echo "|++ ssh $username@$ipaddr $@" 1>&2
    ssh -o ConnectionAttempts=5 $username@$ipaddr "$@"
  fi
  rm -f $sshlog
}

ssh_admin()
{
  sshr root@$adminhost.$domain "$@"
}

wait_for_progress()
{
  limit="$1"
  test -z "$limit" && limit=200		# ca. 20 minutes
  for i in $(seq $limit); do
    sleep 5
    progress="$(ssh_admin ceph -s --format json | jq .progress_events)"
    if [ "$progress" == "{}" ]; then
      break
    fi
    echo "$progress" | grep message
  done
  ssh_admin ceph -s
}


echo "Creating hcloud server: $allhosts ..."
# check that the names are free
existing_hosts="$(echo $(hcloud server list -o noheader -o columns=name))"
for host in $allhosts; do
  case " $existing_hosts " in
    *" $host "*)
      echo "ERROR: '$host' already exists. Please check hcloud server list / export CEPH_NAME_PREFIX=..." 1>&2
      exit 1
      ;;
  esac
done


for host in $allhosts; do
  hetzner_deploy -n $host -v -d debian
  # forget any old host keys, if any. We know, the host is a new one, ...
  ssh-keygen -R $host.$domain -f ~/.ssh/known_hosts
  # and store the now one...
  realhost=$(ssh -o ConnectTimeout=10 -o 'StrictHostKeyChecking=accept-new' root@$host.$domain hostname || true)
  if [ -n "$realhost" -a "$realhost" != "$host" -a "$realhost" != "$host.$domain" ]; then
    echo "ERROR: hostname mismatch. Do we have DNS confusion? $realhost != $host"
    echo "Presse ENTER to continue, CTRL-C to abort."
    read a
  fi
  # FIXME: both of the above should be done by hetzner_deploy
done

for host in $osdhosts; do
  # create one volume per host
  hcloud volume describe --quiet $host-osd 2>/dev/null || hcloud volume create --name $host-osd --server $host --size $osd_host_vol_size_gb
  ### dont do that here: ceph orch wants to see the physical disk and create its own lvm setup, see below with osds_per_device: 4
  ## find the volume device name
  # osddisk=$(ssh root@$host.$domain lsblk -r -p -o NAME -n -Q 'SIZE==20G')
  # vg_perc=$((100 / $osds_per_host))
  # diskids=$(echo $(seq $osds_per_host))	# all in one line...
  # # make one lvm for each osd on the device, if fmissing.
  # ssh root@$host.$domain "test -z \"\$(wipefs -n $osddisk)\" && pvcreate $osddisk && vgcreate osd-vg $osddisk && for id in $diskids; do (set -x; lvcreate -l $vg_perc%VG -n data-\$id osd-vg); done; vgchange -ay osd-vg; lsblk -lp $osddisk"
done

# prepare cephchef user
KEYDIR="/tmp/ceph-tmp-$$"
mkdir -p "$KEYDIR"
ssh-keygen -t ed25519 -f "$KEYDIR/id_ed25519" -N "" -C "ceph-temp-$$"
for host in $allhosts; do
  for file in $KEYDIR/*; do
    cat $file | sshr root@$host.$domain tee .ssh/$(basename $file)
    # do not use scp, we don't have a wrapper for broken dns.
  done
  sshr root@$host.$domain chmod 600 .ssh/id_ed25519 || true	# guessing the name...
  ## create user cephchef with sudo and one ssh-key all across the cluster.
  sshr root@$host.$domain deluser --remove-home $cephchef || true
  sshr root@$host.$domain "adduser --disabled-password --gecos 'Ceph Chef,,,' $cephchef"
  # inherit .ssh from root user, but also add our own id_ed25519.pub to our authorized_keys
  sshr root@$host.$domain "cp -a /root/.ssh ~$cephchef/; chown -R $cephchef:$cephchef ~$cephchef/.ssh; cat ~$cephchef/.ssh/*.pub >> ~$cephchef/.ssh/authorized_keys"
  # allow passwordless sudo
  sshr root@$host.$domain "echo 'cephchef ALL=(ALL:ALL) NOPASSWD:ALL' > /etc/sudoers.d/cephchef"
done
rm -rf $KEYDIR

ssh_admin "for i in 1 2 3 4; do ssh -o 'StrictHostKeyChecking=accept-new' $nameprefix\$i hostname; done"	# accept the host keys...


if [ ! -d $ansible_dir_name ]; then
  git clone --recursive git@gitlab.heinlein-support.de:ansible-playbooks/general-ceph-deployment.git $ansible_dir_name
fi

cd $ansible_dir_name
echo "ansible working directory:"
pwd -P

python3 -m venv ./venv
. ./venv/bin/activate
pip3 install -U -r requirements.txt
pip3 install --upgrade pip

ansible-galaxy collection install -U -r requirements-galaxy.yml

# prepare cluster network and dns mapping
# hetzner per default assigns wild ip addresses. ceph prefers a common subnet for the the cluster.
hex1="$(echo $nameprefix | md5sum | sed -e 's/\(..\).*/\1/')"		# a byte
hex2="$(echo $nameprefix | md5sum | sed -e 's/..\(.\).*/\1/')0"		# and a high nibble.
net_cidr="10.$((16#$hex1)).$((16#$hex2)).0/20"			# leaving 12bit -> 4000 hosts...
net_name="$nameprefix-cluster"
hcloud network create -o json --name $net_name --ip-range $net_cidr
subnet_cidr=$(echo $net_cidr | sed -e 's@/20@/24@')
subnet_prefix=$(echo $subnet_cidr | sed -e 's@\.0/24$@.@')

hcloud network add-subnet $net_name --type server --network-zone $hcloud_network_zone --ip-range $subnet_cidr

etc_hosts_block=""
for host in $allhosts; do
  echo > host_vars/$host.yaml "ansible_host: $host.$domain"

  #  attach to the network, this takes a while
  hcloud server attach-to-network --network $net_name $host
  # find the interface name, this appears to be racy, as we just maniplated networks. better wait a bit.
  # sshr just exits with exit code 1, without printing anything when it fails here. No retry, nothing seems to trigger.
  sleep 2; echo .
  sleep 2; echo .
  sleep 2; echo .
  net_match=$(sshr root@$host.$domain ip -4 -o addr show | grep -s $subnet_prefix)
  interface=$(echo $net_match | sed -e 's@\S\S*\s\(\S\S*\).*@\1@')
  ipaddr=$(echo $net_match | sed -e 's@.*\sinet\s\([0-9\.]*\).*@\1@')
  echo >> host_vars/$host.yaml "ceph_public_interface=$interface"
  etc_hosts_block="$etc_hosts_block$ipaddr $host
"
done

echo "$etc_hosts_block" | ssh_admin "tee -a /etc/hosts"	# make sure, DNS knows them all by their cluster subnet addr.

# prepare inventory.ini
# to enable ssh we need to add to [all:vars]
# this does not work with delegate_to. we need explicit entries in hosts_var/ceph[0-3].yaml
# ansible_host="{{ inventory_hostname }}.jwqa.de"
# we probably don't need a registry...??
# configure_registry_proxies=false
# should we enable configure_etc_hosts ??? what does it do?
# we don't have an eth1. should we switch it to eth0 or leave it undefined?
# ceph_cluster_interface=eth0
# what are the mgmt_networks ?? The default is certainly wrong. we cannot comment that out:
##
# TASK [Add chrony configuration] *****************************************************************
# [ERROR]: Task failed: 'mgmt_networks' is undefined
#
# Task failed.
# Origin: .../ceph-deployment-jw/create-chrony.yaml:52:11
##
# I don't have an http_proxy, let's comment that out.

cat <<EOF >inventory.ini
[all:vars]
ansible_user=$cephchef

ceph_version=20.2.3
cephadm_ssh_user=cephadm

configure_etc_hosts=true

configure_podman_proxy=false
configure_registry_proxies=false
configure_internal_registry=false

configure_bootstrapping_script=true

inet_family=ipv4
mgr_dashboard_interface=eth0

configure_chrony=true
chrony_sources=0.de.pool.ntp.org 1.de.pool.ntp.org 2.de.pool.ntp.org

mgmt_networks=10.128.8.0/22 192.168.102.0/23 10.0.32.0/19

configure_checkmk=false
checkmk_server_url=https://$checkmkhost.$domain
checkmk_agent_site=cephmon
checkmk_server_version=2.5.0p10
checkmk_server_edition=community

configure_cacert=true
configure_apache=false
configure_haproxy=false

# http_proxy=http://proxy.example.com:3128

registry_directory=/var/spool/registry-cache

configure_apt_sources=true

configure_vlans=false
configure_firewall=false

create_acl_cronjob=false

# Registry Server
[registry]
$adminhost

[monstack]
$adminhost

[ceph:children]
adminnode
monnodes
mgrnodes
osdnodes
monstack

# Host to run cephadm bootstrap on
[adminnode]
$adminhost

[monnodes]
$monhosts

[mgrnodes]
$mgrhosts

[osdnodes:children]
osd$gen_label

[osd$gen_label:vars]
ceph_label_osd="osd$gen_label"

[osd$gen_label]
$(echo $osdhosts | tr ' ' \\n)
EOF

ansible all -v -i inventory.ini -m ping


## Seems it is okay to skip this registry-caches.yaml (I have configure_registry_proxies=false)

## configure variables according to the README
## CEPHINSTALL.md says

# Start with
# ansible-playbook -D registry-caches.yaml	# ohne -k -K sosnt fragt der nach passwoertern zu einem unbekannten user.

# Run ansible-playbook-k -K  -D create-apache-proxy.yaml when using the Apache reverse proxy.

# Then run ansible-playbook -k -K -D checkmk-server.yaml. You need to have SSH root access to the monstack host.

# In the end run ansible-playbook -k -K -D new-host.yaml.
ansible-playbook -D new-host.yaml

# On the admin host (first mon)

# we need a uniform public network. On $adminhost, add the pulic network to the ceph-initial.conf
# [global]
# public_network=10.66.0.0/16

ssh_admin "sed -i ceph-initial.conf -e 's@\[global\]@[global]\npublic_network=$subnet_cidr@'"


## we need --skip-mon-network to avoid an error due to the strange /32 interfaces.:
# ./ceph-bootstap.sh explodes with:
# Host looks OK
# Cluster fsid: b77eec00-d69a-11f1-ba6a-92000a584708
# Verifying IP 10.66.1.4 port 3300 ...
# Verifying IP 10.66.1.4 port 6789 ...
# The public CIDR network 10.66.0.0/16 (from -c conf file) is not configured locally.
# Error: None of the public CIDR network(s) {'10.66.0.0/16'} (from -c conf file) is configured locally.
#
#
#         ***************
#         Cephadm hit an issue during cluster installation. Current cluster files will be deleted automatically.
#         To disable this behaviour you can pass the --no-cleanup-on-failure flag. In case of any previous
#         broken installation, users must use the following command to completely delete the broken cluster:
#
#         > cephadm rm-cluster --force --zap-osds --fsid <fsid>
#
#         for more information please refer to https://docs.ceph.com/en/latest/cephadm/operations/#purging-a-cluster
#         ***************
#
#
# Deleting cluster with fsid: b77eec00-d69a-11f1-ba6a-92000a584708
# ERROR: None of the public CIDR network(s) {'10.66.0.0/16'} (from -c conf file) is configured locally.
#
# Bootstrap the Ceph cluster with ./ceph-bootstrap.sh.

ssh_admin ./ceph-bootstap.sh --skip-mon-network

wait_for_progress

cat <<EOF | ssh_admin tee mon.yml
service_type: mon
service_name: mon
placement:
  count: $mon_host_count
  label: mon
EOF

# On the mgmt host

ansible-playbook -D deploy-ceph-sshpub.yaml

ssh_admin ceph orch host ls
# there is still only one host in the cluster. one mon to start with.
ssh_admin ceph orch host label add $adminhost mon
ssh_admin ceph orch apply -i mon.yml

wait_for_progress

# to add the remaining hosts to the cluster and add labels:
ansible-playbook -D add-ceph-hosts.yaml

wait_for_progress

## balancer settings
## done in ceph-initial.conf
# ssh_admin ceph config set mgr mgr/balancer/begin_weekday 1
# ssh_admin ceph config set mgr mgr/balancer/end_weekday 5
# ssh_admin ceph config set mgr target_max_misplaced_ratio 0.005
# ssh_admin ceph config set mgr mgr/balancer/upmap_max_deviation 1

## mgr: we may already have n active mgr by by now. but let's give it our prepared spec.
# ceph orch ps --daemon-type mgr --refresh
ssh_admin ceph orch apply -i monstack.yml

wait_for_progress
#
ssh_admin ceph dashboard set-grafana-frontend-api-url https://$adminhost.$domain:3000/

# allow inbound tcp connetions to port 3000, (and do not kill ssh)
fwid="$(hcloud firewall list | grep firewall_ceph_3000 | sed -e 's/ .*//')"
if [ -z "$fwid" ]; then
  fwid=$(hcloud firewall create --name firewall-ceph-3000 | tr -d "Fa-z ")
  hcloud firewall add-rule --direction in --source-ips 0.0.0.0/0 --port 3000 --protocol tcp $fwid
  hcloud firewall add-rule --direction in --source-ips 0.0.0.0/0 --port 22 --protocol tcp $fwid
  hcloud firewall add-rule --direction in --source-ips 0.0.0.0/0 --protocol icmp $fwid
fi
hcloud firewall apply-to-resource --type server --server "$adminhost" "$fwid"

# ask for $osds_per_host, with the one volume device, we have.
cat <<EOF | ssh_admin tee osd$gen_label.yml
 service_type: osd
service_id: ssd$gen_label
placement:
  label: osd$gen_label
spec:
  data_devices:
    rotational: false
    size: '$(($osd_host_vol_size_gb - 1))G:$(($osd_host_vol_size_gb + 1))G'
  osds_per_device: $osds_per_host
EOF

ssh_admin ceph orch apply -i osd$gen_label.yml

wait_for_progress

ssh_admin ceph orch host ls
ssh_admin ceph osd tree
