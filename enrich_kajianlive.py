#!/usr/bin/env python3
"""
Profil Asatidz - KajianLive OSINT Enrichment Script
Targets: kajianlive.my.id profiles
"""
import subprocess
import json
import re
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import quote, unquote

CONTAINER = "profilasatidz"
MASTER_FILE = "/root/asatidz_master.json"
DETAIL_DIR = "/root/detail"
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

def curl_fetch(url, timeout=15):
    """Fetch URL using curl, return (content, success)"""
    try:
        result = subprocess.run([
            "curl", "-sL", "--max-time", str(timeout),
            "--connect-timeout", "8",
            "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "-H", "Accept-Language: id-ID,id;q=0.9,en;q=0.5",
            "--compressed",
            url
        ], capture_output=True, text=True, timeout=timeout+5)
        return result.stdout, result.returncode == 0 and len(result.stdout) > 200
    except Exception as e:
        log(f"  curl error: {e}")
        return "", False

def slugify(name):
    """Convert name to URL-safe slug"""
    slug = name.lower().strip()
    # Remove honorifics
    honorifics = ["ustadz", "ustad", "ustadzah", "haji", "h.", "hj.", "syaikh", "sheikh", "kiai", "kyai", "dr", "dr.", "prof", "prof.", "lc", "ma"]
    words = [w for w in slug.split() if w not in honorifics]
    slug = " ".join(words)
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")

