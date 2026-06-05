#!/usr/bin/env python3
"""
OSINT Enrichment Script v2 - Uses Wikipedia API + direct site scraping
"""
import subprocess
import json
import re
import sys
import time
import os
from urllib.parse import quote

DATA_DIR = "/home/ubuntu/profilasatidz"

def fetch_url(url, timeout=12):
    headers = [
        "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "-H", "Accept-Language: id-ID,id;q=0.9",
        "--compressed", "-L", "-s", "--max-time", str(timeout), "--connect-timeout", "8",
    ]
    try:
        result = subprocess.run(["curl"] + headers + [url], capture_output=True, text=True, timeout=timeout+5)
        return result.stdout, result.returncode
    except subprocess.TimeoutExpired:
        return "", 28

def strip_html(html):
    text = re.sub(r'<(script|style|noscript|iframe)[^>]*>.*?</\1>', ' ', html, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&[a-z]+;', ' ', text)
    text = re.sub(r'&#[0-9]+;', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def wiki_search(name, lang="id"):
    """Search Wikipedia API"""
    api_url = f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search&srsearch={quote(name)}&format=json&srlimit=5"
    content, code = fetch_url(api_url)
    if code == 0:
        try:
            data = json.loads(content)
            return data.get("query", {}).get("search", [])
        except:
            pass
    return []

def wiki_extract(title, lang="id"):
    """Get Wikipedia article extract"""
    api_url = f"https://{lang}.wikipedia.org/w/api.php?action=query&titles={quote(title)}&prop=extracts&exintro=true&explaintext=true&format=json"
    content, code = fetch_url(api_url)
    if code == 0:
        try:
            data = json.loads(content)
            pages = data.get("query", {}).get("pages", {})
            for pid, pdata in pages.items():
                if "extract" in pdata:
                    return pdata["extract"]
        except:
            pass
    return ""

def wiki_full_text(title, lang="id"):
    """Get full Wikipedia article text"""
    api_url = f"https://{lang}.wikipedia.org/w/api.php?action=parse&page={quote(title)}&prop=text&format=json"
    content, code = fetch_url(api_url)
    if code == 0:
        try:
            data = json.loads(content)
            html = data.get("parse", {}).get("text", {}).get("*", "")
            return strip_html(html)
        except:
            pass
    return ""

def extract_social_from_html(html):
    social = {}
    patterns = {
        "youtube": r'https?://(?:www\.)?youtube\.com/(?:channel/|c/|user/|@)[^\s"<>\\\'$]+',
        "instagram": r'https?://(?:www\.)?instagram\.com/[^\s"<>\\\'$]+',
        "facebook": r'https?://(?:www\.)?facebook\.com/[^\s"<>\\\'$]+',
        "telegram": r'https?://t\.me/[^\s"<>\\\'$]+',
        "twitter": r'https?://(?:www\.)?twitter\.com/[^\s"<>\\\'$]+',
        "tiktok": r'https?://(?:www\.)?tiktok\.com/@[^\s"<>\\\'$]+',
        "website": r'https?://(?:www\.)?(?:[a-z0-9-]+\.)+(?:or\.id|sch\.id|co\.id|web\.id|my\.id|com|org)/[^\s"<>\\\'$]+',
    }
    for platform, pattern in patterns.items():
        matches = re.findall(pattern, html, re.IGNORECASE)
        seen = set()
        for m in matches:
            url = m.rsplit('?', 1)[0].rstrip('/')
            if url not in seen and len(url) < 200 and 'wikipedia' not in url:
                social[platform] = url
                seen.add(url)
                break
    return social

def find_in_text(text, keywords, window=300):
    """Find text sections containing keywords"""
    results = []
    text_lower = text.lower()
    seen = set()
    for kw in keywords:
        idx = text_lower.find(kw.lower())
        while idx != -1:
            start = max(0, idx - 50)
            end = min(len(text), idx + window)
            snippet = text[start:end].strip()
            key = snippet[:80]
            if key not in seen and len(snippet) > 20:
                results.append(snippet)
                seen.add(key)
            idx = text_lower.find(kw.lower(), idx + 1)
    return results

def is_politician(text):
    """Check if Wikipedia article is about a politician (not ustadz)"""
    politician_keywords = ["politikus", "anggota DPR", "DPR-RI", "legislatif", "partai politik", "DPD", "DPRD", "Menteri", "Gubernur", "Bupati", "Walikota"]
    text_lower = text.lower()
    count = sum(1 for kw in politician_keywords if kw in text_lower)
    return count >= 2

def is_ustadz_article(text):
    """Check if article is about an Islamic scholar/ustadz"""
    ustadz_keywords = ["ustadz", "ulama", "pendakwah", "dakwah", "ceramah", "pengajian", "kajian", "pesantren", "santri", "habib", "kyai", "sheikh", "syaikh"]
    text_lower = text.lower()
    count = sum(1 for kw in ustadz_keywords if kw in text_lower)
    return count >= 1

def search_person(name):
    """Research a single person"""
    result = {
        "name": name,
        "bio": "",
        "education": [],
        "expertise": [],
        "publications": [],
        "social_media": {},
        "sources": []
    }
    
    all_text = ""
    all_social = {}
    
    # === SOURCE 1: Wikipedia ID ===
    wiki_results = wiki_search(name, "id")
    
    # Also try without Arabic prefixes
    clean_name = name
    for prefix in ["Abu ", "Syaikh ", "Ustadz ", "Habib ", "Syaikh Prof DR ", "Prof. Dr. ", "DR ", "dr. "]:
        if clean_name.startswith(prefix):
            clean_name = clean_name[len(prefix):]
    
    if clean_name != name and len(clean_name) > 3:
        wiki_results += wiki_search(clean_name, "id")
    
    # Deduplicate by title
    seen_titles = set()
    unique_results = []
    for r in wiki_results:
        t = r['title']
        if t not in seen_titles:
            unique_results.append(r)
            seen_titles.add(t)
    
    # Find the best matching article
    best_title = None
    for r in unique_results:
        title = r['title']
        snippet = re.sub(r'<[^>]+>', '', r.get('snippet', ''))
        
        # Check if this is about the right person
        if name.lower() in title.lower() or title.lower() in name.lower():
            extract = wiki_extract(title, "id")
            if extract:
                if is_politician(extract) and not is_ustadz_article(extract):
                    continue  # Skip politician articles
                best_title = title
                all_text += " " + extract
                result["sources"].append(f"wikipedia:id:{title}")
                break
        
        # Check snippet for ustadz indicators
        if is_ustadz_article(snippet) or "ustadz" in snippet.lower() or "ulama" in snippet.lower():
            extract = wiki_extract(title, "id")
            if extract and not is_politician(extract):
                best_title = title
                all_text += " " + extract
                result["sources"].append(f"wikipedia:id:{title}")
                break
    
    # If no specific match, try first result
    if not best_title and unique_results:
        for r in unique_results[:2]:
            title = r['title']
            extract = wiki_extract(title, "id")
            if extract and len(extract) > 100:
                if not (is_politician(extract) and not is_ustadz_article(extract)):
                    best_title = title
                    all_text += " " + extract
                    result["sources"].append(f"wikipedia:id:{title}")
                    break
    
    # === SOURCE 2: Wikipedia EN ===
    if not best_title:
        wiki_en_results = wiki_search(name, "en")
        for r in wiki_en_results[:3]:
            title = r['title']
            extract = wiki_extract(title, "en")
            if extract and len(extract) > 100:
                if is_ustadz_article(extract) or "islam" in extract.lower() or "scholar" in extract.lower():
                    all_text += " " + extract
                    result["sources"].append(f"wikipedia:en:{title}")
                    break
    
    # === SOURCE 3: Try known websites ===
    name_slug = re.sub(r'[^a-zA-Z0-9]', '', name.lower())
    name_dash = re.sub(r'[^a-zA-Z0-9]', '-', name.lower()).strip('-')
    
    known_sites = [
        f"https://{name_slug}.com",
        f"https://{name_slug}.or.id",
        f"https://{name_slug}.sch.id",
        f"https://{name_slug}.web.id",
        f"https://www.{name_slug}.com",
        f"https://{name_dash}.com",
        f"https://{name_dash}.or.id",
    ]
    
    for site in known_sites:
        content, code = fetch_url(site)
        if code == 0 and len(content) > 500:
            text = strip_html(content)
            if name.lower() in text.lower():
                all_text += " " + text
                all_social.update(extract_social_from_html(content))
                result["sources"].append(site)
                break
    
    # === Extract structured data from all_text ===
    if all_text:
        # Bio: first paragraph or sentence containing the name
        bio_markers = [
            f"{name} adalah", f"{name} merupakan", f"{name} bin", f"{name} ibn",
            f"{clean_name} adalah", f"{clean_name} merupakan",
        ]
        for marker in bio_markers:
            idx = all_text.lower().find(marker.lower())
            if idx != -1:
                end = all_text.find(".", idx + len(marker))
                if end != -1 and end - idx < 600:
                    result["bio"] = all_text[idx:end+1].strip()
                    break
        
        if not result["bio"]:
            # Try to get first sentence
            sentences = all_text.split('.')
            for sent in sentences[:5]:
                if name.lower() in sent.lower() and len(sent) > 30:
                    result["bio"] = sent.strip()[:500]
                    break
        
        # Education
        edu_keywords = [
            "pendidikan", "alumni", "alma mater", "lulusan", "S1", "S2", "S3",
            "sarjana", "magister", "doktor", "pondok pesantren", "universitas",
            "Gontor", "Madinah", "Azhar", "LIPIA", "Mahad", "Tahfizhul",
            "Fakultas", "Jurusan", "Syariah", "Hadits", "Ushuluddin",
            "Tarbiyah", "Tafsir", "Fiqh", "Aqidah",
        ]
        edu_items = find_in_text(all_text, edu_keywords, 300)
        result["education"] = edu_items[:5]
        
        # Expertise
        expertise_found = []
        expertise_keywords = [
            "tauhid", "aqidah", "fiqh", "hadits", "tafsir", "akhlak", "sirah",
            "syariah", "ushul fiqh", "nahwu", "shorof", "faraidh", "tasawuf",
            "tahfidz", "dakwah", "tarbiyah", "usuluddin", "quran",
            "salafi", "manhaj", "sunnah", "bid'ah", "taqlid",
        ]
        all_lower = all_text.lower()
        for kw in expertise_keywords:
            if kw in all_lower:
                expertise_found.append(kw)
        result["expertise"] = expertise_found[:10]
        
        # Publications
        pub_keywords = ["buku", "kitab", "karangan", "tulis", "penulis", "karya", "terbit", "menerjemah", "risalah"]
        pub_items = find_in_text(all_text, pub_keywords, 200)
        result["publications"] = pub_items[:3]
        
        # Social media from article
        all_social.update(extract_social_from_html(all_text))
    
    result["social_media"] = all_social
    
    return result


def main():
    batch_file = sys.argv[1] if len(sys.argv) > 1 else os.path.join(DATA_DIR, "osint_batch_1.json")
    
    with open(batch_file) as f:
        asatidz_list = json.load(f)
    
    print(f"=== OSINT Research v2: {os.path.basename(batch_file)} ===")
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
                "bio": "", "education": [], "expertise": [], "publications": [], "social_media": {}, "sources": []
            })
            print(f"  SKIP: content channel\n")
            continue
        
        data = search_person(name)
        
        print(f"  bio: {'✓' if data['bio'] else '✗'} {(data['bio'][:80] + '...') if data['bio'] and len(data['bio']) > 80 else data['bio']}")
        print(f"  edu: {len(data['education'])} items")
        print(f"  expertise: {data['expertise'][:5]}")
        print(f"  pub: {len(data['publications'])}")
        print(f"  social: {list(data['social_media'].keys())}")
        print(f"  sources: {data['sources']}")
        print()
        
        results.append(data)
        time.sleep(0.5)
    
    # Save results
    output_file = batch_file.replace("batch_", "results_batch_")
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n=== SAVED: {output_file} ===")
    print(f"Processed: {len(results)}")
    has_bio = sum(1 for r in results if r.get('bio'))
    print(f"With bio: {has_bio}/{len(results)}")
    has_edu = sum(1 for r in results if r.get('education'))
    print(f"With education: {has_edu}/{len(results)}")
    has_social = sum(1 for r in results if r.get('social_media'))
    print(f"With social media: {has_social}/{len(results)}")


if __name__ == "__main__":
    main()
