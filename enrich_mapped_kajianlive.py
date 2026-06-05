#!/usr/bin/env python3
"""
Enrichment script for KajianLive mapped profiles with match_score >= 1.0.
Fetches pages from KajianLive, parses details, merges with existing detail files,
and updates the master index inside the Docker container.
"""
import base64
import json
import os
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

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

def curl_fetch_bytes(url, timeout=20):
    """Fetch URL and return decoded string safely handling non-UTF-8 characters"""
    try:
        result = subprocess.run([
            "curl", "-sL", "--max-time", str(timeout),
            "--connect-timeout", "10",
            "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "-H", "Accept-Language: id-ID,id;q=0.9,en;q=0.5",
            "--compressed",
            url
        ], capture_output=True, timeout=timeout+5)
        text = result.stdout.decode('utf-8', errors='replace')
        return text, result.returncode == 0 and len(text) > 200
    except Exception as e:
        log(f"  curl error: {e}")
        return "", False

def clean_html(raw_html):
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

def clean_bio_if_schedule(bio_text):
    if not bio_text:
        return ""
    text_lower = bio_text.lower()
    days = ["jumat", "sabtu", "ahad", "senin", "selasa", "rabu", "kamis"]
    day_count = sum(1 for day in days if day in text_lower)
    has_time = bool(re.search(r'\b\d{1,2}[.:]\d{2}\s*(?:wib|wita|wit)\b', text_lower))
    
    if len(bio_text) < 150:
        if 'jadwal' in text_lower or 'rutin' in text_lower or day_count >= 2:
            return ""
            
    if day_count >= 3 and has_time:
        return ""
        
    return bio_text

def enrich_from_kajianlive(ustadz_id, ustadz_name):
    """Scrape and parse KajianLive bio page"""
    url = f"https://kajianlive.my.id/bio_ustadz.php?id={ustadz_id}"
    log(f"  Fetching KajianLive ID {ustadz_id}...")
    
    html, ok = curl_fetch_bytes(url)
    if not ok:
        log(f"    ✗ Failed to fetch profile page")
        return None
        
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract photo
    foto = ""
    img_tag = soup.find('img', src=re.compile(r'get_foto_ust\.php'))
    if img_tag:
        foto = f"https://kajianlive.my.id/{img_tag['src'].lstrip('/')}"
        
    # Extract Biography, Education, and Karya
    card_text = soup.find(class_='card-text')
    bio_parts = []
    education = []
    karya = []
    
    if card_text:
        # First, find text nodes that are direct children of card_text
        for child in card_text.children:
            if child.name is None:
                text = clean_html(str(child))
                if len(text) > 15 and not text.startswith('Nama:'):
                    bio_parts.append(text)
                    
        # Now walk all tags inside card_text
        current_section = 'bio'
        for child in card_text.find_all(recursive=False):
            if child.name == 'h3':
                header_text = child.get_text().strip().upper()
                if 'PENDIDIKAN' in header_text:
                    current_section = 'education'
                elif 'KARYA' in header_text:
                    current_section = 'karya'
                elif 'PROFIL' in header_text:
                    current_section = 'profil'
                else:
                    current_section = 'other'
            elif child.name in ['ul', 'ol']:
                items = [clean_html(li.get_text()) for li in child.find_all('li') if li.get_text().strip()]
                if current_section == 'education':
                    education.extend(items)
                elif current_section == 'karya':
                    karya.extend(items)
            elif child.name == 'p':
                # Handle potential nested tags inside p (due to buggy HTML markup)
                nested_h3s = child.find_all('h3')
                nested_ps = child.find_all('p')
                nested_uls = child.find_all(['ul', 'ol'])
                
                if nested_h3s or nested_ps or nested_uls:
                    for p_child in child.children:
                        if p_child.name == 'h3':
                            header_text = p_child.get_text().strip().upper()
                            if 'PENDIDIKAN' in header_text:
                                current_section = 'education'
                            elif 'KARYA' in header_text:
                                current_section = 'karya'
                            elif 'PROFIL' in header_text:
                                current_section = 'profil'
                            else:
                                current_section = 'other'
                        elif p_child.name in ['ul', 'ol']:
                            items = [clean_html(li.get_text()) for li in p_child.find_all('li') if li.get_text().strip()]
                            if current_section == 'education':
                                education.extend(items)
                            elif current_section == 'karya':
                                karya.extend(items)
                        elif p_child.name == 'p':
                            text = clean_html(p_child.get_text())
                            if text and not text.startswith('Nama:'):
                                if current_section in ['bio', 'profil']:
                                    bio_parts.append(text)
                                elif current_section == 'education':
                                    education.append(text)
                                elif current_section == 'karya':
                                    karya.append(text)
                        elif p_child.name is None:
                            text = clean_html(str(p_child))
                            if len(text) > 15 and not text.startswith('Nama:'):
                                if current_section in ['bio', 'profil']:
                                    bio_parts.append(text)
                else:
                    text = clean_html(child.get_text())
                    if text and not text.startswith('Nama:'):
                        if current_section in ['bio', 'profil']:
                            bio_parts.append(text)
                        elif current_section == 'education':
                            education.append(text)
                        elif current_section == 'karya':
                            karya.append(text)
                            
    bio = "\n\n".join(bio_parts).strip()
    if len(bio) > 1000:
        bio = bio[:1000] + "..."
        
    bio = clean_bio_if_schedule(bio)
    
    return {
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
        "enriched_at": datetime.now(JAKARTA_TZ).isoformat(),
        "method": "kajianlive"
    }

