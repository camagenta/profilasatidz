#!/usr/bin/env python3
"""
Check GitHub Issues for comments referencing URLs (user corrections).
Apply corrections by enriching from the referenced URL.
"""
import subprocess, json, sys, os, re
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wikifetch import verify_wikipedia_match

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

def find_contribution_in_comments(comments):
    """Find and parse community contributions in comments."""
    # Process from oldest to newest, find the first unprocessed one.
    # To determine if it's unprocessed, we check if there's a bot acknowledgment.
    bot_acks = [c.get("body", "") for c in comments if "✅ Koreksi diterapkan" in c.get("body", "") or "❌ Kontribusi ditolak" in c.get("body", "")]
    
    for comment in comments:
        body = comment.get("body", "")
        
        # Check for new contribution format
        if "## Kontribusi Komunitas" in body and "### Isi Kontribusi" in body:
            comment_id = comment.get("id")
            
            # Simple check if this exact comment ID was already acknowledged
            if any(str(comment_id) in ack for ack in bot_acks):
                continue
                
            # Check for reactions (Approval mechanism)
            reactions = comment.get("reactions", {})
            thumbs_up = reactions.get("+1", 0)
            thumbs_down = reactions.get("-1", 0)
            
            status = "pending"
            if thumbs_up > 0:
                status = "approved"
            elif thumbs_down > 0:
                status = "rejected"
                
            bagian_match = re.search(r'\*\*Bagian:\*\*\s*(.+)', body)
            bagian = bagian_match.group(1).strip() if bagian_match else ""
            
            content_match = re.search(r'### Isi Kontribusi\s*(.*?)(?:### Sumber Referensi|---)', body, re.DOTALL)
            content = content_match.group(1).strip() if content_match else ""
            
            url_match = re.search(r'### Sumber Referensi\s*(https?://[^\s]+)', body)
            url = url_match.group(1).strip() if url_match else ""
            
            return {
                "type": "direct_text",
                "status": status,
                "bagian": bagian,
                "content": content,
                "url": url,
                "user": comment.get("user", {}).get("login", "unknown"),
                "comment_id": comment_id
            }
            
        # Fallback: old generic URL extraction (only if no bot ack yet)
        if len(bot_acks) == 0:
            url_pattern = re.compile(r'https?://[^\s\)]+')
            urls = url_pattern.findall(body)
            for url in urls:
                if "github.com" not in url:
                    return {
                        "type": "url_only",
                        "status": "pending",  # Generic URLs still marked pending for manual review
                        "url": url,
                        "user": comment.get("user", {}).get("login", "unknown"),
                        "comment_id": comment.get("id")
                    }
    return None

