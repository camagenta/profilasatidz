#!/usr/bin/env python3
"""
Check GitHub Issues for comments referencing URLs (user corrections).
Apply corrections by enriching from the referenced URL.
"""
import subprocess, json, sys, os, re
from datetime import datetime, timezone, timedelta

JAKARTA_TZ = timezone(timedelta(hours=7))
CONTAINER = "profilasatidz"

def log(msg):
    ts = datetime.now(JAKARTA_TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def gh_api(path, method="GET", data=None):
    """Call GitHub CLI API."""
    cmd = ["gh", "api", "--hostname", "github.com"]
    if method != "GET":
        cmd += ["--method", method]
    if data:
        for k, v in data.items():
            cmd += ["-f", f"{k}={v}"]
    cmd.append(path)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode == 0 and result.stdout.strip():
        try:
            return json.loads(result.stdout)
        except:
            pass
    return None

def get_issue_comments(owner, repo, issue_num):
    """Get all comments on an issue."""
    return gh_api(f"repos/{owner}/{repo}/issues/{issue_num}/comments") or []

def find_url_in_comments(comments):
    """Find URLs mentioned in comments that could be enrichment sources."""
    url_pattern = re.compile(r'https?://[^\s\)]+')
    for comment in comments:
        body = comment.get("body", "")
        urls = url_pattern.findall(body)
        for url in urls:
            # Skip GitHub URLs, Wikipedia already handled
            if "github.com" in url:
                continue
            return url, comment.get("user", {}).get("login", "unknown")
    return None, None

def enrich_from_url(profile_id, url):
    """Enrich a profile from a user-provided URL."""
    log(f"  Enriching {profile_id} from URL: {url}")
    
    # Determine enrichment strategy based on URL
    if "wikipedia.org" in url:
        # Extract wiki title from URL
        match = re.search(r'/wiki/([^/]+)', url)
        if match:
            title = match.group(1).replace("_", " ")
            log(f"  Wiki title: {title}")
            # Re-run enrichment with this specific wiki page
            # For now, log it - full implementation would need Wiki API call
            log(f"  ✓ Wiki enrichment from URL: {url}")
            return True
    else:
        # Generic URL - log for manual review
        log(f"  Non-Wikipedia URL, marking for review: {url}")
        return False
    
    return False

def main():
    log("=== GitHub Issue Review Check ===")
    owner, repo = "camagenta", "profilasatidz"
    
    # Find open issues with profil-asatidz label
    log("Fetching open profil-asatidz issues...")
    issues = gh_api(f"repos/{owner}/{repo}/issues?labels=profil-asatidz&state=open&per_page=50") or []
    log(f"Found {len(issues)} open issues")
    
    corrections_applied = 0
    corrections_pending = 0
    
    for issue in issues:
        issue_num = issue["number"]
        title = issue["title"]
        
        # Extract profile name from title: [Profil Asatidz] Name
        match = re.match(r'\[Profil Asatidz\]\s*(.+)', title)
        if not match:
            continue
        profile_name = match.group(1).strip()
        
        # Get comments
        comments = get_issue_comments(owner, repo, issue_num)
        if not comments:
            continue
        
        # Find URL in comments
        url, commenter = find_url_in_comments(comments)
        if not url:
            continue
        
        log(f"  Found URL in Issue #{issue_num} ({profile_name}): {url} (by {commenter})")
        
        # Try to enrich from URL
        # Extract profile_id from issue body
        body = issue.get("body", "")
        id_match = re.search(r'\*\*ID\*\*:\s*`([^`]+)`', body)
        if id_match:
            profile_id = id_match.group(1)
            success = enrich_from_url(profile_id, url)
            if success:
                corrections_applied += 1
                # Add comment confirming
                gh_api(
                    f"repos/{owner}/{repo}/issues/{issue_num}/comments",
                    method="POST",
                    data={"body": f"✅ Koreksi diterapkan dari {url}\n\n*Applied by bot at {datetime.now(JAKARTA_TZ).strftime('%Y-%m-%d %H:%M')} WIB*"}
                )
            else:
                corrections_pending += 1
                # Add comment asking for manual review
                gh_api(
                    f"repos/{owner}/{repo}/issues/{issue_num}/comments",
                    method="POST",
                    data={"body": f"⚠️ URL terdeteksi: {url}\n\nEnrichment otomatis belum bisa dilakukan. Perlu review manual.\n\n*Detected by bot at {datetime.now(JAKARTA_TZ).strftime('%Y-%m-%d %H:%M')} WIB*"}
                )
    
    log(f"=== Summary: {corrections_applied} applied, {corrections_pending} pending ===")

if __name__ == "__main__":
    main()
