#!/usr/bin/env python3
"""
OSINT Enrichment Script - Multi-source asatidz profile searcher
Fetches data from known Islamic lecture websites and search engines
"""
import subprocess
import json
import re
import sys
import time
import os
from urllib.parse import quote

DATA_DIR = "/home/ubuntu/profilasatidz"
RESULTS_FILE = os.path.join(DATA_DIR, "osint_results_batch_1.json")
INPUT_FILE = os.path.join(DATA_DIR, "asatidz.json")

def fetch_url(url, timeout=12):
    """Fetch URL with realistic browser headers"""
    headers = [
        "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "-H", "Accept-Language: id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        "--compressed", "-L", "-s", "--max-time", str(timeout), "--connect-timeout", "8",
    ]
    try:
        result = subprocess.run(["curl"] + headers + [url], capture_output=True, text=True, timeout=timeout+5)
        return result.stdout, result.returncode
    except subprocess.TimeoutExpired:
        return "", 28


def strip_html(html):
    """Remove HTML tags and decode entities"""
    text = re.sub(r'<(script|style|noscript|iframe)[^>]*>.*?</\1>', ' ', html, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&[a-z]+;', ' ', text)
    text = re.sub(r'\\s+', ' ', text).strip()
    return text


def find_section(text, keywords, window=300):
    """Find text sections containing keywords"""
    results = []
    text_lower = text.lower()
    for kw in keywords:
        idx = text_lower.find(kw.lower())
        if idx != -1:
            start = max(0, idx - 50)
            end = min(len(text), idx + window)
            snippet = text[start:end].strip()
            if snippet and len(snippet) > 20:
                results.append(snippet)
    return results


def extract_social(html):
    """Extract social media URLs from HTML"""
    social = {}
    patterns = {
        "youtube": r'https?://(?:www\.)?youtube\.com/(?:channel/|c/|user/|@)[^\s"<>\\\'$]+',
        "website": r'https?://(?:www\.)?(?:[a-z0-9-]+\.)?(?:sch\.id|or\.id|co\.id|com|org\.id|net\.id|web\.id|my\.id)/[^\s"<>\\\'$]+',
        "instagram": r'https?://(?:www\.)?instagram\.com/[^\s"<>\\\'$]+',
        "facebook": r'https?://(?:www\.)?facebook\.com/[^\s"<>\\\'$]+',
        "telegram": r'https?://t\.me/[^\s"<>\\\'$]+',
        "twitter": r'https?://(?:www\.)?twitter\.com/[^\s"<>\\\'$]+',
        "tiktok": r'https?://(?:www\.)?tiktok\.com/@[^\s"<>\\\'$]+',
    }
    for platform, pattern in patterns.items():
        matches = re.findall(pattern, html, re.IGNORECASE)
        clean = []
        seen = set()
        for m in matches:
            url = m.rsplit('?', 1)[0].rstrip('/')
            if url not in seen and len(url) < 200:
                clean.append(url)
                seen.add(url)
        if clean:
            social[platform] = clean[0]  # Take first match
    return social


def search_person(name):
    """Research a single person across multiple sources"""
    result = {
        "name": name,
        "bio": "",
        "education": [],
        "expertise": [],
        "publications": [],
        "social_media": {}
    }
    
    all_content = ""
    social_media = {}
    
    # === SOURCE 1: Try person's website (common pattern) ===
    name_slug = name.lower().replace("'", "").replace(" ", "").replace(".", "")
    name_dash = name.lower().replace("'", "").replace(" ", "-").replace(".", "")
    
    common_domains = [
        f"https://{name_slug}.com",
        f"https://{name_slug}.or.id",
        f"https://{name_slug}.sch.id",
        f"https://{name_slug}.web.id",
        f"https://www.{name_slug}.com",
        f"https://{name_dash}.com",
        f"https://{name_dash}.or.id",
    ]
    
    # === SOURCE 2: Search via Bing (works better for Indonesian content) ===
    search_queries = [
        f'"{name}" ustadz biografi pendidikan Indonesia',
        f'{name} ustadz profil ceramah',
    ]
    
    for query in search_queries[:1]:  # Limit to 1 query per person
        bing_url = f"https://www.bing.com/search?q={quote(query)}&setlang=id"
        content, code = fetch_url(bing_url)
        if code == 0 and len(content) > 500:
            text = strip_html(content)
            all_content += " " + text
            social_media.update(extract_social(content))
            
            # Extract links from Bing results
            links = re.findall(r'https?://(?:www\.)?(?!.*(?:bing|microsoft|msn|live|office|outlook|xbox))[a-z0-9-]+\.[a-z]{2,}(?:/[^\s"<>]*)?', content)
            # Prioritize known bio pages
            for link in links[:10]:
                link_lower = link.lower()
                if any(kw in link_lower for kw in ['profil', 'tentang', 'about', 'biografi', 'bio', 'santri', 'pengajar']):
                    page_content, page_code = fetch_url(link)
                    if page_code == 0 and len(page_content) > 300:
                        page_text = strip_html(page_content)
                        all_content += " " + page_text
                        social_media.update(extract_social(page_content))
    
    # === Extract bio ===
    bio_sentences = find_section(all_content, [
        f"{name} adalah", f"{name} merupakan", f"{name} bin", f"{name} ibn",
        f"nama lengkap", f" bernama", "nama:", "kunyah", "lahir",
        "tempat tanggal", "TTL:", "ttl:",
    ], window=400)
    
    if bio_sentences:
        # Pick the best bio sentence
        for sent in bio_sentences:
            if name.lower() in sent.lower() and len(sent) > 30:
                result["bio"] = sent[:500]
                break
        if not result["bio"]:
            result["bio"] = bio_sentences[0][:500]
    
    # === Extract education ===
    edu_items = find_section(all_content, [
        "pendidikan", "alumni", "alma mater", "lulusan", "S1", "S2", "S3",
        "sarjana", "magister", "doktor", "pondok pesantren", "universitas",
        "Gontor", "Madinah", "Azhar", "LIPIA", "Mahad", "Tahfizhul",
        "Fakultas", "Jurusan", "Syariah", "Hadits", "Ushuluddin",
    ], window=300)
    
    seen_edu = set()
    for item in edu_items:
        short = item[:100]
        if short not in seen_edu and len(item) > 20:
            result["education"].append(item)
            seen_edu.add(short)
        if len(result["education"]) >= 5:
            break
    
    # === Extract expertise ===
    expertise_list = []
    expertise_keywords = [
        "tauhid", "aqidah", "fiqh", "hadits", "tafsir", "akhlak", "sirah",
        "syariah", "ushul fiqh", "nahwu", "shorof", "faraidh", "tasawuf",
        "tahfidz", "imam", "khatib", "dakwah", "ceramah rutin",
        "pengajian", "kajian", "tarbiyah", "usuluddin",
    ]
    all_lower = all_content.lower()
    for kw in expertise_keywords:
        if kw in all_lower:
            expertise_list.append(kw)
    
    if expertise_list:
        result["expertise"] = expertise_list[:10]
    
    # === Extract publications ===
    pub_items = find_section(all_content, [
        "buku", "kitab", "karangan", "tulis", "penulis", "karya", "terbit",
        "menerjemah", "risalah", "makalah",
    ], window=200)
    
    seen_pub = set()
    for item in pub_items:
        short = item[:100]
        if short not in seenPub and len(item) > 20:
            result["publications"].append(item)
            seen_pub.add(short)
        if len(result["publications"]) >= 3:
            break
    
    # === Social media ===
    result["social_media"] = social_media
    
    return result


def main():
    batch_file = sys.argv[1] if len(sys.argv) > 1 else os.path.join(DATA_DIR, "osint_batch_1.json")
    
    with open(batch_file) as f:
        asatidz_list = json.load(f)
    
    print(f"=== OSINT Research: {os.path.basename(batch_file)} ===")
    print(f"Total: {len(asatidz_list)} asatidz\n")
    
    results = []
    
    for i, person in enumerate(asatidz_list):
        name = person["name"]
        count = person.get("count", 0)
        
        print(f"[{i+1}/{len(asatidz_list)}] {name} (count={count})")
        
        # Skip obvious non-person entries
        content_channels = ["Kisah Muslim"]
        if name in content_channels:
            results.append({
                "name": name, "is_content_channel": True,
                "bio": "", "education": [], "expertise": [], "publications": [], "social_media": {}
            })
            print(f"  SKIP: known content channel\n")
            time.sleep(0.5)
            continue
        
        data = search_person(name)
        
        # Print summary
        print(f"  bio: {'✓' if data['bio'] else '✗'} {data['bio'][:80]}..." if data['bio'] else "  bio: ✗")
        print(f"  edu: {len(data['education'])} items")
        print(f"  expertise: {data['expertise'][:5]}")
        print(f"  pub: {len(data['publications'])}")
        print(f"  social: {list(data['social_media'].keys())}")
        print()
        
        results.append(data)
        time.sleep(1.5)  # Rate limiting between searches
    
    # Save results
    output_file = batch_file.replace("batch_", "results_batch_")
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"=== SAVED: {output_file} ===")
    print(f"Processed: {len(results)} asatidz")
    has_bio = sum(1 for r in results if r.get('bio'))
    print(f"With bio: {has_bio}/{len(results)}")


if __name__ == "__main__":
    main()
