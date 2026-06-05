#!/usr/bin/env python3
"""
Create or update GitHub Issues for the 85 enriched KajianLive profiles
to keep a historical log of their bio changes and profile completeness.
"""
import json
import subprocess
import time
import sys
from datetime import datetime, timezone, timedelta

CONTAINER = "profilasatidz"
MASTER_FILE = "/root/asatidz_master.json"
JAKARTA_TZ = timezone(timedelta(hours=7))

def log(msg):
    ts = datetime.now(JAKARTA_TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def docker_exec(cmd):
    """Run command inside container, return (stdout, returncode)"""
    result = subprocess.run(
        ["docker", "exec", CONTAINER, "sh", "-c", cmd],
        capture_output=True, text=True, timeout=120
    )
    return result.stdout.strip(), result.returncode

def update_github_issue(profile_id, profile_name, entry):
    """Create or update GitHub Issue for a profile."""
    try:
        slug = entry.get("slug", "")
        count = entry.get("count", 0)
        has_bio = entry.get("has_bio", False)
        has_detail = entry.get("has_detail", False)
        completeness = entry.get("completeness", 0)
        
        body_lines = [
            f"## {profile_name}",
            f"",
            f"- **ID**: `{profile_id}`",
            f"- **Slug**: `{slug}`",
            f"- **Sumber OSINT**: KajianLive",
            f"- **Jumlah Kajian**: {count}",
            f"- **Bio**: {'✅' if has_bio else '❌'}",
            f"- **Detail**: {'✅' if has_detail else '❌'}",
            f"- **Completeness**: {completeness}%",
            f"",
            f"---",
            f"*Last updated: {datetime.now(JAKARTA_TZ).strftime('%Y-%m-%d %H:%M')} WIB*",
        ]
        body = "\n".join(body_lines)
        
        title = f"[Profil Asatidz] {profile_name}"
        labels = "profil-asatidz"
        
        # Check if issue already exists
        result = subprocess.run(
            ["gh", "issue", "list", "--repo", "camagenta/profilasatidz",
             "--search", f'"{title}"', "--state", "open", "--json", "number,title",
             "--limit", "1"],
            capture_output=True, text=True, timeout=15
        )
        
        existing = []
        if result.returncode == 0 and result.stdout.strip():
            try:
                existing = json.loads(result.stdout)
            except:
                pass
        
        if existing:
            # Update existing issue
            issue_num = existing[0]["number"]
            update_result = subprocess.run(
                ["gh", "issue", "edit", str(issue_num), "--repo", "camagenta/profilasatidz",
                 "--body", body],
                capture_output=True, text=True, timeout=15
            )
            if update_result.returncode == 0:
                log(f"  ✓ Issue #{issue_num} updated: {profile_name}")
            else:
                log(f"  ✗ Issue update failed: {update_result.stderr[:100]}")
        else:
            # Create new issue
            create_result = subprocess.run(
                ["gh", "issue", "create", "--repo", "camagenta/profilasatidz",
                 "--title", title, "--body", body, "--label", labels],
                capture_output=True, text=True, timeout=15
            )
            if create_result.returncode == 0:
                log(f"  ✓ Issue created: {profile_name}")
            else:
                log(f"  ✗ Issue create failed: {create_result.stderr[:100]}")
                
    except Exception as e:
        log(f"  ✗ GitHub Issue error: {e}")

def main():
    log("=== KajianLive GitHub Issue Documentation ===")
    
    # Load mapping
    with open('kajianlive_mapping.json') as f:
        mapping_data = json.load(f)
        
    # Get matches with score >= 1.0
    targets = [m for m in mapping_data['mapping'] if m['match_score'] >= 1.0]
    log(f"Loaded {len(targets)} target profiles.")
    
    # Load master from container to get the updated status (completeness, has_bio, etc.)
    master_json, rc = docker_exec(f"cat {MASTER_FILE}")
    if rc != 0:
        log("ERROR: Cannot read master file from container")
        sys.exit(1)
    master = json.loads(master_json)
    master_dict = {m['id']: m for m in master}
    
    total = len(targets)
    for i, t in enumerate(targets):
        profile_id = t['kajian_net']['id']
        name = t['kajian_net']['name']
        
        entry = master_dict.get(profile_id)
        if not entry:
            log(f"[{i+1}/{total}] WARNING: {profile_id} not found in master index")
            continue
            
        log(f"[{i+1}/{total}] Documenting {name}...")
        update_github_issue(profile_id, name, entry)
        
        # Delay to avoid hitting GitHub API secondary limits
        time.sleep(2.0)
        
    log("=== GitHub Issue documentation complete! ===")

if __name__ == "__main__":
    main()
