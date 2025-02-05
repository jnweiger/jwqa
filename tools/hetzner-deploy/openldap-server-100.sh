# Setup for a small local ldap server with 100 users in 10 groups with 10 users each.
#
# - upon first start, this
#   * this creates some ldif files,
#   * starts a docker based server, and
# - re-running this script (after changes)
#   * recreates the ldif files, then
#   * only prints instructions to restart the server.
#
# References: https://github.com/osixia/docker-openldap?tab=readme-ov-file#quick-start
# - LDAP_ADMIN_PASSWORD		default: admin
# - LDAP_CONFIG_PASSWORD	default: config
# - LDAP_READONLY_USER		Add a read only user. Defaults to false
# - LDAP_DOMAIN			Defaults to example.org
# - LDAP_BASE_DN		default: empty = derive from LDAP_DOMAIN
# - LDAP_ORGANISATION		Defaults to Example Inc.
# - LDAP_READONLY_USER		Add a read only user. Defaults to false
# - LDAP_READONLY_USER_USERNAME	Defaults to readonly
# - LDAP_READONLY_USER_PASSWORD Defaults to readonly
# - LDAP_RFC2307BIS_SCHEMA	Use rfc2307bis instead of nis. Defaults to false
# - LDAP_BACKEND		Defaults to mdb (previously hdb in image versions up to v1.1.10)

admin_dn="cn=admin,dc=jwqa,dc=org"
admin_pass="12345678"
ldapport=3389	# default: 389, but when running as non-root under podman, then we need a port above 1000.
ldapsport=6636	# default: 636, but when running as non-root under podman, then we need a port above 1000.

generate_ldif=true	# must be true or false
ldif=$HOME/ldif-100	# must be absolute path, because of docker.
mkdir -p $ldif

## https://www.ibm.com/docs/en/zos/2.2.0?topic=introduction-ldap-schema-attributes
## Supported LDAP syntaxes: general use
# 1.3.6.1.4.1.1466.115.121.1.5 	Binary 			Binary data
# 1.3.6.1.4.1.1466.115.121.1.6 	Bit String* 		Bit data format (for example '0110'B)
# 1.3.6.1.4.1.1466.115.121.1.7 	Boolean 		TRUE, FALSE
# 1.3.6.1.4.1.1466.115.121.1.12 Distinguished Name 	Sequence of attribute type and value pairs
# 1.3.6.1.4.1.1466.115.121.1.15 Directory String 	UTF-8 characters
# 1.3.6.1.4.1.1466.115.121.1.27 Integer 		+/- 62 digit integer
# 1.3.6.1.4.1.1466.115.121.1.28 JPEG* 			Binary data (no format checking)
# 1.3.6.1.4.1.1466.115.121.1.36 Numeric String* 	List of space-separated numbers
# 1.3.6.1.4.1.1466.115.121.1.38 Object Identifier 	Name or numeric object identifier
# 1.3.6.1.4.1.1466.115.121.1.40 Octet String 		Octet data

## Supported LDAP syntaxes: server use
# 1.3.6.1.4.1.1466.115.121.1.3 	Attribute Type Description
# 1.3.6.1.4.1.1466.115.121.1.16 DIT Content Rule Description
# 1.3.6.1.4.1.1466.115.121.1.17 DIT Structure Rule Description
# 1.3.6.1.4.1.1466.115.121.1.30 Matching Rule Description
# 1.3.6.1.4.1.1466.115.121.1.31 Matching Rule Use Description
# 1.3.6.1.4.1.1466.115.121.1.35 Name Form Description
# 1.3.6.1.4.1.1466.115.121.1.37 Object Class Description
# 1.3.6.1.4.1.1466.115.121.1.54 LDAP Syntax Description
# 1.3.6.1.4.1.1466.115.121.1.58 Substring Assertion


## FROM https://stackoverflow.com/questions/6372365/support-reverse-group-membership-maintenance-for-openldap-2-3
## Fails with DEBUG  | 2021-12-15 01:12:47 | ldap_add: No such object (32)
## 	matched DN: cn=config
## adding new entry "olcOverlay={1}memberof,olcDatabase={2}hdb,cn=config"
## ldap_add: Insufficient access (50)
##
# $generate_ldif && cat <<EOF4 > $ldif/11_memberof.ldif
# dn: olcOverlay={1}memberof,olcDatabase={2}hdb,cn=config
# objectClass: olcConfig
# objectClass: olcMemberOf
# objectClass: olcOverlayConfig
# objectClass: top
# olcOverlay: {1}memberof
# EOF4