def apply_direct_contribution(profile_id, contrib):
    """Apply direct text contribution to the profile JSON."""
    log(f"  Applying direct contribution for {profile_id}: {contrib['bagian']}")
    
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    try:
        import nyicil_enrich as ne
    except ImportError:
        sys.path.append('/home/ubuntu/profilasatidz')
        import nyicil_enrich as ne
        
    detail_path = f"{ne.DETAIL_DIR}/{profile_id}.json"
    
    # Read existing detail or create new
    out, rc = ne.docker_exec(f"cat '{detail_path}'")
    if rc == 0 and out.strip():
        result = json.loads(out)
    else:
        # Need master to get name
        master_json, _ = ne.docker_exec(f"cat {ne.MASTER_FILE}")
        master = json.loads(master_json)
        profile_name = "Unknown"
        for m in master:
            if m.get("id") == profile_id:
                profile_name = m.get("name")
                break
        result = {
            "id": profile_id,
            "name": profile_name,
            "bio": "", "education": [], "expertise": [], "kary": [],
            "social_media": {}, "sources": []
        }
    
    # Apply based on "Bagian"
    bagian = contrib["bagian"].lower()
    content = contrib["content"]
    
    source_entry = None
    if contrib["url"]:
        source_entry = {
            "id": f"contrib_{contrib['comment_id']}",
            "url": contrib["url"],
            "title": "Kontribusi Komunitas",
            "sitename": "Referensi Kontributor",
            "accessed": datetime.now(JAKARTA_TZ).strftime("%Y-%m-%d")
        }
        # Add source if not exists
        if not any(s.get("url") == contrib["url"] for s in result.get("sources", [])):
            result.setdefault("sources", []).append(source_entry)
            
    # Field mapping
    if "bio" in bagian:
        result["bio"] = content + (f"\n\n(Tambahan info: {result['bio']})" if result.get("bio") else "")
        if contrib["url"]: result["bio_source"] = contrib["url"]
    elif "foto" in bagian or "photo" in bagian or "gambar" in bagian:
        # URL of image is the contribution content
        new_foto = content.strip()
        existing_foto = result.get("foto", "").strip()
        # Quality heuristic: full-size Wikipedia images (no /thumb/ in path) win over thumbs
        new_is_thumb = "/thumb/" in new_foto
        existing_is_thumb = "/thumb/" in existing_foto
        if not existing_foto:
            result["foto"] = new_foto
            log(f"  + foto set (was empty)")
        elif new_is_thumb and not existing_is_thumb:
            log(f"  - Skipped foto update: existing is full-size, new is thumb (would downgrade)")
        elif existing_is_thumb and not new_is_thumb:
            result["foto"] = new_foto
            log(f"  + foto upgraded from thumb to full-size")
        else:
            result["foto"] = new_foto
            log(f"  + foto replaced (same quality tier)")
        if contrib["url"]: result["foto_source"] = contrib["url"]
    elif "pendidikan" in bagian:
        lines = [line.strip('- *') for line in content.split('\n') if line.strip()]
        result.setdefault("education", []).extend(lines)
        if contrib["url"]: result["education_source"] = contrib["url"]
    elif "karya" in bagian:
        lines = [line.strip('- *') for line in content.split('\n') if line.strip()]
        result.setdefault("kary", []).extend(lines)
        if contrib["url"]: result["kary_source"] = contrib["url"]
    elif "keahlian" in bagian or "topik" in bagian:
        words = [w.strip() for w in content.replace(',', '\n').split('\n') if w.strip()]
        result.setdefault("expertise", []).extend(words)
        if contrib["url"]: result["expertise_source"] = contrib["url"]
    elif "media sosial" in bagian or "social" in bagian or "sosmed" in bagian:
        # Format: "platform: url" per line, or single url
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        if not result.get("social_media"):
            result["social_media"] = {}
        for line in lines:
            if ':' in line:
                platform, url = line.split(':', 1)
                result["social_media"][platform.strip().lower()] = url.strip()
            elif lines.index(line) == 0 and len(lines) == 1 and line.startswith('http'):
                result["social_media"]["lainnya"] = line
        if contrib["url"]: result.setdefault("sources", [])
    elif "jabatan" in bagian or "posisi" in bagian:
        result["jabatan"] = content.strip()
    else:
        # Append to bio for "Lainnya" or unrecognized
        result["bio"] = (result.get("bio", "") + f"\n\nCatatan tambahan: {content}").strip()

    result["enriched_at"] = datetime.now(JAKARTA_TZ).isoformat()
    result["method"] = "community_contribution"
    
    # Save back to container
    detail_json = json.dumps(result, ensure_ascii=False, indent=2)
    import base64
    b64 = base64.b64encode(detail_json.encode()).decode()
    cmd = f"echo '{b64}' | base64 -d > '{detail_path}'"
    out, rc = ne.docker_exec(cmd)
    
    if rc == 0:
        log(f"  ✓ Detail saved: {detail_path}")

        # Update master.json to reflect new fields
        try:
            master_raw, mrc = ne.docker_exec(f"cat {ne.MASTER_FILE}")
            if mrc == 0 and master_raw.strip():
                master = json.loads(master_raw)
                for m in master:
                    if m.get("id") == profile_id:
                        m["has_bio"] = bool(result.get("bio"))
                        m["has_foto"] = bool(result.get("foto"))
                        m["has_detail"] = True
                        m["completeness"] = (
                            (35 if result.get("bio") else 0) +
                            (25 if result.get("foto") else 0) +
                            25 +
                            (15 if m.get("count", 0) > 0 else 0)
                        )
                        break
                master_json = json.dumps(master, ensure_ascii=False, indent=2)
                b64m = base64.b64encode(master_json.encode()).decode()
                ne.docker_exec(f"echo '{b64m}' | base64 -d > '{ne.MASTER_FILE}'")
                log(f"  ✓ Master updated (has_bio={result.get('bio','')[:0]!=''}, has_foto={bool(result.get('foto'))})")
        except Exception as e:
            log(f"  ⚠ Failed to update master: {e}")

        # Trigger Hot-Reload
        import urllib.request
        try:
            urllib.request.urlopen("http://localhost:8080/api/reload", timeout=5)
            log("  ✓ Server hot-reloaded successfully")
        except Exception as e:
            log(f"  ⚠ Failed to trigger hot-reload: {e}")

        return True
    return False

