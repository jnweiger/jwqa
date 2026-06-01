#!/usr/bin/env python3
#
# (C) 2026 j.weigert@heinlein-support.de
#
# Environment variables used:
#
#   CMK_API_USER="automation_user"
#   CMK_API_PASS="your_secure_password_or_token"
#
#   CMK_BASE_URL="https://checkmk.yourcompany.com"	# default to http://localhost
#
# Requires:
#	pip install requests
#
#
# 
# Reference: 
#	- find -L . -type f -name \*.py  | xargs grep 'Bulk renaming of hosts'
#	  ./lib/check_mk/gui/wato/pages/host_rename.py:        return _("Bulk renaming of hosts")
#
# ATTENTION: Do not use this hosts_rename.py - the API only does a raw rename. There is 
# much more to renaming, as host names are used as primary keys in all places.


import os
import sys
import argparse
import json
import requests
from urllib.parse import urljoin



def get_api_base_url(site_id):
    """Construct the base URL for the Checkmk API."""
    base = os.environ.get('CMK_BASE_URL', 'http://localhost')
    # Ensure no trailing slash in base, then append site and api path
    return f"{base.rstrip('/')}/{site_id}/check_mk/api/1.0"


def get_bearer_token(api_url, user, password):
    """Get a Bearer token from Checkmk."""
    auth_url = urljoin(api_url, "auth/token")
    payload = {
        "username": user,
        "password": password
    }
    try:
        resp = requests.post(auth_url, json=payload)
        resp.raise_for_status()
        return resp.json().get("token")
    except requests.exceptions.HTTPError as e:
        print(f"Error getting token: {e}")
        print(f"Response: {e.response.text}")
        sys.exit(1)


def fetch_hosts(api_url, headers, old_domain=None):
    """Fetch hosts. If old_domain is None, fetches all hosts."""
    list_url = urljoin(api_url, "domain_objects/host/list")

    filter_obj = None
    if old_domain:
        filter_obj = {
            "op": "and",
            "conditions": [
                {"op": "=", "field": "attributes.domain", "value": old_domain}
            ]
        }

    payload = {
        "filter": filter_obj,
        "sort": [],
        "expand": ["attributes"]
    }

    # Checkmk 2.0+ usually expects POST for list with filters
    resp = requests.post(list_url, headers=headers, json=payload)

    if resp.status_code != 200:
        print(f"Failed to fetch hosts: {resp.status_code} - {resp.text}")
        sys.exit(1)

    data = resp.json()
    return data.get("value", [])


def update_host_domain(api_url, headers, host_id, new_domain):
    """Update a single host's domain."""
    edit_url = urljoin(api_url, f"domain_objects/host/{host_id}")

    payload = {
        "attributes": {
            "domain": new_domain
        },
        "set_attributes": True
    }

    resp = requests.put(edit_url, headers=headers, json=payload)

    if resp.status_code not in [200, 204]:
        print(f"  -> FAILED: {resp.status_code} - {resp.text}")
        return False
    return True

def activate_changes(api_url, headers, site_id):
    """Activate changes on the site."""
    activate_url = urljoin(api_url, "domain_objects/site_config/activate")

    payload = {
        "sites": [site_id],
        "force": False,
        "ignore_warnings": False
    }

    resp = requests.post(activate_url, headers=headers, json=payload)

    if resp.status_code != 200:
        print(f"Failed to activate changes: {resp.status_code} - {resp.text}")
        return False
    return True

