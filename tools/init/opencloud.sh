#! /bin/bash
#
# ENV_VARS: 	OC_NAME,INIT_ADMIN_PASS
# DNS_NAME:     cloud.OC_NAME
# DNS_NAME:     collabora.OC_NAME
# DNS_NAME:     wopiserver.OC_NAME
# DNS_NAME:     traefik.OC_NAME
# DNS_NAME:     keycloak.OC_NAME
# AUTOSTART_CERTBOT:     false		# we do everything with traefik here. 
# HCLOUD_TYPE:  cx23			# cx23 4GB, ...
# OPEN_PORTS:	80,22,443	# not enforced currently, info only.
#
# Study
# - https://github.com/opencloud-eu/opencloud-compose
# - https://docs.opencloud.eu/docs/admin/getting-started/container/docker-compose/docker-compose-base/
#
# TODO:
# - control OC_VERSION. it seems 
#
# CAUTION:
# * The official quick start documented in https://docs.opencloud.eu/docs/admin/ is:
#   	curl -L https://opencloud.eu/install | /bin/bash
#   - It does not explain under which conditions it would work.
#   - It does not seem to work on hetzner cloud.
#   - It does not hint at the docker-compose install used here.
#

source env.sh	# not really needed here.

export LC_ALL=C
export DEBIAN_FRONTEND=noninteractive

export EMAIL=jw@example.org

admin_pass="$(tr -dc 'a-z0-9' < /dev/urandom | head -c 8)"
test -n "$INIT_ADMIN_PASS" && export admin_pass="$INIT_ADMIN_PASS"
echo "export admin_pass=$admin_pass" >> env.sh

curl -fsSL https://get.docker.com -o get-docker.sh
sh ./get-docker.sh

systemctl enable docker
systemctl start docker

apt install -y curl git vim ca-certificates
git clone https://github.com/opencloud-eu/opencloud-compose.git

cd opencloud-compose
cp .env.example .env

sed -i -e "s/INSECURE=true/# INSECURE=true/" .env
sed -i -e "s/TRAEFIK_ACME_MAIL=.*/TRAEFIK_ACME_MAIL=$EMAIL/" .env
sed -i -e "s/INITIAL_ADMIN_PASSWORD=.*/INITIAL_ADMIN_PASSWORD=$admin_pass/" .env
echo 'COMPOSE_FILE=docker-compose.yml:traefik/opencloud.yml' >> .env

names="cloud collabora wopiserver traefik keycloak"
# check, if we onw all our DNS entries here.
for name in $FQDNS; do
    addr=$(dig +short $name)
    if [ -z "$addr" ]; then
        echo "ERROR: failed to retrieve ip addr for: $name"
	echo "Press ENTER to continue."
	read a
    else
	if ip addr | grep -Fqw '37.27.30.108'; then
	    echo "$name = $addr is here"
	else
            echo "+ hostname -I"
	    hostname -I
            echo "ERROR: $name points elsewhere: $addr"
	    echo "Press ENTER to continue."
	    read a
	fi
   fi
done

TLD=$OC_NAME.$HCLOUD_DNS_ZONE
for name in $names; do
  ucname=$(echo $name | tr a-z A-Z)
  test "$ucname" == CLOUD && ucname=OC
  sed -i -e "s/${ucname}_DOMAIN=.*/${ucname}_DOMAIN=$name.$TLD/" .env
done

docker compose config | grep image:

cat <<EOF
  OpenCloud docker compose environment is prepared.
  Please do the following to start the server:

cd opencloud-compose
docker compose up
EOF

