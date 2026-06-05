#!/usr/bin/env python3
"""
Profil Asatidz - Incremental Enrichment Script (nyicil mode)
Target: 5-10 profiles per run, random delay, Wikipedia-first approach
"""
import subprocess
import json
import random
import time
import os
import sys
import re
from datetime import datetime, timezone, timedelta
import argparse

# Config
CONTAINER = "profilasatidz"
MASTER_FILE = "/root/asatidz_master.json"
DETAIL_DIR = "/root/detail"
ENRICHED_FILE = "/root/asatidz_enriched.json"
MIN_BATCH = 5
MAX_BATCH = 10
MIN_DELAY = 20   # seconds between profiles
MAX_DELAY = 60
PROFILE_TIMEOUT = 90  # seconds per profile
WIKIPEDIA_DELAY = 3   # seconds between wiki requests

JAKARTA_TZ = timezone(timedelta(hours=7))

# Telegram config (read from env file)
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""
_env_file = os.path.expanduser("~/.hermes/.env")
if os.path.exists(_env_file):
    with open(_env_file) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line.startswith("TELEGRAM_BOT_TOKEN="):
                TELEGRAM_BOT_TOKEN = _line.split("=", 1)[1].strip()
            elif _line.startswith("TELEGRAM_HOME_CHANNEL="):
                TELEGRAM_CHAT_ID = _line.split("=", 1)[1].strip()

def now_str():
    return datetime.now(JAKARTA_TZ).strftime("%Y-%m-%d %H:%M:%S")

def log(msg):
    print(f"[{now_str()}] {msg}", flush=True)

def docker_exec(cmd):
    """Run command inside container, return (stdout, returncode)"""
    result = subprocess.run(
        ["docker", "exec", CONTAINER, "sh", "-c", cmd],
        capture_output=True, text=True, timeout=120
    )
    return result.stdout.strip(), result.returncode

def docker_cp_from(container_path, local_path):
    """Copy file from container to host"""
    result = subprocess.run(
        ["docker", "cp", f"{CONTAINER}:{container_path}", local_path],
        capture_output=True, text=True, timeout=30
    )
    return result.returncode == 0

def docker_cp_to(local_path, container_path):
    """Copy file from host to container"""
    result = subprocess.run(
        ["docker", "cp", local_path, f"{CONTAINER}:{container_path}"],
        capture_output=True, text=True, timeout=30
    )
    return result.returncode == 0

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
    except subprocess.TimeoutExpired:
        return "", False
    except Exception as e:
        log(f"  curl error: {e}")
        return "", False

