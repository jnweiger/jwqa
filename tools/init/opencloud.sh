#! /bin/bash
#
# ENV_VARS: 	OC_NAME,INIT_ADMIN_PASS
# ENV_VARS_OPT: OC_VERSION		# E.g. 6.2.0, default: latest
# ENV_VARS_OPT: OC_DOCKER_TAG,OC_DOCKER_IMAGE		# default: OC_DOCKER_IMAGE=opencloudeu/opencloud-rolling
# DNS_NAME:     OC_NAME
# DNS_NAME:     cloud.OC_NAME
# DNS_NAME:     collabora.OC_NAME
# DNS_NAME:     keycloak.OC_NAME
# DNS_NAME:     mail.OC_NAME
# HCLOUD_TYPE:  cx23			# cx23 4GB, ...
# OPEN_PORTS:	80,22,443	# not enforced currently, info only.
#
# Study
# - https://docs.opencloud.eu/docs/admin/getting-started/container/docker-compose/extern
# - https://docs.opencloud.eu/docs/admin/configuration/collabora/collabora-fonts
#
# Start this with:
#	export HCLOUD_TOKEN=...
#	export HCLOUD_DNS_ZONE=...
#	export HCLOUD_SSHKEY_NAMES=...
#	export INIT_ADMIN_PASS=...
# 	hetzner_deploy.sh -n oc71 init/opencloud.sh OC_VERSION=7.1 INIT_ADMIN_PASS=1234
#       env OC_NAME=oc-test hetzner_deploy opencloud OC_VERSION=daily-$(date +%Y%m%d) OC_DOCKER_TAG=daily OC_DOCKER_IMAGE=opencloudeu/opencloud-rolling
#       env OC_NAME=oc90r hetzner_deploy opencloud OC_DOCKER_TAG=9.0.0
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

export PROXY_PORT=9200		# default, can be overridden by passing PROXY_PORT=9200 at the command line

source env.sh
export LC_ALL=C
export DEBIAN_FRONTEND=noninteractive

if [ ! -f init/opencloud/nginx.sh ]; then
  echo "nginx setup missing!"
  exit 1
fi
# temporaroly hide the names we don't want.
ALL_FQDNS="$FQDNS"
FQDNS="$DNS_NAME cloud.$DNS_NAME"
source init/opencloud/nginx.sh
FQDNS="$ALL_FQDNS"
echo "nginx setup for ssl-offloading done ..."

test -z "$EMAIL" && export EMAIL=admin@$HCLOUD_DNS_ZONE
# docker-compose.yml reacts to OC_DOCKER_TAG
if [ -n "$OC_VERSION" -a -z "$OC_DOCKER_TAG" ]; then
  export OC_DOCKER_TAG=$OC_VERSION
  echo >> env.sh 'export OC_DOCKER_TAG="$OC_VERSION"'
fi

admin_pass="$(tr -dc 'a-z0-9' < /dev/urandom | head -c 8)"
test -n "$INIT_ADMIN_PASS" && export admin_pass="$INIT_ADMIN_PASS"
echo >> env.sh "export admin_pass=$admin_pass"

if ! systemctl is-enabled docker; then
  curl -fsSL https://get.docker.com -o get-docker.sh
  sh ./get-docker.sh

  systemctl enable docker
  systemctl start docker
fi

## prepare inbucket
echo >> init/opencloud/inbucket/.env "INBUCKET_DOMAIN=mail.$DNS_NAME"