def merge_existing_detail(existing, new_result):
    if not existing:
        return new_result
        
    merged = dict(new_result)
    
    # 1. Merge fields where we want to keep/combine lists
    for field in ["kary", "education", "expertise"]:
        existing_val = existing.get(field)
        new_val = merged.get(field)
        if existing_val and not new_val:
            merged[field] = existing_val
        elif existing_val and new_val:
            if isinstance(existing_val, list) and isinstance(new_val, list):
                combined = list(new_val)
                for item in existing_val:
                    if item not in combined:
                        combined.append(item)
                merged[field] = combined
                
    # 2. For bio, keep the existing one if it's longer
    existing_bio = existing.get("bio", "")
    new_bio = merged.get("bio", "")
    if len(existing_bio) > len(new_bio):
        merged["bio"] = existing_bio
        
    # 3. For foto and other single-value fields, keep existing if new is empty
    for field in ["foto", "jabatan", "social_media"]:
        existing_val = existing.get(field)
        if existing_val and not merged.get(field):
            merged[field] = existing_val
            
    # 4. Sources list combination
    existing_sources = existing.get("sources", [])
    new_sources = merged.get("sources", [])
    combined_sources = list(existing_sources)
    for s in new_sources:
        if not any(x.get("url") == s.get("url") for x in combined_sources):
            combined_sources.append(s)
    merged["sources"] = combined_sources
    
    return merged

def main():
    log("=== KajianLive Mapped Enrichment ===")
    
    # Load mapping
    with open('kajianlive_mapping.json') as f:
        mapping_data = json.load(f)
        
    # Filter mappings with score >= 1.0
    targets = [m for m in mapping_data['mapping'] if m['match_score'] >= 1.0]
    log(f"Found {len(targets)} mapped targets with score >= 1.0")
    
    # Load master file from container
    log("Loading master index from container...")
    master_json, rc = docker_exec(f"cat {MASTER_FILE}")
    if rc != 0:
        log("ERROR: Cannot read master file from container")
        sys.exit(1)
        
    master = json.loads(master_json)
    
    # Create master lookup dict by id
    master_dict = {m['id']: m for m in master}
    
    # Process targets in batches of 10 with random delay
    batch_size = 10
    total_targets = len(targets)
    
    for i, t in enumerate(targets):
        profile_id = t['kajian_net']['id']
        kl_id = t['kajianlive']['id']
        name = t['kajian_net']['name']
        
        # Batch logging boundary
        if i % batch_size == 0:
            batch_num = (i // batch_size) + 1
            total_batches = (total_targets + batch_size - 1) // batch_size
            log(f"--- Processing Batch {batch_num}/{total_batches} ---")
            
        log(f"[{i+1}/{total_targets}] Enriching {name} (ID: {profile_id})")
        
        # Scrape
        result = enrich_from_kajianlive(kl_id, name)
        
        if result:
            # Check if detail exists in container
            detail_path = f"{DETAIL_DIR}/{profile_id}.json"
            existing_json, rc = docker_exec(f"cat {detail_path} 2>/dev/null || echo '{{}}'")
            existing = {}
            if rc == 0 and existing_json.strip() != "{}":
                try:
                    existing = json.loads(existing_json)
                except:
                    pass
            
            # Merge
            merged = merge_existing_detail(existing, result)
            
            # Add/ensure identifiers
            merged["id"] = profile_id
            merged["count"] = t['kajian_net'].get('count', 0)
            merged["source_url"] = f"https://kajian.net/kajian-audio/Ceramah/{name.replace(' ', '%20')}"
            
            # Save merged JSON back to container
            merged_str = json.dumps(merged, ensure_ascii=False, indent=2)
            b64_detail = base64.b64encode(merged_str.encode()).decode()
            save_cmd = f"echo '{b64_detail}' | base64 -d > '{detail_path}'"
            _, rc_save = docker_exec(save_cmd)
            
            if rc_save == 0:
                log(f"    ✓ Detail enriched and saved: {detail_path}")
                
                # Update master index entry
                if profile_id in master_dict:
                    entry = master_dict[profile_id]
                    entry["has_bio"] = bool(merged.get("bio"))
                    entry["has_foto"] = bool(merged.get("foto"))
                    entry["has_detail"] = True
                    entry["completeness"] = (
                        (35 if merged.get("bio") else 0) +
                        (25 if merged.get("foto") else 0) +
                        25 +
                        (15 if entry.get("count", 0) > 0 else 0)
                    )
            else:
                log(f"    ✗ Failed to save detail for {name}")
        else:
            log(f"    ✗ Skipping {name} (failed to fetch)")
            
        # Polite scraping delay: random delay between 2.0 to 5.0 seconds
        delay = random.uniform(2.0, 5.0)
        time.sleep(delay)
        
    # Write updated master file back to container
    log("Updating master index in container...")
    master_json_str = json.dumps(master, ensure_ascii=False, indent=2)
    b64_master = base64.b64encode(master_json_str.encode()).decode()
    master_cmd = f"echo '{b64_master}' | base64 -d > '{MASTER_FILE}'"
    docker_exec(master_cmd)
    log("✓ Master updated successfully in container")
    log("=== Enrichment complete! ===")

if __name__ == "__main__":
    main()