def check_version(api_url, headers):
    """Check the API version to ensure compatibility."""
    version_url = urljoin(api_url, "version")
    try:
        resp = requests.get(version_url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            version = data.get("version", "unknown")
            print(f"Connected to Checkmk version: {version}")
            # Optional: Warn if version is too old
            if version.startswith("1."):
                print("Warning: This script is optimized for Checkmk 2.0+")
            return True
        else:
            print(f"Could not fetch version: {resp.status_code}")
            return False
    except Exception as e:
        print(f"Version check failed: {e}")
        return False


def main():
    desc= "CAUTION: This is an unfinished exercise. Renaming hosts in checkmk is hard. Please study ./lib/check_mk/gui/wato/pages/host_rename.py and then use\n\t Setup -> hosts Hosts -> Rename multiple hosts\n\n"
    print(desc)
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("--old-domain", required=False, help="Current top-level domain to filter. If omitted, lists ALL hosts.")
    parser.add_argument("--new-domain", required=False, help="New top-level domain to set. If omitted, runs in LIST-ONLY mode.")
    parser.add_argument("--site-id", required=True, help="Checkmk Site ID (e.g., cmk_site)")
    parser.add_argument("-n", "--no-op", action="store_true", help="Dry-run mode: Show what would change but do NOT update or activate.")
    parser.add_argument("--activate", action="store_true", help="Activate changes after updating. (Required to apply changes to the monitoring engine).")

    args = parser.parse_args()

    # Environment Variables
    user = os.environ.get("CMK_API_USER")
    password = os.environ.get("CMK_API_PASS")

    if not user or not password:
        print("Error: CMK_API_USER and CMK_API_PASS must be set in environment variables.")
        sys.exit(1)

    api_url = get_api_base_url(args.site_id)

    # Step 1: Authenticate
    print(f"Authenticating to {api_url}...")
    token = get_bearer_token(api_url, user, password)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    if not check_version(api_url, headers):
        print("Proceeding anyway, but version check failed.")

    # Step 2: Determine Mode
    is_update_mode = bool(args.new_domain)
    is_no_op = args.no_op
    is_activate = args.activate
    filter_desc = f"Domain: {args.old_domain}" if args.old_domain else "ALL HOSTS"

    if is_no_op:
        print("Mode: DRY-RUN")
    else:
        print(f"Mode: {'UPDATE' if is_update_mode else 'LIST-ONLY'}")

    print(f"Filter: {filter_desc}")

    # Step 3: Fetch Hosts
    print(f"Fetching hosts...")
    hosts = fetch_hosts(api_url, headers, args.old_domain)

    if not hosts:
        print(f"ERROR: No hosts found matching {filter_desc}")
        return

    print(f"OK: Found {len(hosts)} hosts.")

    # Step 4: Process
    if is_update_mode:
        if is_no_op:
            print(f"{'Host Name':<40} | {'Current Domain':<30} | {'New Domain':<30}")
            print("-" * 105)
            for host in hosts:
                host_name = host.get("name")
                current_domain = host.get("attributes", {}).get("domain", "N/A")
                print(f"{host_name:<40} | {current_domain:<30} | {args.new_domain:<30}")
            print(f"Total: {len(hosts)} hosts would be updated.")
            return

        # Actual Update
        success_count = 0
        for host in hosts:
            host_id = host.get("id")
            host_name = host.get("name")
            current_domain = host.get("attributes", {}).get("domain", "N/A")

            print(f"Updating: {host_name} ({current_domain} -> {args.new_domain})")
            if update_host_domain(api_url, headers, host_id, args.new_domain):
                success_count += 1
            else:
                print(f"  -> FAILED")

        print("-" * 60)
        print(f"Updated {success_count}/{len(hosts)} hosts.")

        if success_count > 0:
            if is_activate:
                print("Activating changes...")
                if activate_changes(api_url, headers, args.site_id):
                    print("Changes activated successfully.")
                else:
                    print("WARNING: Updates succeeded, but activation failed.")
            else:
                print("Changes updated in DB. You need to activate changes in the Web UI now.")
        else:
            print("No changes.")

    else:
        # LIST-ONLY MODE (No --new-domain provided)
        print(f"{'Host Name':<40} | {'Current Domain':<30}")
        print("-" * 75)
        for host in hosts:
            host_name = host.get("name")
            current_domain = host.get("attributes", {}).get("domain", "N/A")

            print(f"{host_name:<40} | {current_domain:<30}")

        print("-" * 75)
        print(f"Total: {len(hosts)} hosts.")
        print("No changes were made. Use --new-domain to apply updates.")

if __name__ == "__main__":
    main()