## Caution: keep in sync with nginx.sh
cat <<EOF > /etc/nginx/sites-available/mail-inbucket
server {
    listen 80;
    listen [::]:80;
    server_name mail.$DNS_NAME;
    location /.well-known/acme-challenge/ { root /var/www/html; }
    location / { return 301 https://\$host\$request_uri; }
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;

    server_name mail.$DNS_NAME;

    ssl_certificate /etc/letsencrypt/live/$DNS_NAME/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DNS_NAME/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;


    location / {
        proxy_pass http://127.0.0.1:9000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 300s;   # let websockets live for a while
    }
}
EOF

## Reference:
# - https://sdk.collaboraonline.com/docs/installation/Proxy_settings.html#reverse-proxy-settings-in-nginx-config-ssl-termination
# Reverse proxy settings in Nginx config (SSL termination)
# In coolwsd.xml the corresponding setting is ssl.enable=false and ssl.termination=true.
#
cat <<EOF > /etc/nginx/sites-available/collabora
server {
    listen 80;
    listen [::]:80;
    server_name collabora.$DNS_NAME;
    location /.well-known/acme-challenge/ { root /var/www/html; }
    location / { return 301 https://\$host\$request_uri; }
}

server {
 listen       443 ssl;
 listen [::]:443 ssl;

 server_name collabora.$DNS_NAME;

 ssl_certificate /etc/letsencrypt/live/$DNS_NAME/fullchain.pem;
 ssl_certificate_key /etc/letsencrypt/live/$DNS_NAME/privkey.pem;


 # static files
 location ^~ /browser {
   proxy_pass http://127.0.0.1:9980;
   proxy_set_header Host \$host;
 }


 # WOPI discovery URL
 location ^~ /hosting/discovery {
   proxy_pass http://127.0.0.1:9980;
   proxy_set_header Host \$host;
 }


 # Capabilities
 location ^~ /hosting/capabilities {
   proxy_pass http://127.0.0.1:9980;
   proxy_set_header Host \$host;
 }


 # main websocket, download, presentation (legacy svg) and image upload
 location ^~ /cool/ {
   proxy_pass http://127.0.0.1:9980;
   proxy_http_version 1.1;
   proxy_set_header Upgrade \$http_upgrade;
   proxy_set_header Connection "Upgrade";
   proxy_set_header Host \$host;
   proxy_read_timeout 36000s;
 }


 # health checks, used since 26.04.3.1 by load balancers and monitoring
 location ^~ /livez {
   proxy_pass http://127.0.0.1:9980;
   proxy_set_header Host \$host;
 }


 location ^~ /readyz {
   proxy_pass http://127.0.0.1:9980;
   proxy_set_header Host \$host;
 }
}
EOF

ln -s /etc/nginx/sites-available/collabora     /etc/nginx/sites-enabled/collabora
ln -s /etc/nginx/sites-available/mail-inbucket /etc/nginx/sites-enabled/mail-inbucket
nginx -t
systemctl reload nginx

## extending the cert should not be necessary. In any case, here is how:
# certbot certificates
# certbot --expand -n --nginx --cert-name $DNS_NAME -d $DNS_NAME,cloud.$DNS_NAME,collabora.$DNS_NAME,mail.$DNS_NAME certonly || true
# certbot -n --nginx --cert-name $DNS_NAME install  || true
# systemctl restart nginx


# ttf-mscorefonts-installer is mentioned in collabora config docs. The package asks for an EULA. We agree unattended.
echo "ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true" | debconf-set-selections
apt install -y curl git jq vim ca-certificates swaks # ttf-mscorefonts-installer
git clone https://github.com/opencloud-eu/opencloud-compose.git

(cd init/opencloud/inbucket; docker compose up -d)
sleep 4
swaks --to testy@jwqa.de --server mail.$DNS_NAME:2500 || true
echo "Read the test-mail e.g. with:"
echo "      firefox https://mail.$DNS_NAME/m/testy@jwqa.de"

mkdir -p    oc-run/{data,config,apps}
chmod a+rwx oc-run/{data,config,apps}	# must allow write for docker uid=1000, gid=1000
cp init/opencloud/config-app-registry.yaml oc-run/config/app-registry.yaml

cd opencloud-compose
cp .env.example .env

# https://docs.opencloud.eu/docs/admin/getting-started/container/docker-compose/external-proxy#configure-and-start-opencloud
sed -i -e "s/INSECURE=true/# INSECURE=true/" .env
echo >> .env "OC_DOMAIN=$DNS_NAME"
echo >> .env "COLLABORA_DOMAIN=collabora.$DNS_NAME"
echo >> .env "INBUCKET_DOMAIN=mail.$DNS_NAME"
echo >> .env "DEMO_USERS=true"
echo >> .env "INITIAL_ADMIN_PASSWORD=$admin_pass"
echo >> .env "COMPOSE_FILE=docker-compose.yml:weboffice/collabora.yml:external-proxy/opencloud.yml:external-proxy/collabora.yml:search/tika.yml"

# where config, data, apps reside (default: inside docker volumes, that is not nice.
echo >> .env "OC_CONFIG_DIR=/root/oc-run/config/"
echo >> .env "OC_DATA_DIR=/root/oc-run/data/"
echo >> .env "OC_APPS_DIR=/root/oc-run/apps/"

# outbound mail
echo >> .env "SMTP_HOST=mail.$DNS_NAME"
echo >> .env "SMTP_PORT=2500"
echo >> .env "SMTP_SENDER=noreply@mail.$DNS_NAME"
echo >> .env "SMTP_USERNAME="
echo >> .env "SMTP_PASSWORD="
echo >> .env "SMTP_TRANSPORT_ENCRYPTION=none"
echo >> .env "SMTP_INSECURE=true"
echo >> .env "SMTP_AUTHENTICATION=none"

## we enable the following services:
# guest-auth		https://github.com/opencloud-eu/docs/pull/1257/changes#diff-133ad3591ba0201adbc4619cad9f2f03d55ba769b501fa3ed7cbd44f732d19fd
# email			needed by guest-auth (docs/admin/configuration/mail-notifications.md)
#			Make sure that your SMTP configuration is working (mailpit inbucket?)
# notification		needed by mail-notification

echo >> .env 'OC_ENABLE_GUEST_LINKS=true'
echo >> .env "START_ADDITIONAL_SERVICES=notifications"

# collabora behind nginx ssl termination
echo >> .env "COLLABORA_SSL_ENABLE=false"
echo >> .env "COLLABORA_SSL_VERIFICATION=false"
echo >> .env "COLLABORA_SSL_TERMINATION=true"	# that is hardcoded true in weboffice/collabora.yaml

# optional: customize via custom/guest.yml
# 	For a complete list of settings, see the [auth-guest environment variables](../../dev/server/services/auth-guest/env-vars.mdx)

docker compose up -d


# check if we are Up
docker compose ps opencloud

# check, if the opencloud container has this as true
docker compose exec opencloud printenv OC_ENABLE_GUEST_LINKS

# check if notificaitons service is running: the output must contain notifications
docker compose exec opencloud printenv OC_ADD_RUN_SERVICES
docker compose logs opencloud | grep '"service":"notifications"' | tail -10

# check that configuration contains the service account settings for the `auth-guest` service
docker compose exec opencloud grep -A3 "auth_guest:" /etc/opencloud/opencloud.yaml

# check if the collabora container expoese its discovers
curl -s http://127.0.0.1:9980/hosting/discovery | head -n5
# check if nginx promotes to https and proxies the discovery
curl -s -L http://collabora.$DNS_NAME/hosting/discovery | head -n5
# same output here as above.

## but collabora still does not work:
# wsd-00001-00043 2026-11-11 17:31:22.418627 [ websrv_poll ] ERR  #32: Bad request: GET HTTP/1.0 /cool/https%3A%2F%2Foc90r.jwqa.de%2Fwopi%2Ffiles%2Fdc69c2afc00d2163bd534798930daede483093e29173d92104199e14a1dcaff6%3Faccess_token%3DeyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJXb3BpQ29udGV4dCI6eyJBY2Nlc3NUb2tlbiI6IkZKblJyN2Q1YWdOX1lMZEJ4SkVZWnVCcWIwdXIyOUdFTGZKTjltc1VHX0RWcWYweHRNQ1BJYmJxcGFKZUczX1BsYURQUThZdU9FVnNvYThWblJISDdHNlNyb2ZtQmhBZ1RHaTlTbzhzZENkLVdHX1hvRno1NER2RlVlVThZWG92TWR0QU5yV3RVS21JNTVKQ2Jhc3dJR2N2a0dtc29ZUXFHZU9teVE2eE1zS1h1b19MUkxiNkVfbkpyT3RZcFNDazdOeFFCUElhSV9adm1YWEhEUGR2eE10aVdXdVFGUFltcWloUDgyMGFfZ0k5LXRTbzg4Y3JxdkJHWWxzcVVBREVVLXFRQzl3N3htY3I2NE9YQkdES3Y1WVI1aVAzSVJLVUlxVWNrbklPYVdnSTVGVFFsc09lU2k5N3p0V0VhT1RTWEd3eDMwbVp3Szl0TWVuMlFuVGFMbXlIcmpmVW51RWk3Y2hDUEVTQS1Udld0YlhjalNfTnRIT3VVeGI3NlNRS0dMbnZ5a013UUEzZm5EdXdvSW42OVBKQTBRNXlPWWdKQXdtSTg5TmVFcThHOEZNRng5dW1Qel9VMmpMbkl3YlZ4MzBGV2t5SlczU1NWZC1NZXNtcTVCSFdESnc0QVJabm9JcG82OXlTZi14bHBaSUNRM19pWjhUcENtMVFTdFhaSHdMVXlaOS12WnRBR2tQV0lZUFBZNjExR1B4cHJXYlRwemo3NEVHTVV5M0kzUnp5MjNSNlVjc2tiXzVxcElQM05MUlhsV0hMYWh2VXl4c1ZRTU9PT3FHdDkzamJLdl95TkI4WGV4SFRIZHZsRnc5dXpnam9qRTItZlRSQUc4MUV5TW0xTWVsTTFtQkRQVklVYlNGWFRSNmR1Skt2ZTB6UnNSeVZtdFhuX0JFdTBoTmxkdzh5eHh2U3ZKaFZtcW9Vek1IaVpJcVlhdnFvY3BIM2NCWGlTb1hDejcyYmhLbGN5cXRwSjZMS0FjV0Y2UTNmZjFmY0RLejZueEFaOEx1VVpQc1ZLT1ZrWWFSSjVDck9sQkh5c0F2eVg2R2Vnb3JkOUNNVTV1X0s4ZnF4UjBqLXVMeHNMZldvaXI2MFNiRlcxWkhaZjRiTm9pMEhsOWpFRGdOMTVyTnpfMnB0WC13RjdlbHJXcXNhelZNcHZQai0ySjNidXdrV2RQdEhtWXR6ajYzdDBqbVNSUnFYbWJyNk8wNnhhM3ZxWEFYNUxCOWR5c3cxY05tMnYwQ1BFQWJJRUNqVjRjOWZ4MmtXX0haOGdXeThoWE5QTlVrMGxuX1YxZVdWdXdPcWk0UFQzYk8wM0xzdUNYMUlKeWNKTDdjemRwMDJYbUxCUl9tRVREWVdwREdCbXBjS1pRbmtaQjA0T3VrektxTWZYOGpGSk5LQWFLMmJlZ0VMYVlxd3c3VmN6V2YwcXlzcFd1Vk50ZUQydExhanZQaz0iLCJWaWV3T25seVRva2VuIjoiIiwiRmlsZVJlZmVyZW5jZSI6eyJyZXNvdXJjZV9pZCI6eyJzdG9yYWdlX2lkIjoiYTI4ZjM3OGYtYmNkYy00OTA5LTk2ZDQtMjA1MGUzZWJkYTIzIiwib3BhcXVlX2lkIjoiZTAxNDYwMjMtZTdjOS00NmRjLWFkZTctZTM2ZjI5MTdiM2Y5Iiwic3BhY2VfaWQiOiI5NzViMDA5Zi1mNmEzLTRkYWYtYjU2Ni01ZTQyMWI2N2U1MjkifSwicGF0aCI6Ii4ifSwiVGVtcGxhdGVSZWZlcmVuY2UiOm51bGwsIlZpZXdNb2RlIjozfSwiZXhwIjoxNzk0NTA0Njc0fQ.ErrZ8ooW6-PM7G-mw5n6s9u6EakWn_Dy0sJp2n_G060%26access_token_ttl%3D1794504674000%26permission%3Dedit/ws?WOPISrc=https%3A%2F%2Foc90r.jwqa.de%2Fwopi%2Ffiles%2Fdc69c2afc00d2163bd534798930daede483093e29173d92104199e14a1dcaff6&compat=/ws, content-length: -1, chunked: false, Host: collabora.oc90r.jwqa.de / X-Real-IP: 80.139.89.146 / X-Forwarded-For: 80.139.89.146 / X-Forwarded-Proto: https / Connection: close / User-Agent: Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:155.0) Gecko/20100101 Firefox/155.0 / Accept: */* / Accept-Language: de,en-US;q=0.9,en;q=0.8 / Accept-Encoding: gzip, deflate, br, zstd / Sec-WebSocket-Version: 13 / Origin: https://collabora.oc90r.jwqa.de / Sec-WebSocket-Extensions: permessage-deflate / Sec-WebSocket-Key: /rc3roHTmWAVVTvL0X0X8w== / Sec-Fetch-Dest: empty / Sec-Fetch-Mode: websocket / Sec-Fetch-Site: same-origin / Sec-GPC: 1 / Pragma: no-cache / Cache-Control: no-cache, closeConnection: true, socket-data: [GET /cool/https%3A%2F%2Foc90r.jwqa.de%2Fwopi%2Ffiles%2Fdc69c2afc00d2163bd534798930daede483093e29173d92104199e14a1dcaff6%3Faccess_token%3DeyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJXb3BpQ29udGV4dCI6eyJBY2Nlc3NUb2tlbiI6IkZKblJyN2Q1YWdOX1lMZEJ4SkVZWnVCcWIwdXIyOUdFTGZKTjltc1VHX0RWcWYweHRNQ1BJYmJxcGFKZUczX1BsYURQUThZdU9FVnNvYThWblJISDdHNlNyb2ZtQmhBZ1RHaTlTbzhzZENkLVdHX1hvRno1NER2RlVlVThZWG92TWR0QU5yV3RVS21JNTVKQ2Jhc3dJR2N2a0dtc29ZUXFHZU9teVE2eE1zS1h1b19MUkxiNkVfbkpyT3RZcFNDazdOeFFCUElhSV9adm1YWEhEUGR2eE...]: Invalid or unknown request.|home/collabora/jenkins/workspace/package_code_26.04_rpm/rpmbuild/BUILD/coolwsd-26.04.5.2/wsd/ClientRequestDispatcher.cpp:1721
## mabye ot helps to remove an old volume:
# docker volume rm opencloud-compose_collabora-proof-key


# print out image, version and birth.
docker inspect opencloud-compose-opencloud-1 | grep -E '(config_files|Image.:|image.version|image.url|image.created)'

#
echo "early exit"
# exit 0
# =================================
#
# sed -i -e "s/TRAEFIK_ACME_MAIL=.*/TRAEFIK_ACME_MAIL=$EMAIL/" .env
# ## without collabora or tika
# echo >> .env 'COMPOSE_FILE=docker-compose.yml:traefik/opencloud.yml'
# ## with tika
# # echo >> .env 'COMPOSE_FILE=docker-compose.yml:search/tika.yml:traefik/opencloud.yml'
# ## with collabora
# #echo >> .env 'COMPOSE_FILE=docker-compose.yml:weboffice/collabora.yml:traefik/opencloud.yml:traefik/collabora.yml'
# ## with tika and collabora
# # https://github.com/opencloud-eu/opencloud/issues/2807
# # echo >> .env 'COMPOSE_FILE=docker-compose.yml:search/tika.yml:weboffice/collabora.yml:traefik/opencloud.yml:traefik/collabora.yml'
#
#
# names="cloud collabora wopiserver keycloak"
# # check, if we onw all our DNS entries here.
# for name in $FQDNS; do
#     addr=$(dig +short $name)
#     if [ -z "$addr" ]; then
#         echo "ERROR: failed to retrieve ip addr for: $name"
# 	echo "Press ENTER to continue."
# 	read a
#     else
# 	if ip addr | grep -Fqw "$IPADDR"; then
# 	    echo "$name = $addr is here"
# 	else
#             echo "+ hostname -I"
# 	    hostname -I
#             echo "ERROR: $name points elsewhere: $addr"
# 	    echo "Press ENTER to continue."
# 	    read a
# 	fi
#    fi
# done
#
# TLD=$OC_NAME.$HCLOUD_DNS_ZONE
# for name in $names; do
#   ucname=$(echo $name | tr a-z A-Z)
#   test "$ucname" == CLOUD && ucname=OC
#   sed -i -e "s/${ucname}_DOMAIN=.*/${ucname}_DOMAIN=$name.$TLD/" .env
# done
#
# docker compose config | grep image:
#
# docker compose up
#
# cat <<'EOF'
#   OpenCloud docker compose environment is prepared.
#
# you can stop the server with CTRL-C here.
# To fully clean up, use
#
# 	docker compose down
# 	docker volume rm $(docker volume ls -q)
# EOF

