#!/usr/bin/env python3
"""
OSINT Enrichment Script v3 - Improved matching + multi-source
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
    api_url = f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search&srsearch={quote(name)}&format=json&srlimit=10"
    content, code = fetch_url(api_url)
    if code == 0:
        try:
            data = json.loads(content)
            return data.get("query", {}).get("search", [])
        except:
            pass
    return []

def wiki_extract(title, lang="id"):
    api_url = f"https://{lang}.wikipedia.org/w/api.php?action=query&titles={quote(title)}&prop=extracts&exintro=false&explaintext=true&format=json"
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
    politician_keywords = ["politikus", "anggota DPR", "DPR-RI", "legislatif", "partai politik", "DPD", "DPRD", "Menteri", "Gubernur", "Bupati", "Walikota", "sultan", "kesultanan"]
    text_lower = text.lower()
    count = sum(1 for kw in politician_keywords if kw in text_lower)
    return count >= 2

def is_ustadz_related(text):
    ustadz_keywords = ["ustadz", "ulama", "pendakwah", "dakwah", "ceramah", "pengajian", "kajian", "pesantren", "santri", "habib", "kyai", "sheikh", "syaikh", "dosen", "fatwa", "salafi"]
    text_lower = text.lower()
    count = sum(1 for kw in ustadz_keywords if kw in text_lower)
    return count >= 1

def name_similarity(name1, name2):
    """Check if two names likely refer to the same person"""
    # Normalize: lowercase, remove common prefixes
    def normalize(n):
        n = n.lower().strip()
        for p in ["abu ", "syaikh ", "ustadz ", "habib ", "prof. dr. ", "prof.dr. ", "dr. ", "dr ", "h. ", "hajj ", "haji "]:
            if n.startswith(p):
                n = n[len(p):]
        # Remove Arabic characters for comparison
        n = re.sub(r'[\u0600-\u06FF]', '', n)
        n = re.sub(r'[^a-z0-9\s]', '', n)
        n = re.sub(r'\s+', ' ', n).strip()
        return set(n.split())
    
    set1 = normalize(name1)
    set2 = normalize(name2)
    
    if not set1 or not set2:
        return False
    
    # Check overlap
    overlap = set1 & set2
    min_size = min(len(set1), len(set2))
    
    if min_size == 0:
        return False
    
    # At least 50% of words should match
    return len(overlap) / min_size >= 0.5

def search_person(name):
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
    
    # Try with cleaned name
    clean_name = name
    for prefix in ["Abu ", "Syaikh ", "Ustadz ", "Habib ", "Syaikh Prof DR ", "Prof. Dr. ", "DR ", "dr. ", "الشيخ "]:
        if clean_name.startswith(prefix):
            clean_name = clean_name[len(prefix):]
    
    if clean_name != name and len(clean_name) > 3:
        wiki_results += wiki_search(clean_name, "id")
    
    # Deduplicate
    seen_titles = set()
    unique_results = []
    for r in wiki_results:
        t = r['title']
        if t not in seen_titles:
            unique_results.append(r)
            seen_titles.add(t)
    
    # Find best matching article
    best_title = None
    best_score = 0
    
    for r in unique_results:
        title = r['title']
        snippet = re.sub(r'<[^>]+>', '', r.get('snippet', ''))
        
        # Score the match
        score = 0
        if name_similarity(name, title):
            score += 10
        if name.lower() in title.lower() or title.lower() in name.lower():
            score += 5
        if is_ustadz_related(snippet):
            score += 3
        
        if score > best_score:
            extract = wiki_extract(title, "id")
            if extract and len(extract) > 100:
                if not (is_politician(extract) and not is_ustadz_related(extract)):
                    best_title = title
                    best_score = score
    
    if best_title:
        extract = wiki_extract(best_title, "id")
        if extract:
            all_text += " " + extract
            result["sources"].append(f"wikipedia:id:{best_title}")
    
    # === SOURCE 2: Wikipedia EN (if ID didn't work well) ===
    if not best_title or len(all_text) < 200:
        wiki_en_results = wiki_search(name, "en")
        for r in wiki_en_results[:5]:
            title = r['title']
            if name_similarity(name, title) or name.lower() in title.lower():
                extract = wiki_extract(title, "en")
                if extract and len(extract) > 100:
                    if is_ustadz_related(extract) or "islam" in extract.lower() or "scholar" in extract.lower():
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
            if name.lower() in text.lower() or clean_name.lower() in text.lower():
                all_text += " " + text
                all_social.update(extract_social_from_html(content))
                result["sources"].append(site)
                break
    
    # === SOURCE 4: Try kajian.net page for topic info ===
    kajian_url = f"https://kajian.net/kajian-audio/Ceramah/{quote(name)}"
    content, code = fetch_url(kajian_url)
    if code == 0 and len(content) > 1000:
        text = strip_html(content)
        # Extract topic titles from kajian.net (they list ceramah titles)
        topics = re.findall(r'<a[^>]*>([^<]*(?:Tafsir|Fiqh|Aqidah|Tauhid|Hadits|Sirah|Akhlak|Ibadah|Ramadhan|Haji|Zakat|Shalat|Doa|Surga|Neraka|Iman|Islam|Quran|Sunnah|Kitab|Surah|Rukun|Wajib|Sunnah|Makruh|Haram)[^<]*)</a>', text, re.IGNORECASE)
        if topics:
            unique_topics = list(set(topics))[:10]
            result["expertise"].extend(unique_topics)
    
    # === Extract structured data ===
    if all_text:
        # Bio: first sentence containing the name
        sentences = re.split(r'(?<=[.!?])\s+', all_text)
        for sent in sentences[:10]:
            if (name.lower() in sent.lower() or clean_name.lower() in sent.lower()) and len(sent) > 30:
                result["bio"] = sent.strip()[:500]
                break
        
        if not result["bio"]:
            # Try pattern: "X adalah..."
            for pattern in [f"{name} adalah", f"{name} merupakan", f"{clean_name} adalah", f"{clean_name} merupakan"]:
                idx = all_text.lower().find(pattern.lower())
                if idx != -1:
                    end = all_text.find(".", idx + len(pattern))
                    if end != -1 and end - idx < 600:
                        result["bio"] = all_text[idx:end+1].strip()
                        break
        
        # Education
        edu_keywords = [
            "pendidikan", "alumni", "alma mater", "lulusan", "S1", "S2", "S3",
            "sarjana", "magister", "doktor", "pondok pesantren", "universitas",
            "Gontor", "Madinah", "Azhar", "LIPIA", "Mahad", "Tahfizhul",
            "Fakultas", "Jurusan", "Syariah", "Hadits", "Ushuluddin",
            "Tarbiyah", "Tafsir", "Fiqh", "Aqidah", "Dakwah",
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
        result["expertise"] = list(set(result["expertise"] + expertise_found))[:10]
        
        # Publications
        pub_keywords = ["buku", "kitab", "karangan", "tulis", "penulis", "karya", "terbit", "menerjemah", "risalah"]
        pub_items = find_in_text(all_text, pub_keywords, 200)
        result["publications"] = pub_items[:3]
        
        # Social media
        all_social.update(extract_social_from_html(all_text))
    
    result["social_media"] = all_social
    
    return result


def main():
    batch_file = sys.argv[1] if len(sys.argv) > 1 else os.path.join(DATA_DIR, "osint_batch_1.json")
    
    with open(batch_file) as f:
        asatidz_list = json.load(f)
    
    print(f"=== OSINT Research v3: {os.path.basename(batch_file)} ===")
    print(f"Total: {len(asatidz_list)} asatidz\n")
    
    results = []
    
    for i, person in enumerate(asatidz_list):
        name = person["name"]
        count = person.get("count", 0)
        
        print(f"[{i+1}/{len(asatidz_list)}] {name} (count={count})")
        
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
        time.sleep(0.3)
    
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
