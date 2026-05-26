#!/usr/bin/env python3
import os
import sys
import argparse
import json
import requests
from urllib.parse import urljoin

def get_api_base_url(site_id):
    """Construct the base URL for the Checkmk API."""
    # Checkmk 2.0+ API usually lives at /check_mk/api/1.0
    # Adjust if your installation uses a different path (e.g., /my_cmk/check_mk/api/1.0)
    base = os.environ.get('CMK_BASE_URL', 'http://localhost')
    return f"{base}/{site_id}/check_mk/api/1.0"

def login(api_url, user, password):
    """Perform basic auth and return headers."""
    return {
        "Authorization": f"Bearer {password}", 
        # Note: In newer CK versions, you might need to generate a token via API first, 
        # but basic auth or bearer token with password often works for scripts if configured.
        # However, the standard way for 2.0+ is often:
        # Authorization: Bearer <TOKEN> where token is generated via /auth/token
        # But for simplicity in scripts, many use:
        # Authorization: Basic <base64(user:pass)>
        # Let's stick to the most robust method for 2.0+: Basic Auth converted to Bearer if needed, 
        # or just Basic Auth if the server accepts it.
        # Actually, Checkmk 2.0+ prefers Bearer tokens. Let's try to get one or use Basic.
        # For this script, we will use Basic Auth header which is widely supported for CLI tools.
        "Authorization": f"Basic {requests.auth._basic_auth_str(user, password)}"
    }
    # Correction: Checkmk 2.0+ API often requires a Bearer token generated via /auth/token endpoint.
    # Let's implement the token generation flow for maximum compatibility.
    pass

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
        print(f"Response: {resp.text}")
        sys.exit(1)

def fetch_hosts_by_domain(api_url, headers, old_domain):
    """Fetch all hosts that match the old domain."""
    # The API endpoint for listing hosts
    list_url = urljoin(api_url, "domain_objects/host")
    
    # We need to filter. The API supports filtering via query params or body.
    # For 2.0+, we can use the 'filter' query param or POST with a filter object.
    # Let's use the GET with query parameters for simplicity if supported, 
    # otherwise we fetch all and filter locally (less efficient but safer for complex filters).
    # Better: Use the specific filter syntax.
    
    # Checkmk API Filter syntax: ?filter={"op": "and", "conditions": [...]}
    # We want: attributes.domain == old_domain
    
    filter_obj = {
        "op": "and",
        "conditions": [
            {"op": "=", "field": "attributes.domain", "value": old_domain}
        ]
    }
    
    params = {
        "filter": json.dumps(filter_obj)
    }
    
    # Note: Some versions require the filter in the body for POST, but GET with filter param is standard for listing.
    # If GET fails, we might need to POST to /list.
    # Let's try the standard GET first.
    
    resp = requests.get(list_url, headers=headers, params=params)
    
    if resp.status_code != 200:
        # Fallback: Try POST to /list if GET with filter fails (common in older 2.0 patches)
        list_url_post = urljoin(api_url, "domain_objects/host/list")
        payload = {
            "filter": filter_obj,
            "sort": [],
            "expand": ["attributes"]
        }
        resp = requests.post(list_url_post, headers=headers, json=payload)
        
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
        "set_attributes": True # Ensure we are setting, not merging partially
    }
    
    resp = requests.put(edit_url, headers=headers, json=payload)
    
    if resp.status_code not in [200, 204]:
        print(f"Failed to update host {host_id}: {resp.status_code} - {resp.text}")
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

def main():
    parser = argparse.ArgumentParser(description="Migrate Checkmk hosts to a new domain.")
    parser.add_argument("--old-domain", required=True, help="Current top-level domain (e.g., foo.bar.oldtop)")
    parser.add_argument("--new-domain", required=True, help="New top-level domain (e.g., newdomain.newtop)")
    parser.add_argument("--site-id", required=True, help="Checkmk Site ID (e.g., cmk_site)")
    
    args = parser.parse_args()

    # Environment Variables
    user = os.environ.get("CMK_API_USER")
    password = os.environ.get("CMK_API_PASS")
    
    if not user or not password:
        print("Error: CMK_API_USER and CMK_API_PASS must be set in environment variables.")
        sys.exit(1)

    api_url = get_api_base_url(args.site_id)
    
    # Step 1: Get Token
    print(f"Authenticating to {api_url}...")
    token = get_bearer_token(api_url, user, password)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Step 2: Fetch Hosts
    print(f"Fetching hosts with domain: {args.old_domain}...")
    hosts = fetch_hosts_by_domain(api_url, headers, args.old_domain)
    
    if not hosts:
        print("No hosts found with the specified domain.")
        return

    print(f"Found {len(hosts)} hosts to migrate.")
    
    # Step 3: Update Hosts
    success_count = 0
    for host in hosts:
        host_id = host.get("id")
        host_name = host.get("name")
        
        print(f"Updating {host_name} ({host_id})...")
        if update_host_domain(api_url, headers, host_id, args.new_domain):
            success_count += 1
        else:
            print(f"  -> FAILED")
            
    print(f"Updated {success_count}/{len(hosts)} hosts.")
    
    if success_count > 0:
        # Step 4: Activate Changes
        print("Activating changes...")
        if activate_changes(api_url, headers, args.site_id):
            print("Changes activated successfully.")
        else:
            print("WARNING: Changes were updated but activation failed.")
    else:
        print("No changes made, skipping activation.")

if __name__ == "__main__":
    main()
