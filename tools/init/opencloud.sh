#! /bin/bash
#
# ENV_VARS: 	OC_NAME,INIT_ADMIN_PASS
# ENV_VARS_OPT: OC_VERSION		# E.g. 6.2.0, default: latest
# ENV_VARS_OPT: OC_DOCKER_TAG,OC_DOCKER_IMAGE		# default: OC_DOCKER_IMAGE=opencloudeu/opencloud-rolling
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
# - https:/docs.opencloud.eu/docs/next/admin/configuration/collabora/collabora-fonts
#
# Start this with:
#	export HCLOUD_TOKEN=...
#	export HCLOUD_DNS_ZONE=...
#	export HCLOUD_SSHKEY_NAMES=...
#	export INIT_ADMIN_PASS=...
# 	env OC_NAME=oc71  OC_VERSION=7.1 hetzner_deploy.sh init/opencloud.sh
#       env OC_NAME=oc72d1 OC_VERSION=7.2-$(date +%Y%m%d) OC_DOCKER_TAG=daily OC_DOCKER_IMAGE=opencloudeu/opencloud-rolling hetzner_deploy.sh opencloud
#
# CAUTION:
# * The official quick start documented in https://docs.opencloud.eu/docs/admin/ is:
#   	curl -L https://opencloud.eu/install | /bin/bash
#   - It does not explain under which conditions it would work.
#   - It does not seem to work on hetzner cloud.
#   - It does not hint at the docker-compose install used here.
#
# TODO:
#  - make storage driver configurable: STORAGE_USERS=posix ??
#  - add radicale calender support to .env COMPOSE_FILE=

source env.sh

export LC_ALL=C
export DEBIAN_FRONTEND=noninteractive

test -z "$EMAIL" && export EMAIL=admin@$HCLOUD_DNS_ZONE
# docker-compose.yml reacts to OC_DOCKER_TAG
if [ -n "$OC_VERSION" -a -z "$OC_DOCKER_TAG" ]; then
  export OC_DOCKER_TAG=$OC_VERSION
  echo >> env.sh 'export OC_DOCKER_TAG="$OC_VERSION"'
fi

admin_pass="$(tr -dc 'a-z0-9' < /dev/urandom | head -c 8)"
test -n "$INIT_ADMIN_PASS" && export admin_pass="$INIT_ADMIN_PASS"
echo >> env.sh "export admin_pass=$admin_pass"

curl -fsSL https://get.docker.com -o get-docker.sh
sh ./get-docker.sh

systemctl enable docker
systemctl start docker

# ttf-mscorefonts-installer is mentioned in collabora config docs. The package asks for an EULA. We agree unattended.
echo "ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true" | debconf-set-selections
apt install -y curl git vim ca-certificates ttf-mscorefonts-installer
git clone https://github.com/opencloud-eu/opencloud-compose.git

cd opencloud-compose
cp .env.example .env

sed -i -e "s/INSECURE=true/# INSECURE=true/" .env
sed -i -e "s/TRAEFIK_ACME_MAIL=.*/TRAEFIK_ACME_MAIL=$EMAIL/" .env
sed -i -e "s/INITIAL_ADMIN_PASSWORD=.*/INITIAL_ADMIN_PASSWORD=$admin_pass/" .env
## without collabora or tika
echo >> .env 'COMPOSE_FILE=docker-compose.yml:traefik/opencloud.yml'
## with tika
# echo >> .env 'COMPOSE_FILE=docker-compose.yml:search/tika.yml:traefik/opencloud.yml'
## with collabora
#echo >> .env 'COMPOSE_FILE=docker-compose.yml:weboffice/collabora.yml:traefik/opencloud.yml:traefik/collabora.yml'
## with tika and collabora
# https://github.com/opencloud-eu/opencloud/issues/2807
# echo >> .env 'COMPOSE_FILE=docker-compose.yml:search/tika.yml:weboffice/collabora.yml:traefik/opencloud.yml:traefik/collabora.yml'


names="cloud collabora wopiserver traefik keycloak"
# check, if we onw all our DNS entries here.
for name in $FQDNS; do
    addr=$(dig +short $name)
    if [ -z "$addr" ]; then
        echo "ERROR: failed to retrieve ip addr for: $name"
	echo "Press ENTER to continue."
	read a
    else
	if ip addr | grep -Fqw "$IPADDR"; then
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

docker compose up

cat <<'EOF'
  OpenCloud docker compose environment is prepared.

you can stop the server with CTRL-C here.
To fully clean up, use

	docker compose down
	docker volume rm $(docker volume ls -q)
EOF