def strip_html(html):
    """Remove HTML tags and decode entities"""
    text = re.sub(r'<(script|style|noscript|iframe|nav|header|footer|aside)[^>]*>.*?</\1>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&[a-z]+;', ' ', text)
    text = re.sub(r'&#[0-9]+;', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def is_relevant_profile(text, title=""):
    """
    Validate if the Wikipedia page text is related to Islamic religious figures/scholars.
    """
    if not text:
        return False
    
    text_lower = text.lower()
    title_lower = title.lower() if title else ""
    
    # Islamic/religious companion keywords
    islamic_keywords = [
        "ustadz", "ustad", "ustadzah", "ulama", "pendakwah", "da'i", "dai",
        "penceramah", "mubaligh", "mubalig", "tokoh agama", "ahli ilmu",
        "pemuka agama", "sunnah", "salaf", "salafy", "salafiyah", "pesantren",
        "ma'had", "madrasah", "kajian", "dakwah", "hadits", "fiqih", "tafsir",
        "aqidah", "tauhid", "fiqh", "hadis", "syaikh", "sheikh", "khotib", "khatib",
        "studi islam", "pemikiran islam", "islamic"
    ]
    
    # Check if at least one companion keyword is present in text or title
    has_keyword = any(kw in text_lower for kw in islamic_keywords) or any(kw in title_lower for kw in islamic_keywords)
    
    # Check if the page is generally related to Islam/Muslims
    has_islam_context = any(w in text_lower for w in ["islam", "muslim", "hijriah", "masehi", "al-qur'an", "quran", "sunnah"])
    
    # Exclude obvious non-religious professions if they don't have strong religious context
    non_religious_jobs = ["politikus", "bupati", "gubernur", "presiden", " dpr ", " dpd ", "menteri", "atlet", "pemain sepak", "penyanyi", "aktor", "aktris", "sutradara", "pembalap", "pengusaha"]
    has_non_religious_job = any(job in text_lower for job in non_religious_jobs)
    
    # Strong positive matches override non-religious jobs (e.g., an Ustadz who is also active in other fields)
    strong_keywords = ["ustadz", "ustad", "ulama", "pendakwah", "syaikh", "pesantren", "ma'had", "kajian", "dakwah", "salafy", "sunnah"]
    has_strong_keyword = any(skw in text_lower for skw in strong_keywords) or any(skw in title_lower for skw in strong_keywords)
    
    if has_non_religious_job and not has_strong_keyword:
        return False
        
    return has_keyword and has_islam_context

def wiki_search(name, lang="id"):
    """Search Wikipedia for a person"""
    from urllib.parse import quote
    api_url = f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search&srsearch={quote(name)}&format=json&srlimit=5"
    content, ok = curl_fetch(api_url, timeout=10)
    if ok:
        try:
            data = json.loads(content)
            return data.get("query", {}).get("search", [])
        except:
            pass
    return []

def wiki_extract(title, lang="id"):
    """Extract full article text from Wikipedia"""
    from urllib.parse import quote
    api_url = f"https://{lang}.wikipedia.org/w/api.php?action=query&titles={quote(title)}&prop=extracts&exintro=false&explaintext=true&format=json"
    content, ok = curl_fetch(api_url, timeout=12)
    if ok:
        try:
            data = json.loads(content)
            pages = data.get("query", {}).get("pages", {})
            for pid, page in pages.items():
                if pid != "-1" and "extract" in page:
                    return page["extract"]
        except:
            pass
    return ""

def extract_bio_from_wiki(text):
    """Extract biography section from Wikipedia text"""
    if not text:
        return ""
    # Try to find biography section
    sections = [
        (r'(?i)(?:biografi|hidupan|riwayat hidup|profil|tentang|penjelasan).*?\\n\\n', 0),
        (r'(?i)(?:pendidikan|education).*?\\n\\n', 1),
        (r'(?i)(?:karier|career|pekerjaan).*?\\n\\n', 2),
        (r'(?i)(?:karya|works|publikasi).*?\\n\\n', 3),
    ]
    
    # First paragraph is usually the bio summary
    paragraphs = [p.strip() for p in text.split('\\n\\n') if p.strip() and len(p.strip()) > 60]
    if paragraphs:
        first = paragraphs[0]
        # Skip if it's too short or just a disambiguation
        if len(first) > 80:
            # Clean up
            clean = re.sub(r'\\[\\d+\\]', '', first)
            clean = re.sub(r'\\s+', ' ', clean).strip()
            if len(clean) > 60:
                return clean[:500]
    return ""

def extract_pendidikan(text):
    """Extract education info from Wikipedia text"""
    if not text:
        return []
    results = []
    edu_patterns = [
        r'(?:Sarjana|S1|S2|S3|Magister|Doktor|PhD|SMA|SMP|SD|Madrasah|Pesantren)\b[^.。]*',
        r"(?:Universitas|Institut|Sekolah|Akademi|Ma'had|Pontianak|Surabaya|Jakarta|Yogyakarta|Malang|Bandung)[^.。]*",
    ]    
    for pattern in edu_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            clean = m.strip()
            if 8 < len(clean) < 120 and clean not in results:
                results.append(clean)
    return results[:5]

def extract_keahlian(text):
    """Extract expertise/topics"""
    if not text:
        return []
    results = []
    topics = [
        "Fiqih", "Tafsir", "Hadits", "Aqidah", "Sejarah Islam", "Bahasa Arab",
        "Tasawuf", "Akhlak", "Dakwah", "Sirah", "Ushul Fiqih", "Ilmu Hadits",
        "Ilmu Tafsir", "Quran", "Sunnah", "Manhaj", "Tauhid", "Shalat", "Puasa",
        "Zakat", "Hajj", "Muamalah", "Ushul", "Mantiq", "Balaghah", "Nahwu",
        "Sharaf", "Iqtishad Islam", "Pendidikan Islam", "Keluarga", "Perempuan",
        "Anak Muda", "Kesehatan", "Psikologi"
    ]
    for topic in topics:
        if re.search(r'\\b' + re.escape(topic) + r'\\b', text, re.IGNORECASE):
            results.append(topic)
    return results[:8]

def check_title_match(target_name, wiki_title):
    """
    Ensure the Wikipedia article title shares at least one significant word with the target name,
    preventing citation matches (like name mentioned in bibliography of an unrelated article) from hijacking.
    """
    import re
    # Normalize and clean name
    clean_target = re.sub(r'[^\w\s]', ' ', target_name).lower()
    
    # Remove common honorifics and titles
    honorifics = {"ustadz", "ustad", "ustadzah", "haji", "h", "hj", "syaikh", "sheikh", "kiai", "kyai", "dr", "prof", "lc", "ma"}
    target_words = [w for w in clean_target.split() if w not in honorifics and len(w) > 2]
    
    clean_title = re.sub(r'[^\w\s]', ' ', wiki_title).lower()
    title_words = clean_title.split()
    
    # Check if at least one significant word matches
    for word in target_words:
        if word in title_words or any(word in tw for tw in title_words):
            return True
    return False

def enrich_profile(name, source_url):
    """Enrich a single profile. Returns dict or None."""
    log(f"  Enriching: {name}")
    
    # Wikipedia ID first
    wiki_results = wiki_search(name, "id")
    time.sleep(WIKIPEDIA_DELAY)
    
    bio = ""
    educations = []
    expertise = []
    wiki_title = ""
    
    if wiki_results:
        # Loop through top 5 results to find the first relevant religious profile
        for result_item in wiki_results[:5]:
            candidate_title = result_item.get("title", "")
            
            # First, check if title is a semantic match to the name
            if not check_title_match(name, candidate_title):
                log(f"    Skipping Wiki ID candidate (Title mismatch): {candidate_title}")
                continue
                
            candidate_text = wiki_extract(candidate_title, "id")
            time.sleep(WIKIPEDIA_DELAY)
            
            if candidate_text and is_relevant_profile(candidate_text, candidate_title):
                wiki_title = candidate_title
                log(f"  ✓ Relevant Wiki ID match: {wiki_title} (score: {result_item.get('wordcount', 0)} words)")
                bio = extract_bio_from_wiki(candidate_text)
                educations = extract_pendidikan(candidate_text)
                expertise = extract_keahlian(candidate_text)
                
                if bio:
                    log(f"    ✓ Bio: {len(bio)} chars")
                if educations:
                    log(f"    ✓ Education: {len(educations)} entries")
                if expertise:
                    log(f"    ✓ Expertise: {len(expertise)} topics")
                break
            else:
                log(f"    Skipping irrelevant Wiki ID candidate: {candidate_title}")
    
    # Fallback: Wikipedia EN if ID failed
    if not bio:
        wiki_en = wiki_search(name, "en")
        time.sleep(WIKIPEDIA_DELAY)
        if wiki_en:
            for result_item in wiki_en[:5]:
                candidate_title = result_item.get("title", "")
                
                # Check title match for EN wiki too
                if not check_title_match(name, candidate_title):
                    log(f"    Skipping Wiki EN candidate (Title mismatch): {candidate_title}")
                    continue
                    
                candidate_text = wiki_extract(candidate_title, "en")
                time.sleep(WIKIPEDIA_DELAY)
                
                if candidate_text and is_relevant_profile(candidate_text, candidate_title):
                    log(f"  ✓ Relevant Wiki EN match: {candidate_title}")
                    wiki_title = candidate_title
                    bio = extract_bio_from_wiki(candidate_text)
                    educations = extract_pendidikan(candidate_text)
                    expertise = extract_keahlian(candidate_text)
                    break
                else:
                    log(f"    Skipping irrelevant Wiki EN candidate: {candidate_title}")
    
    # Build result
    result = {
        "name": name,
        "source_url": source_url,
        "bio": bio,
        "education": educations,
        "expertise": expertise,
        "kary": [],
        "social_media": {},
        "sources": [],
        "foto": "",
        "jabatan": "",
        "completeness": 0,
        "enriched_at": datetime.now(JAKARTA_TZ).isoformat(),
        "method": "wikipedia" if bio else "failed"
    }
    
    if bio:
        result["sources"].append({
            "id": "wiki_id",
            "url": f"https://{'' if 'title' not in dir() else ''}id.wikipedia.org/wiki/{wiki_title.replace(' ', '_')}" if wiki_title else "",
            "title": wiki_title or f"Artikel Wikipedia: {name}",
            "sitename": "Wikipedia Bahasa Indonesia",
            "accessed": datetime.now(JAKARTA_TZ).strftime("%Y-%m-%d")
        })
    
    return result

def slugify(name):
    """Convert name to URL-safe slug"""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\\s-]", "", slug)
    slug = re.sub(r"[\\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug

def merge_existing_detail(detail_path, new_result):
    """Merge new enrichment result with existing detail, preserving non-empty fields."""
    import base64
    existing = {}
    # Try to read existing detail
    b64_path = detail_path.replace('/', '_').replace('.', '_')
    get_cmd = f"base64 -w0 {detail_path}" if False else f"cat {detail_path}"
    out, rc = docker_exec(f"cat {detail_path} 2>/dev/null || echo '{{}}'")
    if rc == 0 and out and out.strip() != "{}":
        try:
            existing = json.loads(out)
        except:
            pass

    if not existing:
        return new_result

    # Merge strategy: new_result fills empty fields, existing non-empty fields are preserved
    # Exception: bio, education, expertise always take Wikipedia (new_result) if available
    merged = dict(new_result)

    # Preserve existing fields that are non-empty and not filled by new enrichment
    preserve_fields = ["kary", "social_media", "foto", "jabatan"]
    for field in preserve_fields:
        existing_val = existing.get(field)
        new_val = merged.get(field)
        if existing_val and not new_val:
            merged[field] = existing_val
            log(f"    Merged (kept existing): {field}={str(existing_val)[:60]}")
        elif existing_val and new_val:
            # For arrays, merge unique entries
            if isinstance(existing_val, list) and isinstance(new_val, list):
                combined = list(new_val)
                for item in existing_val:
                    if item not in combined:
                        combined.append(item)
                merged[field] = combined
                log(f"    Merged (combined): {field}")
            # For dicts/strings, keep new (already set)
    
    # Preserve existing sources, append new ones
    existing_sources = existing.get("sources", [])
    new_sources = merged.get("sources", [])
    if existing_sources:
        combined_sources = list(existing_sources)
        for s in new_sources:
            if s not in combined_sources:
                combined_sources.append(s)
        merged["sources"] = combined_sources

    return merged


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manual", action="store_true", help="Manual mode: target specific profiles")
    parser.add_argument("names", nargs="*", help="Profile names to enrich (manual mode)")
    args = parser.parse_args()
    
    if args.manual:
        log("=== Profil Asatidz Manual Enrichment ===")
        if not args.names or args.names == ["--all"]:
            log("ERROR: Provide profile names or --all flag")
            sys.exit(1)
        log(f"Manual targets: {args.names}")
    else:
        log("=== Profil Asatidz Nyicil Enrichment ===")
    
    # Determine batch size
    if args.manual:
        batch_size = len(args.names)
    else:
        batch_size = random.randint(MIN_BATCH, MAX_BATCH)
    log(f"Target batch size: {batch_size}")
    
    # Load master from container
    log("Loading master data...")
    master_json, rc = docker_exec(f"cat {MASTER_FILE}")
    if rc != 0:
        log("ERROR: Cannot read master file from container")
        sys.exit(1)
    
    try:
        master = json.loads(master_json)
    except json.JSONDecodeError as e:
        log(f"ERROR: Invalid master JSON: {e}")
        sys.exit(1)
    
    # Find unenriched entries (no bio, no has_bio)
    unenriched = [e for e in master if not e.get("has_bio", False) and not e.get("has_detail", False)]
    log(f"Unenriched: {len(unenriched)} / {len(master)} total")
    
    if args.manual:
        # Manual mode: find specific profiles by name (match even if already enriched)
        batch = []
        for name in args.names:
            if name == "--all":
                batch = unenriched[:]
                break
            found = [e for e in master if e.get("name", "").lower() == name.lower()]
            if found:
                batch.append(found[0])
            else:
                log(f"  WARNING: Profile not found: {name}")
        if not batch:
            log("No matching profiles found.")
            return
        log(f"Manual batch: {[e.get('name') for e in batch]}")
    else:
        if not unenriched:
            log("All profiles enriched! Nothing to do.")
            return
        # Pick random batch
        batch = random.sample(unenriched, min(batch_size, len(unenriched)))
        log(f"Selected {len(batch)} profiles for this run")
    
    # Enrich each
    enriched_count = 0
    failed_count = 0
    enriched_names = []
    
    for i, entry in enumerate(batch):
        name = entry.get("name", "Unknown")
        source_url = entry.get("source_url", "")
        
        log(f"[{i+1}/{len(batch)}] Processing: {name}")
        
        try:
            result = enrich_profile(name, source_url)
            
            if result and result.get("bio"):
                # Save as detail JSON via temp file (merge with existing)
                # Use 'id' as unique reference for detail file
                profile_id = entry.get("id") or f"kajian-{entry.get('slug') or slugify(name)}"
                detail_path = f"{DETAIL_DIR}/{profile_id}.json"
                result = merge_existing_detail(detail_path, result)
                # Ensure id is set in result
                result["id"] = profile_id
                detail_json = json.dumps(result, ensure_ascii=False, indent=2)
                
                # Write via base64 to avoid shell escaping issues
                import base64
                b64 = base64.b64encode(detail_json.encode()).decode()
                cmd = f"echo '{b64}' | base64 -d > '{detail_path}'"
                out, rc = docker_exec(cmd)
                
                if rc == 0:
                    log(f"  ✓ Detail saved: {detail_path}")
                    
                    # Update master entry
                    for m in master:
                        if m.get("name") == name:
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
                    enriched_count += 1
                    enriched_names.append(name)
                else:
                    log(f"  ✗ Failed to write detail: {out}")
                    failed_count += 1
            else:
                log(f"  ✗ No bio found")
                failed_count += 1
                
        except Exception as e:
            log(f"  ✗ Error: {e}")
            failed_count += 1
        
        # Random delay between profiles (except last)
        if i < len(batch) - 1:
            delay = random.randint(MIN_DELAY, MAX_DELAY)
            log(f"  Waiting {delay}s before next...")
            time.sleep(delay)
    
    # Save updated master
    log("Updating master file...")
    master_json = json.dumps(master, ensure_ascii=False, indent=2)
    
    # Write via base64 to avoid shell escaping and device-busy issues
    import base64
    b64_master = base64.b64encode(master_json.encode()).decode()
    cmd = f"echo '{b64_master}' | base64 -d > '{MASTER_FILE}'"
    out, rc = docker_exec(cmd)
    
    if rc == 0:
        log("✓ Master updated in container")
    else:
        log(f"✗ Failed to update master in container: {out}")
    
    # Summary
    still_unenriched = len([e for e in master if not e.get("has_bio", False) and not e.get("has_detail", False)])
    summary = f"=== Summary: {enriched_count} enriched, {failed_count} failed, {still_unenriched} remaining ==="
    log(summary)
    
    # Log to file
    log_file = "/home/ubuntu/nyicil_manual.log" if args.manual else "/home/ubuntu/nyicil_summary.log"
    try:
        with open(log_file, "a") as lf:
            lf.write(f"\n{'='*60}\n")
            lf.write(f"[{datetime.now(JAKARTA_TZ).strftime('%Y-%m-%d %H:%M')}]\n")
            lf.write(summary + "\n")
            if enriched_names:
                lf.write("Profil baru:\n")
                for n in enriched_names:
                    lf.write(f"  • {n} (bio+edu+expertise)\n")
    except Exception:
        pass
    
    # GitHub Issues: create/update issue per enriched profile (skip manual mode)
    if not args.manual:
        for i, entry in enumerate(batch):
            profile_id = entry.get("id") or f"kajian-{entry.get('slug') or slugify(entry.get('name',''))}"
            profile_name = entry.get("name", "Unknown")
            was_enriched = entry.get("name") in enriched_names
            update_github_issue(profile_id, profile_name, was_enriched, entry)

    # Send Telegram notification (skip in manual mode)
    if not args.manual and (enriched_count > 0 or failed_count > 0):
        now = datetime.now(JAKARTA_TZ).strftime("%d %b %Y")
        msg = f"📿 <b>Profil Asatidz — {now}</b>\n\n"
        msg += f"✅ Enriched: <b>{enriched_count}</b>\n"
        msg += f"❌ Failed: <b>{failed_count}</b>\n"
        msg += f"📊 Remaining: <b>{still_unenriched}</b> / {len(master)}\n\n"
        if enriched_names:
            msg += "<b>Profil baru:</b>\n"
            for n in enriched_names:
                msg += f"• {n}\n"
        if failed_count > 0:
            msg += f"\n⚠️ {failed_count} profil perlu review (Wiki match kurang relevan)"
        send_telegram(msg)

def update_github_issue(profile_id, profile_name, was_enriched, entry):
    """Create or update GitHub Issue for a profile. Body = resume of live data."""
    try:
        import subprocess as sp, json as j
        
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
            f"- **Sumber**: [{source_url}]({source_url})",
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
        result = sp.run(
            ["gh", "issue", "list", "--repo", "camagenta/profilasatidz",
             "--search", f'"{title}"', "--state", "open", "--json", "number,title",
             "--limit", "1"],
            capture_output=True, text=True, timeout=15
        )
        
        existing = []
        if result.returncode == 0 and result.stdout.strip():
            try:
                existing = j.loads(result.stdout)
            except:
                pass
        
        if existing:
            # Update existing issue
            issue_num = existing[0]["number"]
            update_result = sp.run(
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
            create_result = sp.run(
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

def send_telegram(message):
    """Send message to Telegram via Bot API"""
    global TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log("  Telegram: token/chat not configured")
        return False
    try:
        import urllib.parse
        payload = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT_ID,
            "parse_mode": "HTML",
            "text": message
        })
        # Write payload to temp file to avoid shell escaping issues
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tf:
            tf.write(payload)
            tf.flush()
            payload_file = tf.name
        
        result = subprocess.run([
            "curl", "-sS", "--max-time", "15",
            "-X", "POST",
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            "-d", f"@{payload_file}"
        ], capture_output=True, text=True, timeout=20)
        os.unlink(payload_file)
        success = '"ok":true' in result.stdout
        if success:
            log("  ✓ Telegram sent")
        else:
            log(f"  ✗ Telegram failed: {result.stdout[:100]}")
        return success
    except Exception as e:
        log(f"  Telegram error: {e}")
        return False

if __name__ == "__main__":
    main()