## FROM https://stackoverflow.com/questions/6372365/support-reverse-group-membership-maintenance-for-openldap-2-3
## inspect with: ldapsearch -b cn=config -D 'cn=root,cn=config' -W
## ldap_add: Insufficient access (50)
#
# $generate_ldif && cat <<EOF4 > $ldif/11_memberof.ldif
# dn: cn=module{0},cn=config
# objectClass: olcModuleList
# cn: module{0}
# olcModulePath: /usr/lib/openldap
# olcModuleLoad: {0}memberof
# olcModuleLoad: {1}refint
# EOF4

# sometimes, hdb is mentioned instead of mdb - in newer openldap servers, it is mdb.
$generate_ldif && cat <<EOF16 > $ldif/16_db.ldif

dn: olcDatabase={1}mdb,cn=config
changetype: modify
replace: olcSuffix
olcSuffix: dc=jwqa,dc=org
-
replace: olcRootDN
olcRootDN: $admin_dn
-
replace: olcRootPW
olcRootPW: $admin_pass
EOF16

## the dc=jwqa,dc=org is commented out here, to avoid complains that it already exits.
$generate_ldif && cat <<EOF18 > $ldif/18_ou.ldif

# dn: dc=jwqa,dc=org
# objectClass: top
# objectClass: dcObject
# objectClass: organization
# o: jwqa
# dc: jwqa
# -
dn: ou=users,dc=jwqa,dc=org
objectClass: organizationalUnit
ou: users

dn: ou=groups,dc=jwqa,dc=org
objectClass: organizationalUnit
ou: groups

EOF18

$generate_ldif && cat << EOF19 > $ldif/19_samaccount_schema.ldif
# This is a schema extension.
# We add private attributes to objectclass jwextra. the class is loaded at startup already,
# because I have not found a ways to load it with ldapadd during runtime. I always get permission denied.
#
# To use these attributes
# - run ldapadd to load the file
# - create a new object and add jwextra to its list of objectclasses.
#
# 1.3.6.1.4.1.39430	is the owncloud OID schema prefix.
#  - we use 1.1.10, 1.1.11, 1.1.12, ... for attributes
#  - and 1.3.2 for the class name
dn: cn=samaccount,cn=schema,cn=config
objectClass: olcSchemaConfig
cn: samaccount
olcAttributeTypes: ( 1.3.6.1.4.1.39430.1.1.4 NAME 'sAMAccountName' DESC 'Originally from LSDN, but openldap does not have that field.' EQUALITY caseIgnoreMatch SUBSTR caseIgnoreSubstringsMatch SYNTAX 1.3.6.1.4.1.1466.115.121.1.15 SINGLE-VALUE )
olcObjectClasses: ( 1.3.6.1.4.1.39430.1.3.2 NAME 'samaccount' DESC 'samaccount LDAP Schema' AUXILIARY MAY ( sAMAccountName ) )
EOF19

$generate_ldif && cat <<EOF20 > $ldif/20_users.ldif

# Start dn with uid (user identifier / login), not cn (Firstname + Surname)
dn: uid=einstein,ou=users,dc=jwqa,dc=org
objectClass: inetOrgPerson
objectClass: organizationalPerson
objectClass: person
objectClass: posixAccount
objectClass: top
objectClass: samaccount
uid: einstein
givenName: Albert
sn: Einstein
cn: albert-einstein
sAMAccountName: AlbertEinstein
displayName: Albert Einstein
description: A German-born theoretical physicist who developed the theory of relativity, one of the two pillars of modern physics (alongside quantum mechanics).
mail: einstein@jwqa.org
uidNumber: 20000
gidNumber: 30000
homeDirectory: /home/einstein
userPassword:: e1NTSEF9TXJEcXpFNGdKbXZxbVRVTGhvWEZ1VzJBbkV3NWFLK3J3WTIvbHc9PQ==


dn: uid=marie,ou=users,dc=jwqa,dc=org
objectClass: inetOrgPerson
objectClass: organizationalPerson
objectClass: person
objectClass: posixAccount
objectClass: top
objectClass: samaccount
uid: marie
givenName: Marie
sn: Curie
cn: marie-curie
sAMAccountName: MarieCurie
displayName: Marie Skłodowska Curie
description: A Polish and naturalized-French physicist and chemist who conducted pioneering research on radioactivity.
mail: marie@jwqa.org
uidNumber: 20001
gidNumber: 30000
homeDirectory: /home/marie
userPassword:: e1NTSEF9UmFvQWs3TU9jRHBIUWY3bXN3MGhHNnVraFZQWnRIRlhOSUNNZEE9PQ==

