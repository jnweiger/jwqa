#!/usr/bin/env python3
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
    parser = argparse.ArgumentParser(description="Migrate Checkmk hosts to a new domain or list them.")
    parser.add_argument("--old-domain", required=False, help="Current top-level domain to filter (e.g., foo.bar.oldtop). If omitted, lists ALL hosts.")
    parser.add_argument("--new-domain", required=False, help="New top-level domain to set (e.g., newdomain.newtop). If omitted, runs in LIST-ONLY mode.")
    parser.add_argument("--site-id", required=True, help="Checkmk Site ID (e.g., cmk_site)")

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
    # ... after getting token ...
    if not check_version(api_url, headers):
        print("Proceeding anyway, but version check failed.")

    # Step 2: Determine Mode
    is_update_mode = bool(args.new_domain)
    filter_desc = f"Domain: {args.old_domain}" if args.old_domain else "ALL HOSTS"

    print(f"Mode: {'UPDATE' if is_update_mode else 'LIST-ONLY'}")
    print(f"Filter: {filter_desc}")
    if args.old_domain and not is_update_mode:
        print(f"Action: Listing hosts that would be changed from '{args.old_domain}' to '{args.new_domain}' (but no change will be made).")
    elif not args.old_domain and not is_update_mode:
        print(f"Action: Listing ALL hosts.")

    # Step 3: Fetch Hosts
    print(f"Fetching hosts...")
    hosts = fetch_hosts(api_url, headers, args.old_domain)

    if not hosts:
        print("No hosts found matching the criteria.")
        return

    print(f"Found {len(hosts)} hosts.")
    print("-" * 60)

    # Step 4: Process
    if is_update_mode:
        # UPDATE MODE
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
            print("Activating changes...")
            if activate_changes(api_url, headers, args.site_id):
                print("Changes activated successfully.")
            else:
                print("WARNING: Updates succeeded, but activation failed.")
        else:
            print("No changes made, skipping activation.")

    else:
        # LIST-ONLY MODE
        print(f"{'Host Name':<40} | {'Current Domain':<30}")
        print("-" * 75)
        for host in hosts:
            host_name = host.get("name")
            current_domain = host.get("attributes", {}).get("domain", "N/A")

            # If old_domain was specified, we are showing who would change.
            # If old_domain was NOT specified, we are showing everyone.
            if args.old_domain:
                print(f"{host_name:<40} | {current_domain:<30} (Would change to: {args.new_domain})")
            else:
                print(f"{host_name:<40} | {current_domain:<30}")

        print("-" * 75)
        print(f"Total: {len(hosts)} hosts.")
        print("No changes were made. Use --new-domain to apply updates.")

if __name__ == "__main__":
    main()
