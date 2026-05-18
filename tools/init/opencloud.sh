#! /bin/bash
#
# DNS_NAME:     cloud
# DNS_NAME:     collabora
# DNS_NAME:     wopiserver
# DNS_NAME:     traefik
# DNS_NAME:     keycloak
# HCLOUD_TYPE:  cx23		# cpx11 2GB, cpx21 4GB, cpx41 8G
# ENV_VARS_OPT: INIT_ADMIN_PASS
# OPEN_PORTS:	80,22,443	# not enforced currently, info only.
#
# Study
# - https://github.com/opencloud-eu/opencloud-compose
# - https://docs.opencloud.eu/docs/admin/getting-started/container/docker-compose/docker-compose-base/
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

apt install -y curl git vim ca-certificates transport-https
git clone https://github.com/opencloud-eu/opencloud-compose.git

cd opencloud-compose
cp .env.example .env

sed -i -e "'s/INSECURE=true/# INSECURE=true/'" .env
sed -i -e "'s/TRAEFIK_ACME_MAIL=.*/TRAEFIK_ACME_MAIL=$EMAIL/'" .env
sed -i -e "'s/INITIAL_ADMIN_PASSWORD=.*/INITIAL_ADMIN_PASSWORD=$admin_pass/'" .env
echo 'COMPOSE_FILE=docker-compose.yml:traefik/opencloud.yml' >> .env

names="cloud collabora wopiserver traefik keycloak"
for name in $names; do
done


for name in $names; do
  ucname=$(echo $name | tr a-z A-Z)
  test "$ucname" == CLOUD && ucname=OC
  sed -i -e "'s/${ucname}_DOMAIN=.*/${ucname}_DOMAIN=$name.$TLD/'" .env
done

cat <<EOF
  OpenCloud docker compose environment is prepared.
  Please do the following to start the server:

cd opencloud-compose
docker compose up
EOF