def clean_html(raw_html):
    """Clean tags and decode entities"""
    if not raw_html:
        return ""
    text = re.sub(r'<[^>]+>', ' ', raw_html)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&rsquo;', "'", text)
    text = re.sub(r'&lsquo;', "'", text)
    text = re.sub(r'&rdquo;', '"', text)
    text = re.sub(r'&ldquo;', '"', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def parse_education_from_text(text):
    """Extract education items from bio text if structured"""
    items = []
    # Try finding S1/S2/S3 patterns
    edu_patterns = [
        r'(?:Sarjana|S-1|S1|S-2|S2|S-3|S3|Magister|Doktor|PhD|Madrasah|Pesantren|Lulusan|Alumni)\b[^.。\n]*',
        r"(?:Universitas|Institut|Sekolah|Akademi|Ma'had|Pondok Pesantren)[^.。\n]*",
    ]
    for pattern in edu_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            clean = clean_html(m)
            if 10 < len(clean) < 120 and clean not in items:
                items.append(clean)
    return items[:5]

def enrich_from_kajianlive(ustadz_id, ustadz_name):
    """Scrape and parse KajianLive bio page"""
    url = f"https://kajianlive.my.id/bio_ustadz.php?id={ustadz_id}"
    log(f"Fetching KajianLive profile ID {ustadz_id}: {ustadz_name}")
    
    html, ok = curl_fetch(url)
    if not ok:
        log(f"  ✗ Failed to fetch profile page")
        return None
    
    # 1. Extract photo
    foto = ""
    foto_match = re.search(r'get_foto_ust\.php\?file=([^"\'>\s]+)', html)
    if foto_match:
        foto = f"https://kajianlive.my.id/get_foto_ust.php?file={foto_match.group(1)}"
        log(f"  ✓ Photo URL: {foto}")
    
    # 2. Extract Biography & Education
    bio = ""
    education = []
    
    # Find biography text blocks
    # Typically inside <p> or plain text sections
    # In KajianLive, it is often raw text after "Jadwal Kajian Rutin:"
    bio_section_match = re.search(r'Jadwal Kajian Rutin:.*?</main>|Jadwal Kajian Rutin:(.*?)Copyright', html, re.DOTALL | re.IGNORECASE)
    if bio_section_match:
        bio_text = bio_section_match.group(1) if len(bio_section_match.groups()) > 0 else bio_section_match.group(0)
        
        # Extract individual paragraphs or clean block
        paragraphs = re.split(r'<br\s*/?>|\n\n', bio_text)
        cleaned_paragraphs = []
        for p in paragraphs:
            cleaned = clean_html(p)
            # Skip advertisement/schedule text
            if not cleaned or "Jadwal" in cleaned or "Copyright" in cleaned or "@kajianlive" in cleaned:
                continue
            if len(cleaned) > 50:
                cleaned_paragraphs.append(cleaned)
        
        if cleaned_paragraphs:
            bio = "\n\n".join(cleaned_paragraphs)
            # Shorten if too long
            if len(bio) > 800:
                bio = bio[:800] + "..."
            log(f"  ✓ Bio: {len(bio)} chars extracted")
            
            # Extract education
            education = parse_education_from_text(bio)
            if education:
                log(f"  ✓ Education: {len(education)} items")

    # 3. Extract Karya Tulis (Publications)
    karya = []
    karya_section_match = re.search(r'Karya tulis(.*?)Copyright', html, re.DOTALL | re.IGNORECASE)
    if karya_section_match:
        karya_text = karya_section_match.group(1)
        items = re.findall(r'<li>(.*?)</li>|\d+\.\s*(.*?)(?=<br|<p|<li>|\d+\.|$)', karya_text, re.DOTALL)
        for item in items:
            val = item[0] or item[1]
            clean = clean_html(val)
            if clean and 5 < len(clean) < 150:
                karya.append(clean)
        if karya:
            log(f"  ✓ Karya Tulis: {len(karya)} publications")
            
    # If no bio found in text blocks, fallback to searching for clean text paragraphs in entire HTML
    if not bio:
        text_only = clean_html(html)
        # Find index of "Jadwal Kajian Rutin:"
        idx = text_only.find("Jadwal Kajian Rutin:")
        if idx != -1:
            snippet = text_only[idx+20:idx+800]
            bio = snippet.strip()
            log(f"  ✓ Fallback Bio: {len(bio)} chars extracted")
            education = parse_education_from_text(bio)

    result = {
        "name": ustadz_name,
        "bio": bio,
        "education": education,
        "expertise": [],
        "kary": karya,
        "social_media": {},
        "sources": [{
            "id": "kajianlive",
            "url": url,
            "title": f"Biografi {ustadz_name}",
            "sitename": "KajianLive",
            "accessed": datetime.now(JAKARTA_TZ).strftime("%Y-%m-%d")
        }],
        "foto": foto,
        "jabatan": "",
        "completeness": 0,
        "enriched_at": datetime.now(JAKARTA_TZ).isoformat(),
        "method": "kajianlive"
    }
    
    return result

def update_github_issue(profile_id, profile_name, was_enriched, entry):
    """Create or update GitHub Issue for a profile."""
    try:
        # Build issue body (resume)
        slug = entry.get("slug", "")
        source_url = entry.get("source_url", "")
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
                log(f"  ✓ GitHub Issue #{issue_num} updated: {profile_name}")
            else:
                log(f"  ✗ GitHub Issue update failed: {update_result.stderr[:100]}")
        else:
            # Create new issue
            create_result = subprocess.run(
                ["gh", "issue", "create", "--repo", "camagenta/profilasatidz",
                 "--title", title, "--body", body, "--label", labels],
                capture_output=True, text=True, timeout=15
            )
            if create_result.returncode == 0:
                log(f"  ✓ GitHub Issue created: {profile_name}")
            else:
                log(f"  ✗ GitHub Issue create failed: {create_result.stderr[:100]}")
                
    except Exception as e:
        log(f"  ✗ GitHub Issue error: {e}")

def main():
    log("=== KajianLive OSINT Enrichment Test ===")
    
    # 5 test ustadz from page 1 of KajianLive
    test_ustadz = [
        {"id": "1145", "name": "Ahmad Syakir"},
        {"id": "841", "name": "Faisal Abdurrahim"},
        {"id": "317", "name": "Nizar Hidayatur Rahman"},
        {"id": "1441", "name": "Deni Irawan"},
        {"id": "1444", "name": "Hendri Waluyo Lensa"}
    ]
    
    # Load master file from container
    log("Loading master file from container...")
    master_json, rc = docker_exec(f"cat {MASTER_FILE}")
    if rc != 0:
        log("ERROR: Cannot read master file from container")
        sys.exit(1)
        
    master = json.loads(master_json)
    
    for item in test_ustadz:
        k_id = item["id"]
        name = item["name"]
        slug = slugify(name)
        profile_id = f"kajian-{slug}"
        
        # Scrape KajianLive profile
        result = enrich_from_kajianlive(k_id, name)
        
        if result and result.get("bio"):
            # Update master array
            # Check if ustadz already exists in master, else add him
            found = False
            for m in master:
                if m.get("slug") == slug or m.get("id") == profile_id:
                    m["has_bio"] = True
                    m["has_detail"] = True
                    m["completeness"] = (
                        35 + 25 + 15  # bio, detail, count (if count > 0)
                    )
                    entry = m
                    found = True
                    break
            
            if not found:
                entry = {
                    "name": name,
                    "slug": slug,
                    "source_url": f"https://kajian.net/kajian-audio/Ceramah/{quote(name)}",
                    "count": 0,
                    "categories": [],
                    "has_bio": True,
                    "has_foto": bool(result.get("foto")),
                    "has_detail": True,
                    "id": profile_id,
                    "completeness": 60
                }
                master.append(entry)
                log(f"  ✓ Added {name} to master index")
            
            # Save detail JSON in container
            detail_path = f"{DETAIL_DIR}/{profile_id}.json"
            detail_json = json.dumps(result, ensure_ascii=False, indent=2)
            
            import base64
            b64 = base64.b64encode(detail_json.encode()).decode()
            cmd = f"echo '{b64}' | base64 -d > '{detail_path}'"
            out, rc = docker_exec(cmd)
            
            if rc == 0:
                log(f"  ✓ Detail saved: {detail_path}")
                # Create/update GitHub Issue
                update_github_issue(profile_id, name, True, entry)
            else:
                log(f"  ✗ Failed to save detail: {out}")
        else:
            log(f"  ✗ Skipping {name} (no bio found)")
            
    # Write master file back to container
    log("Updating master file in container...")
    master_json_str = json.dumps(master, ensure_ascii=False, indent=2)
    
    import base64
    b64_master = base64.b64encode(master_json_str.encode()).decode()
    master_cmd = f"echo '{b64_master}' | base64 -d > '{MASTER_FILE}'"
    docker_exec(master_cmd)
    log("✓ Master updated successfully")

if __name__ == "__main__":
    main()
