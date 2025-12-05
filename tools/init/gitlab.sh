#! /bin/bash
#
# DNS_NAME: gitlab
# HCLOUD_TYPE: cpx31   	# 4       shared      x86            8.0 GB     160 GB
# ENV_VARS_OPT: INIT_ADMIN_PASS
#
# References:
#  - https://docs.gitlab.com/install/package/ubuntu/?tab=Community+Edition
#  - https://docs.gitlab.com/tutorials/install_gitlab_single_node/?utm_source=chatgpt.com
#
# Note:
#  - postinstall of the gitlab-ce package takes ca 5 min.

source env.sh

edition=ce	# ce or ee

export EXTERNAL_URL="https://$DNS_NAME"
# gitlab will generate a random password, when GITLAB_ROOT_PASSWORD is undefined.
test -n "$INIT_ADMIN_PASS" && export GITLAB_ROOT_PASSWORD="$INIT_ADMIN_PASS"

# No apache for gitlab. It wants o occupy port 80 and 443 with its own nginx or Puma web server.
# There is no option to feed an existing cert into gitlab.
# Post install of the gitlab package is fancy: it sets up postgres, a web server, contacts letsencrypt, yada yada...
apt purge -y apache2

apt install -y curl
curl "https://packages.gitlab.com/install/repositories/gitlab/gitlab-$edition/script.deb.sh" | bash
apt install -y gitlab-$edition

test -f /etc/gitlab/initial_root_password && ( set -x; cat /etc/gitlab/initial_root_password )

