#! /bin/bash

## HCLOUD_TYPE:  cpx11		# cpx11 2GB, cpx21 4GB, cpx41 8G
# HCLOUD_IMAGE: debian-13
export PROXY_PORT=9200		# default, can be overridden by passing PROXY_PORT=9200 after nginx

source env.sh
export LC_ALL=C
export DEBIAN_FRONTEND=noninteractive

for kv in $ARGS; do
   name=${kv%%=*}
   test -n "$name" && export $kv
   echo "export $kv" >> env.sh
done

apt purge -y apache2
apt install -y nginx openssl ca-certificates certbot python3-certbot-nginx

if [ -n "$HCLOUD_DNS_ZONE" ]; then
  # FIXME:  this should go into hetzner_deploy.sh
  # add a search domain to resolv.conf, so that short hostnames work. 
  # resolvconf -u also makes 'hostname --fqdn' work. WOW. (domainname does not.)
  domainname "$HCLOUD_DNS_ZONE"
  ## /etc/resolvconf/* does not exist today..??? 
  # echo search "$HCLOUD_DNS_ZONE" >> /etc/resolvconf/resolv.conf.d/base
  # resolvectl .... ??? 
fi

cat <<EOF > /etc/nginx/sites-available/ssl-proxy
server {
    listen 443 ssl;
    http2 on;

    server_name $DNS_NAME;

    ssl_certificate     /etc/letsencrypt/live/$DNS_NAME/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DNS_NAME/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;

    location / {
        proxy_pass http://127.0.0.1:$PROXY_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}

server {
    listen 80;
    server_name $DNS_NAME;

    return 301 https://\$host\$request_uri;
}
EOF

ln -s /etc/nginx/sites-available/ssl-proxy /etc/nginx/sites-enabled/ssl-proxy
rm /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx


