#! /bin/bash

name="$1"
hostcount=5

if [ -z "$name" ]; then
  echo
  echo "Usage: $0 nameprefix"
  echo
  exit 1
fi

for i in $(seq 0 $(($hostcount - 1)) ); do (set -x; hetzner_dns del      $name$i); done
for i in $(seq 0 $(($hostcount - 1)) ); do (set -x; hcloud server delete $name$i); done
for i in $(seq 0 $(($hostcount - 1)) ); do (set -x; hcloud volume delete $name$i-osd); done
(set -x; hcloud network delete $name-cluster)

