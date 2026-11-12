#! /bin/bash
#
# This is a simple upload only ftp server.
#
# ENV_VARS_OPT: FTP_PORT	# default: s14321
# ENV_VARS_OPT: FTP_USER	# default: ftpupload
# ENV_VARS_OPT: FTP_PASS	# default: ... see below
# ENV_VARS_OPT: FTP_UMASK	# default: 533:422 (aka upload-only) use "002:002" for free file sharing.
# DNS_NAME:     ftp-DATE
# HCLOUD_TYPE:  cx23				# cx23 4GB, ...
# OPEN_PORTS:	12321,30000,30001,30002,30003	# not enforced currently, info only.
#
# Start this with
# 	hetzner_deploy.sh [-d] pureftpd
#
# BUG ALERT:
#  The pure-pw tool in mbentley/pure-ftpd:latest uses insane argon2 parameters:
#  docker exec -it pureftpd cat /etc/pure-ftpd/pureftpd.pdb | xxd
#  ...
#  00000800: fd00 0000 fe00 0000 ff00 0001 0000 0000  ................
#  00000810: 0966 7470 7570 6c6f 6164 0000 0082 2461  .ftpupload....$a
#  00000820: 7267 6f6e 3269 6424 763d 3139 246d 3d38  rgon2id$v=19$m=8
#  00000830: 3139 322c 743d 3531 312c 703d 3124 6977  192,t=511,p=1$iw
#  00000840: 746e 6274 536f 6153 732f 4473 394b 762f  tnbtSoaSs/Ds9Kv/
# -> this t=511 should be t=2 normally. password hashing takes ca 10 to 20 seconds of CPU time with t=511
#    -> every login is delayed by that hashing time.
#	-> https://github.com/mbentley/docker-pure-ftpd/issues/1


export FTP_PORT=14321		# default, can be overridden by passing FTP_PORT=2121 as a parameter to pureftpd
export FTP_USER=ftpupload
export FTP_PASS=tbatstdgagitwamwtbamro
export FTP_UMASK="533:422"          # files -> 0200 (w only), dirs -> 0300 (wx only)

source env.sh		# needed for IPADDR
export LC_ALL=C
export DEBIAN_FRONTEND=noninteractive

mkdir -p   pure-ftpd
mkdir -p   /srv/ftp/data	# a netral place, so that others (non-root) can access
chown 1000 /srv/ftp/data
chgrp 33   /srv/ftp/data	# 33=www-data the normal apache user / group id.
chmod u+wx /srv/ftp/data	# assert, that we uid=1000 can write files in data.
chmod u-r  /srv/ftp/data	# disallow no directory listings.
chmod g+rs /srv/ftp/data	# sticky bit, so that users in www-data group can read the files, even if we uid=1000 cannot.
ln -s /srv/ftp/data pure-ftpd	# convenience for the root user


curl -fsSL https://get.docker.com -o get-docker.sh
sh ./get-docker.sh

systemctl enable docker
systemctl start docker

cd pure-ftpd

echo >>.env "FTP_USER_NAME=$FTP_USER"
echo >>.env "FTP_USER_PASS=$FTP_PASS"

cat <<EOF>docker-compose.yaml
services:
  ftpd:
    image: stilliard/pure-ftpd:hardened
    # image: mbentley/pure-ftpd:latest		# has a 10 sec delay when logging in. https://github.com/mbentley/docker-pure-ftpd/issues/1
    container_name: pureftpd
    restart: unless-stopped
    ports:
      - "14321:21"
      - "30000-30003:30000-30003"
    env_file:
      - .env
    environment:
      PUBLICHOST: "$IPADDR"
      FTP_PASSIVE_PORTS: "30000:30003"
      FTP_USER_HOME: "/data"
      FTP_USER_UID: "1000"
      FTP_USER_GID: "1000"
      FTP_UMASK: "$FTP_UMASK"          # files=577 -> 0200 (w only) : dirs=477 0300 (wx only)
    volumes:
      - ./data:/data
EOF

docker compose up -d
sleep 3
docker compose ps
echo
docker compose logs
echo
echo "ftp $DNS_NAME $FTP_PORT"
echo " username: $FTP_USER"
echo " password: $FTP_PASS"
echo