dn: uid=richard,ou=users,dc=jwqa,dc=org
objectClass: inetOrgPerson
objectClass: organizationalPerson
objectClass: person
objectClass: posixAccount
objectClass: top
objectClass: samaccount
uid: richard
givenName: Richard
sn: Feynman
cn: richard-feynman
sAMAccountName: RichardFeynman
displayName: Richard Phillips Feynman
description: An American theoretical physicist, known for his work in the path integral formulation of quantum mechanics, the theory of quantum electrodynamics, the physics of the superfluidity of supercooled liquid helium, as well as his work in particle physics for which he proposed the parton model.
mail: richard@jwqa.org
uidNumber: 20002
gidNumber: 30000
homeDirectory: /home/richard
userPassword:: e1NTSEF9Z05LZTRreHdmOGRUREY5eHlhSmpySTZ3MGxSVUM1d1RGcWROTVE9PQ==

# userPassword for Jeff Moss is hacker
# It can be generated with: slappasswd -h '{SSHA}' -s hacker | tr -d '\n' | base64
dn: uid=jeff,ou=users,dc=jwqa,dc=org
objectClass: inetOrgPerson
objectClass: organizationalPerson
objectClass: person
objectClass: posixAccount
objectClass: top
objectClass: samaccount
uid: moss
givenName: Jeff
sn: Moss
cn: jeff-moss
sAMAccountName: JeffMoss
displayName: Jeff Moss
description: Jeff Moss (born January 1, 1975), also known as Dark Tangent, is an American hacker, computer and internet security expert who founded the Black Hat and DEF CON computer security conferences.
mail: jeff@jwqa.org
uidNumber: 20002
gidNumber: 30000
homeDirectory: /home/jeff
userPassword:: e1NTSEF9UllCcE1EdXlqTk92RjFxMlVzUHlXbHpMK1pLSE1NcjM=
EOF20

$generate_ldif && cat <<EOF30 > $ldif/30_groups.ldif

## From https://stackoverflow.com/questions/8937248/ldap-error-invalid-structural-object-class-chain-organizationalunit-referral
## The objectClass: extensibleObject allows us to have multiple objectClasses.
## Without that, we always get "Object class violation (65): invalid structural object class chain (groupOfUniqueNames/posixGroup)"
##
## posixGroup is a 'structural object class', but does not allow the 'uniqueMember' attribute.
## groupOfUniqueNames is a 'structural object class', but does not allow the 'gidNumber' attribute.
## We can use one of the two, combined with 'objectClasses: extensibleObject' - to allow foreign attributes.
dn: cn=physics-lovers,ou=groups,dc=jwqa,dc=org
objectClass: top
objectClass: extensibleObject
objectClass: posixGroup
# objectClass: groupOfUniqueNames
cn: physics-lovers
description: Physics lovers
gidNumber: 30007
uniqueMember: uid=einstein,ou=users,dc=jwqa,dc=org
uniqueMember: uid=marie,ou=users,dc=jwqa,dc=org
uniqueMember: uid=richard,ou=users,dc=jwqa,dc=org

dn: cn=users,ou=groups,dc=jwqa,dc=org
#objectClass: groupOfUniqueNames
objectClass: extensibleObject
objectClass: posixGroup
objectClass: top
cn: users
description: All LDAP users
gidNumber: 30000
uniqueMember: uid=einstein,ou=users,dc=jwqa,dc=org
uniqueMember: uid=marie,ou=users,dc=jwqa,dc=org
uniqueMember: uid=richard,ou=users,dc=jwqa,dc=org
uniqueMember: uid=jeff,ou=users,dc=jwqa,dc=org
uniqueMember: uid=admin,ou=users,dc=jwqa,dc=org

dn: cn=hackers,ou=groups,dc=jwqa,dc=org
# objectClass: groupOfUniqueNames
objectClass: extensibleObject
objectClass: posixGroup
objectClass: top
cn: hackers
description: Hackers
gidNumber: 30002
uniqueMember: uid=jeff,ou=users,dc=jwqa,dc=org


## The hackers group is nested in the sailors group.
## Therefore jeff should see things that are shared with sailors.
dn: cn=sailors,ou=groups,dc=jwqa,dc=org
# objectClass: groupOfUniqueNames
objectClass: extensibleObject
objectClass: posixGroup
objectClass: top
cn: sailors
description: Sailing ship lovers
gidNumber: 30001
uniqueMember: uid=einstein,ou=users,dc=jwqa,dc=org
uniqueMember: cn=hackers,ou=groups,dc=jwqa,dc=org
EOF30

$generate_ldif && cat << EOF40 > $ldif/40_jwextra_schema.ldif
# This is a schema extension.
# We add private attributes to objectclass jwextra. the class is loaded at startup already,
# because I have not found a ways to load it with ldapadd during runtime. I always get permission denied.
#
# To use these attributes
# - run ldapadd to load the file
# - create a new object and add jwextra to its list of objectclasses.
#
# 1.3.6.1.4.1.39430	is the owncloud OID schema prefix.
#  - we use 1.1.10, 1.1.11, 1.1.12, ... for attributes
#  - and 1.3.2 for the class name
dn: cn=jwextra,cn=schema,cn=config
objectClass: olcSchemaConfig
cn: jwextra
olcAttributeTypes: ( 1.3.6.1.4.1.39430.1.1.10 NAME 'color' DESC 'A generic name attribute.' EQUALITY caseIgnoreMatch SUBSTR caseIgnoreSubstringsMatch SYNTAX 1.3.6.1.4.1.1466.115.121.1.15 SINGLE-VALUE )
olcAttributeTypes: ( 1.3.6.1.4.1.39430.1.1.11 NAME 'fixID' DESC 'For testing custom attributes.' EQUALITY caseIgnoreMatch SUBSTR caseIgnoreSubstringsMatch SYNTAX 1.3.6.1.4.1.1466.115.121.1.15 SINGLE-VALUE )
olcObjectClasses: ( 1.3.6.1.4.1.39430.1.3.3 NAME 'jwextra' DESC 'jwextra LDAP Schema' AUXILIARY MAY ( color $ fixID ) )
EOF40

# -------------------------- begin of lemmings generator
function generate_user()
{
  namepre=$1
  namecnt=$2
  groupname=$2
  userPassword=e1NTSEF9WHlSZjJxcnMycXhSbkM4emVVV3lOMWVtVENqOVB0RVIK	# slappasswd -s secret | base64
  ucfirst=$(echo $namepre | sed -e 's/./\U&/')
  uidNumber=$(expr 20000 + $namecnt)
  color=$(shuf -e red green blue white red -n 1)	# 40% red, 20% green, blue, white

cat << EOU

# Start dn with uid (user identifier / login), not cn (Firstname + Surname)
dn: uid=$namepre$namecnt,ou=users,dc=jwqa,dc=org
objectClass: inetOrgPerson
objectClass: organizationalPerson
objectClass: person
objectClass: posixAccount
objectClass: top
objectClass: samaccount
objectClass: jwextra
uid: $namepre$namecnt
givenName: N$namecnt
sn: $ucfirst
cn: n$namecnt-$namepre
sAMAccountName: N$namecnt$ucfirst
displayName: N$namecnt $ucfirst
description: Number $namecnt of $ucfirst.
mail: $namepre$namecnt@jwqa.org
uidNumber: $uidNumber
gidNumber: 30000
homeDirectory: /home/$namepre$namecnt
userPassword:: $userPassword
color: $color

EOU
}

function generate_users_and_group()
{
  namepre=$1
  cnt_from=$2
  cnt_to=$3
  groupname=$3

  echo 1>&2 "+ generate_users_and_group $1 $2 ..."
  for u in $(seq -w $cnt_from $cnt_to); do
    generate_user $namepre $u $groupname
  done

  ucfirst=$(echo $namepre | sed -e 's/./\U&/')
  gidNumber=$(expr 30000 + $(echo $3 | sum | head -c 3))

  cat << EOG

dn: cn=${groupname}s,ou=groups,dc=jwqa,dc=org
objectClass: top
objectClass: extensibleObject
objectClass: posixGroup
# objectClass: groupOfUniqueNames
cn: group$groupname
description: $ucfirst group
gidNumber: $gidNumber
EOG

  for g in $(seq -w $cnt_from $cnt_to); do
    echo "uniqueMember: uid=$namepre$g,ou=users,dc=jwqa,dc=org"
  done
  echo ""
}

if $generate_ldif; then
  generate_users_and_group lemming  0 009 lem0  >  $ldif/45_lem100.ldif
  generate_users_and_group lemming 10 019 lem1  >> $ldif/45_lem100.ldif
  generate_users_and_group lemming 20 029 lem2  >> $ldif/45_lem100.ldif
  generate_users_and_group lemming 30 039 lem3  >> $ldif/45_lem100.ldif
  generate_users_and_group lemming 40 049 lem4  >> $ldif/45_lem100.ldif
  generate_users_and_group lemming 50 059 lem5  >> $ldif/45_lem100.ldif
  generate_users_and_group lemming 60 069 lem6  >> $ldif/45_lem100.ldif
  generate_users_and_group lemming 70 079 lem7  >> $ldif/45_lem100.ldif
  generate_users_and_group lemming 80 089 lem8  >> $ldif/45_lem100.ldif
  generate_users_and_group lemming 90 099 lem9  >> $ldif/45_lem100.ldif
  generate_users_and_group rabbit  1 100 rabbit >> $ldif/45_lem100.ldif
fi
# -------------------------- end of lemmings generator

ports="-p $ldapport:389 -p $ldapsport:636"
mount="$ldif:/container/service/slapd/assets/config/bootstrap/ldif/custom"
opts="-v $mount $ports --env LDAP_CONFIG_PASSWORD=$admin_pass --env LDAP_ADMIN_PASSWORD=$admin_pass --env LDAP_ORGANISATION=JW-QA-org --env LDAP_DOMAIN=jwqa.org --env LDAP_READONLY_USER=true"

docker container inspect -f 'openldap is already running' openldap 2> /dev/null && {
  echo " - to reload try:"
  echo "    docker kill openldap; docker rm openldap"
  echo "    docker run --rm --name openldap $opts osixia/openldap --copy-service --loglevel debug"
  exit 0
}


docker run --rm --name openldap $opts -d osixia/openldap --copy-service --loglevel debug
sleep 5
ldapserver=$(docker inspect openldap | jq '.[0].NetworkSettings.IPAddress' -r)

if [ "$ldapserver" == "null" ]; then
  echo "ERROR: failed to start openldap, retrying without --rm and --detach for better diagnostics."
  sleep 2
  set -x
  docker run --name openldap $opts osixia/openldap --copy-service --loglevel debug
  set +x
  sleep 2
  echo ""
  echo "ERROR: failed to start openldap ... when done inspecting the issue, please clean up with: docker rm openldap"
  echo "retry: docker run --rm --name openldap $opts osixia/openldap --copy-service --loglevel debug"
  exit 0
fi

ldapsearch -x -H ldap://$ldapserver -b dc=jwqa,dc=org -D "$admin_dn" -w "$admin_pass" -v

docker run --rm -p 6443:443 --name phpldapadmin-server --env PHPLDAPADMIN_LDAP_HOSTS=$ldapserver --detach osixia/phpldapadmin

cat << EOF6
-----------------------------------------------
Connect to php ldapadmin:
  https://$(hostname -I  | sed -e 's/ .*//'):6443
  Login DN: $admin_dn
  Password: $admin_pass
EOF6

cat << EOF7
-----------------------------------------------

 ldapsearch -x -H ldap://$ldapserver -D $admin_dn -w $admin_pass -b dc=jwqa,dc=org '(uid=lemming012)'

   uidNumber: 2012
   gidNumber: 30000
   homeDirectory: /home/lemming012
   color: blue

 ldapsearch -x -H ldap://$ldapserver -D $admin_dn -w $admin_pass -b ou=groups,dc=jwqa,dc=org '(objectClass=*)' dn uniqueMember

   # sailors, groups, jwqa.org
   dn: cn=sailors,ou=groups,dc=jwqa,dc=org
   uniqueMember: uid=einstein,ou=users,dc=jwqa,dc=org
   uniqueMember: cn=hackers,ou=groups,dc=jwqa,dc=org
   ...

Extend the LDAP Schema
 - Edit ~/ldif/40_jwextra_schema.ldif
	For each attribute add an olcAttributeTypes line.
	Make sure all attributes in the file are listed in the olcObjectClasses line.
 - run (FIXME: ldapadd always fails. We must docker kill and restart)
	ldapadd -H ldap://$ldapserver -D "$admin_dn" -w "$admin_pass" -v -f ldif/40_jwextra_schema.ldif
 - Then create objects that inherit from objectclass jwextra or add jwextra to te objectclass list of existing objects.
 - Then ldapadmin should allow the new attributes for 'Add new attribute'
 - to update an existing Schema, (FIXME: ldapmodify always fails. Must docker kill and restart...)
    - Edit the file to include the line 'changetype: modify' as the second line.
    - Run
	ldapmodify -H ldap://$ldapserver -D "$admin_dn" -w "$admin_pass" -v -f ldif/40_jwextra_schema.ldif
      still fails to update... No such object, Insufficient access, or similar.
EOF7


