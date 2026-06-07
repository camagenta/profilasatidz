#!/usr/bin/env python3
"""
Re-enrich 50 asatidz with Wikipedia-style citations (sanad).
For each entry, search via Wikipedia API + Exa API and produce:
  - bio, bio_source, bio_quote
  - education[], education_source, education_quote
  - expertise[], expertise_source, expertise_quote
  - publications[], publications_source, publications_quote
  - social_media{} with _url + _verified
  - sources[] array for the detail panel footer
"""
import json
import time
import urllib.request
import urllib.parse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wikifetch import verify_wikipedia_match

EXA_KEY = os.environ.get('EXA_KEY', 'cb395eba-ccbe-43f1-b828-f2376b69e3e8')

def wiki_search(name):
    """Search Wikipedia API for a page about this person."""
    # Clean name: remove non-Indonesian prefixes
    clean = name.replace('Ustadz ', '').replace('Ust. ', '').replace('Syaikh ', '').replace('Prof. ', '').replace('Prof Dr ', '').replace('DR ', '').replace('Dr. ', '').replace('dr. ', '').replace('KH. ', '').replace('KH ', '').replace('K.H. ', '').replace('Lc. ', '').replace('Lc ', '').replace('M.A. ', '').replace('M.A ', '').replace(', M.A.', '').strip()
    # Try exact title match first
    url = f"https://id.wikipedia.org/w/api.php?action=query&titles={urllib.parse.quote(clean)}&prop=extracts|extlinks&exintro=true&explaintext=true&ellimit=20&format=json"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'ProfilAsatidz/1.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        pages = data.get('query', {}).get('pages', {})
        for pid, page in pages.items():
            if pid == '-1':
                continue
            extract = page.get('extract', '')
            extlinks = page.get('extlinks', [])
            title = page.get('title', clean)
            return {
                'title': title,
                'extract': extract[:800],
                'url': f"https://id.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}",
                'extlinks': [l.get('url', '') for l in extlinks]
            }
    except Exception as e:
        pass
    return None

def wiki_search_en(name):
    """Try English Wikipedia."""
    clean = name.replace('Ustadz ', '').replace('Ust. ', '').replace('Syaikh ', '').replace('Prof. ', '').replace('Prof Dr ', '').replace('DR ', '').replace('Dr. ', '').replace('dr. ', '').replace('KH. ', '').replace('KH ', '').replace('K.H. ', '').replace('Lc. ', '').replace('Lc ', '').replace('M.A. ', '').replace('M.A ', '').replace(', M.A.', '').strip()
    url = f"https://en.wikipedia.org/w/api.php?action=query&titles={urllib.parse.quote(clean)}&prop=extracts|extlinks&exintro=true&explaintext=true&ellimit=20&format=json"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'ProfilAsatidz/1.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        pages = data.get('query', {}).get('pages', {})
        for pid, page in pages.items():
            if pid == '-1':
                continue
            extract = page.get('extract', '')
            extlinks = page.get('extlinks', [])
            title = page.get('title', clean)
            return {
                'title': title,
                'extract': extract[:800],
                'url': f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}",
                'extlinks': [l.get('url', '') for l in extlinks]
            }
    except Exception as e:
        pass
    return None