def enrich_from_url(profile_id, url):
    """Enrich a profile from a user-provided URL."""
    log(f"  Enriching {profile_id} from URL: {url}")
    
    # Add paths so we can import nyicil_enrich
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    try:
        import nyicil_enrich as ne
    except ImportError:
        sys.path.append('/home/ubuntu/profilasatidz')
        import nyicil_enrich as ne
    
    # Determine enrichment strategy based on URL
    if "wikipedia.org" in url:
        # Extract wiki title from URL
        match = re.search(r'/wiki/([^/]+)', url)
        if match:
            import urllib.parse
            title = urllib.parse.unquote(match.group(1)).replace("_", " ")
            log(f"  Wiki title extracted: {title}")
            
            # Fetch Wikipedia extract
            lang = "en" if ".en.wikipedia.org" in url or "/en." in url else "id"
            wiki_text = ne.wiki_extract(title, lang)
            
            if wiki_text:
                bio = ne.extract_bio_from_wiki(wiki_text)
                educations = ne.extract_pendidikan(wiki_text)
                expertise = ne.extract_keahlian(wiki_text)
                
                # Fetch name from master to verify
                master_json, rc = ne.docker_exec(f"cat {ne.MASTER_FILE}")
                if rc != 0:
                    log("  ✗ Failed to read master file from container")
                    return False
                master = json.loads(master_json)
                
                profile_name = "Unknown"
                target_entry = None
                for entry in master:
                    if entry.get("id") == profile_id:
                        profile_name = entry.get("name")
                        target_entry = entry
                        break

                if not verify_wikipedia_match(profile_name, title, wiki_text[:500]):
                    log(f"  ✗ Lesson #14 guard: Wikipedia page '{title}' does not match profile '{profile_name}' — refusing to save")
                    return False

                # Build result
                result = {
                    "name": profile_name,
                    "source_url": target_entry.get("source_url", "") if target_entry else "",
                    "bio": bio,
                    "education": educations,
                    "expertise": expertise,
                    "kary": [],
                    "social_media": {},
                    "sources": [{
                        "id": "wiki_id",
                        "url": url,
                        "title": title,
                        "sitename": f"Wikipedia Bahasa {'Inggris' if lang == 'en' else 'Indonesia'}",
                        "accessed": datetime.now(JAKARTA_TZ).strftime("%Y-%m-%d")
                    }],
                    "foto": "",
                    "jabatan": "",
                    "completeness": 0,
                    "enriched_at": datetime.now(JAKARTA_TZ).isoformat(),
                    "method": "wikipedia"
                }
                
                # Save detail JSON in container
                detail_path = f"{ne.DETAIL_DIR}/{profile_id}.json"
                result = ne.merge_existing_detail(detail_path, result)
                result["id"] = profile_id
                detail_json = json.dumps(result, ensure_ascii=False, indent=2)
                
                import base64
                b64 = base64.b64encode(detail_json.encode()).decode()
                cmd = f"echo '{b64}' | base64 -d > '{detail_path}'"
                out, rc = ne.docker_exec(cmd)
                
                if rc == 0:
                    log(f"  ✓ Detail saved: {detail_path}")
                    # Update master entry
                    for m in master:
                        if m.get("id") == profile_id:
                            m["has_bio"] = bool(result.get("bio"))
                            m["has_foto"] = bool(result.get("foto"))
                            m["has_detail"] = True
                            m["completeness"] = (
                                (35 if result.get("bio") else 0) +
                                (25 if result.get("foto") else 0) +
                                25 +
                                (15 if m.get("count", 0) > 0 else 0)
                            )
                            break
                    # Write master back using robust base64 docker_exec
                    master_json_str = json.dumps(master, ensure_ascii=False, indent=2)
                    b64_master = base64.b64encode(master_json_str.encode()).decode()
                    master_cmd = f"echo '{b64_master}' | base64 -d > '{ne.MASTER_FILE}'"
                    ne.docker_exec(master_cmd)
                    log(f"  ✓ Master file updated in container")
                    return True
                else:
                    log(f"  ✗ Failed to write detail file: {out}")
                    return False
    else:
        # Generic URL - log for manual review
        log(f"  Non-Wikipedia URL, marking for review: {url}")
        return False
    
    return False

def main():
    log("=== GitHub Issue Review Check ===")
    owner, repo = "camagenta", "profilasatidz"
    
    # Find open issues with profil-asatidz label
    log("Fetching recently updated profil-asatidz issues...")
    issues = gh_api(f"repos/{owner}/{repo}/issues?labels=profil-asatidz&state=open&sort=updated&direction=desc&per_page=10") or []
    log(f"Found {len(issues)} issues to review")
    
    corrections_applied = 0
    corrections_pending = 0
    
    for issue in issues:
        issue_num = issue["number"]
        title = issue["title"]
        
        match = re.match(r'\[Profil Asatidz\]\s*(.+)', title)
        if not match:
            continue
        profile_name = match.group(1).strip()
        
        comments = get_issue_comments(owner, repo, issue_num)
        if not comments:
            continue
        
        contrib = find_contribution_in_comments(comments)
        if not contrib:
            continue
            
        log(f"  Found contribution in Issue #{issue_num} ({profile_name}) by {contrib['user']}")
        
        body = issue.get("body", "")
        id_match = re.search(r'\*\*ID\*\*:\s*`([^`]+)`', body)
        if not id_match:
            continue
            
        profile_id = id_match.group(1)
        
        if contrib["type"] == "direct_text":
            if contrib["status"] == "approved":
                success = apply_direct_contribution(profile_id, contrib)
                if success:
                    corrections_applied += 1
                    gh_api(
                        f"repos/{owner}/{repo}/issues/{issue_num}/comments",
                        method="POST",
                        data={"body": f"✅ **Status:** Disetujui & Diterapkan (Approved)\n\nKoreksi diterapkan dari kontribusi komunitas (Comment ID: {contrib['comment_id']})\n\n*Applied by bot at {datetime.now(JAKARTA_TZ).strftime('%Y-%m-%d %H:%M')} WIB*"}
                    )
            elif contrib["status"] == "rejected":
                corrections_pending += 1  # Counted as reviewed but rejected
                gh_api(
                    f"repos/{owner}/{repo}/issues/{issue_num}/comments",
                    method="POST",
                    data={"body": f"❌ **Status:** Ditolak oleh Admin (Rejected)\n\nKontribusi ditolak (Comment ID: {contrib['comment_id']}).\n\n*Rejected by admin at {datetime.now(JAKARTA_TZ).strftime('%Y-%m-%d %H:%M')} WIB*"}
                )
                log(f"  Contribution in Issue #{issue_num} was rejected by admin.")
            else:
                log(f"  Contribution in Issue #{issue_num} is pending admin reaction (👍 or 👎). Skipping.")
                
        else:
            # Fallback for old URL-only
            url = contrib["url"]
            success = enrich_from_url(profile_id, url)
            if success:
                corrections_applied += 1
                gh_api(
                    f"repos/{owner}/{repo}/issues/{issue_num}/comments",
                    method="POST",
                    data={"body": f"✅ Koreksi diterapkan dari {url}\n\n*Applied by bot at {datetime.now(JAKARTA_TZ).strftime('%Y-%m-%d %H:%M')} WIB*"}
                )
                gh_api(
                    f"repos/{owner}/{repo}/issues/{issue_num}",
                    method="PATCH",
                    data={"state": "closed"}
                )
            else:
                corrections_pending += 1
                gh_api(
                    f"repos/{owner}/{repo}/issues/{issue_num}/comments",
                    method="POST",
                    data={"body": f"⚠️ URL terdeteksi: {url}\n\nEnrichment otomatis belum bisa dilakukan. Perlu review manual.\n\n*Detected by bot at {datetime.now(JAKARTA_TZ).strftime('%Y-%m-%d %H:%M')} WIB*"}
                )
    
    log(f"=== Summary: {corrections_applied} applied, {corrections_pending} pending ===")

if __name__ == "__main__":
    main()