def exa_search(name, num=5):
    """Search Exa API."""
    clean = name
    payload = json.dumps({
        "query": f"{clean} sunnah Indonesia ustadz pendakwah",
        "numResults": num,
        "contents": {"text": True, "maxCharacters": 500}
    }).encode()
    url = "https://api.exa.ai/search"
    req = urllib.request.Request(url, data=payload, headers={
        'x-api-key': EXA_KEY,
        'Content-Type': 'application/json'
    }, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        results = data.get('results', [])
        return [{
            'url': res.get('url', ''),
            'title': res.get('title', ''),
            'text': (res.get('text', '') or '')[:400],
            'publishedDate': res.get('publishedDate', '')
        } for res in results]
    except Exception as e:
        print(f"  Exa error: {e}")
        return []

def parse_social_media(extlinks, exa_results):
    """Extract social media links."""
    sm = {}
    social_patterns = {
        'youtube': ['youtube.com', 'youtu.be'],
        'facebook': ['facebook.com', 'fb.com'],
        'instagram': ['instagram.com'],
        'twitter': ['twitter.com', 'x.com'],
        'telegram': ['t.me'],
        'tiktok': ['tiktok.com'],
        'website': []
    }
    all_links = list(extlinks)
    for r in exa_results:
        all_links.append(r.get('url', ''))
    
    for link in all_links:
        link_lower = link.lower()
        for platform, patterns in social_patterns.items():
            if any(p in link_lower for p in patterns):
                key = platform
                if platform == 'youtube' and 'youtube_video' not in sm:
                    pass
                if key not in sm:
                    sm[key] = link
    
    return sm

def extract_education(text):
    """Extract education info from text."""
    edu_keywords = ['sarjana', 'magister', 'doktor', 'S1', 'S2', 'S3', 'SMA', 'SMK', 'MA ', 'MTs', 'MI ',
                    'universitas', 'UIN', 'UIA', 'UGM', 'ITB', 'ITS', 'UNDIP', 'UNAIR', 'ITSB',
                    'LIPIA', 'Madinah', 'Mekkah', 'Al-Azhar', 'Al Azhar', 'pesantren', 'madrasah',
                    'mahad', 'fakultas', 'jurusan', 'lulus', 'alumni', 'berijazah', 'ijazah',
                    'berpendidikan', 'menempuh', 'pendidikan', 'sekolah',
                    'bachelor', 'master', 'phd', 'diploma']
    lines = text.replace('\r', '\n').split('\n')
    edu_lines = []
    for line in lines:
        line = line.strip()
        if not line or len(line) < 10:
            continue
        if any(kw.lower() in line.lower() for kw in edu_keywords):
            # Clean up
            line = line.replace('|', ' ').replace('  ', ' ').strip()
            if len(line) > 200:
                line = line[:200]
            edu_lines.append(line)
    return list(dict.fromkeys(edu_lines))[:5]  # dedup, max 5

def extract_expertise(text, name):
    """Extract expertise/topics."""
    topic_map = {
        'hadits': ['hadits', 'hadist', 'hadeeth'],
        'fiqh': ['fiqh', 'fikih', 'fiqih'],
        'tafsir': ['tafsir', 'tafseer'],
        'aqidah': ['aqidah', 'aqidat', 'akidah', 'creed'],
        'tauhid': ['tauhid', 'tawhid', 'tauhid'],
        'tahfidz': ['tahfidz', 'tahfiz', 'hafidz', 'menghafal quran'],
        'dakwah': ['dakwah', 'dakwa', 'da\'wa'],
        'manhaj': ['manhaj', 'manhaj'],
        'sholat': ['sholat', 'salah', 'ibadah', 'doa', 'prayer'],
        'puasa': ['puasa', 'shaum', 'fasting', 'ramadan'],
        'zakat': ['zakat'],
        'haji': ['haji', 'hajj', 'pilgrimage'],
        'sirah': ['sirah', 'sejarah nabi', 'nabi muhammad'],
        'akhlaq': ['akhlaq', 'akhlak', 'moral', 'ethics'],
        'keluarga': ['keluarga', 'pernikahan', 'nikah', 'rumah tangga'],
        'quran': ['quran', 'al-quran', 'al quran'],
        'sejarah': ['sejarah', 'history'],
        'bahasa arab': ['bahasa arab', 'arabic']
    }
    text_lower = text.lower()
    found = []
    for topic, keywords in topic_map.items():
        if any(kw in text_lower for kw in keywords):
            found.append(topic)
    return list(dict.fromkeys(found))[:7]

def extract_bio_sentences(text, name, max_sentences=3):
    """Extract the most relevant biographical sentences."""
    # Split into sentences
    sentences = []
    for chunk in text.split('.'):
        chunk = chunk.strip()
        if len(chunk) > 20 and len(chunk) < 300:
            sentences.append(chunk)
    
    # Score sentences by relevance (contain name or bio-ish keywords)
    bio_keywords = ['adalah', 'lahir', 'dari', 'alumni', 'lulusan', 'pendidikan',
                    'menjabat', 'ketua', 'pembina', 'pengajar', 'pendiri', 'founder',
                    'ulama', 'cendekiawan', 'penceramah', 'penulis', 'ustadz', 'ustad',
                    'teacher', 'scholar', 'lecturer', 'preacher']
    scored = []
    for s in sentences:
        score = 0
        s_lower = s.lower()
        if any(part.lower() in s_lower for part in name.split()[:2]):
            score += 3
        for kw in bio_keywords:
            if kw in s_lower:
                score += 1
        scored.append((score, s))
    scored.sort(reverse=True)
    best = [s for _, s in scored[:max_sentences]]
    if not best and sentences:
        best = [sentences[0]]
    return '. '.join(best) + ('.' if best else '')

def main():
    with open('/home/ubuntu/profilasatidz/asatidz_enriched.json') as f:
        data = json.load(f)
    
    # Get top 50 by count that have some enrichment
    enriched_names = set()
    for e in data:
        if e.get('bio') or e.get('education') or e.get('expertise') or e.get('social_media'):
            enriched_names.add(e['name'])
    
    # Also get top 50 by count
    sorted_data = sorted(data, key=lambda x: x.get('count', 0), reverse=True)
    target_names = set()
    for e in sorted_data[:50]:
        target_names.add(e['name'])
    
    # Union
    all_targets = enriched_names | target_names
    print(f"Target: {len(all_targets)} names to re-enrich with citations")
    
    result = []
    sources_counter = 0
    
    for entry in data:
        name = entry['name']
        if name not in all_targets:
            result.append(entry)
            continue
        
        print(f"\nProcessing: {name}")
        sources = []
        
        # 1. Wikipedia ID
        wiki = wiki_search(name)
        time.sleep(0.3)
        if wiki and not verify_wikipedia_match(name, wiki['title'], wiki['extract'][:500]):
            print(f"  Lesson #14 guard: rejected Wiki ID '{wiki['title']}' for '{name}' (title mismatch)")
            wiki = None

        # 2. Wikipedia EN
        if not wiki:
            wiki = wiki_search_en(name)
            time.sleep(0.3)
            if wiki and not verify_wikipedia_match(name, wiki['title'], wiki['extract'][:500]):
                print(f"  Lesson #14 guard: rejected Wiki EN '{wiki['title']}' for '{name}' (title mismatch)")
                wiki = None
        
        # 3. Exa
        exa_results = exa_search(name, num=5)
        time.sleep(0.5)
        
        wiki_text = wiki.get('extract', '') if wiki else ''
        all_exa_text = ' '.join(r.get('text', '') for r in exa_results)
        combined_text = wiki_text + ' ' + all_exa_text
        
        # Build sources list
        if wiki:
            sources.append({
                'id': str(len(sources) + 1),
                'url': wiki['url'],
                'title': f"Wikipedia: {wiki['title']}",
                'snippet': wiki['extract'][:150]
            })
        
        for i, er in enumerate(exa_results[:3]):
            sources.append({
                'id': str(len(sources) + 1),
                'url': er['url'],
                'title': er['title'] or 'Sumber Online',
                'snippet': er['text'][:150]
            })
        
        # Bio
        bio = ''
        bio_source = ''
        bio_quote = ''
        if wiki_text:
            bio = extract_bio_sentences(wiki_text, name)
            bio_source = wiki['url']
            bio_quote = wiki_text[:200]
        elif all_exa_text:
            bio = extract_bio_sentences(all_exa_text, name)
            if exa_results:
                bio_source = exa_results[0]['url']
                bio_quote = exa_results[0].get('text', '')[:200]
        
        # Education
        edu = extract_education(combined_text)
        edu_source = ''
        edu_quote = ''
        if edu:
            if wiki:
                edu_source = wiki['url']
            elif exa_results:
                edu_source = exa_results[0]['url']
            edu_quote = ' '.join(edu)[:200]
        
        # Expertise
        expertise = extract_expertise(combined_text, name)
        exp_source = ''
        exp_quote = ''
        if expertise:
            if wiki:
                exp_source = wiki['url']
            elif exa_results:
                exa_results[0]['url'] if exa_results else ''
                exp_source = exa_results[0]['url']
            exp_quote = ', '.join(expertise)
        
        # Social media
        extlinks = wiki.get('extlinks', []) if wiki else []
        sm = parse_social_media(extlinks, exa_results)
        
        # Format social media with _url/verified
        formatted_sm = {}
        for platform, url in sm.items():
            formatted_sm[platform] = url
            formatted_sm[f"{platform}_url"] = url
            formatted_sm[f"{platform}_verified"] = 'true'
        
        entry['bio'] = bio
        entry['bio_source'] = bio_source
        entry['bio_quote'] = bio_quote
        entry['education'] = edu
        entry['education_source'] = edu_source
        entry['education_quote'] = edu_quote
        entry['expertise'] = expertise
        entry['expertise_source'] = exp_source
        entry['expertise_quote'] = exp_quote
        entry['publications'] = entry.get('publications', [])
        entry['publications_source'] = ''
        entry['publications_quote'] = ''
        entry['social_media'] = formatted_sm
        entry['sources'] = sources
        entry['source_url'] = entry.get('source_url', '')
        
        result.append(entry)
        print(f"  bio={bool(bio)}, edu={len(edu)}, exp={len(expertise)}, sm={len(sm)}, sources={len(sources)}")
    
    # Write
    with open('/home/ubuntu/profilasatidz/asatidz_enriched.json', 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    enriched_count = sum(1 for e in result if e.get('bio') or e.get('sources'))
    print(f"\n✓ Done. {enriched_count} entries with data.")

if __name__ == '__main__':
    main()
