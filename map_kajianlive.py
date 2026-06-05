#!/usr/bin/env python3
import json
import re
from difflib import SequenceMatcher

def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()

def normalize(name):
    """Normalize name for comparison by removing common titles and punctuation."""
    n = name.lower()
    
    # Extract only letters and spaces
    n = re.sub(r'[^a-z\s]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    
    words = n.split()
    
    # Titles to remove
    titles = {
        'ustadz', 'ustad', 'ustadzah', 'syaikh', 'sheikh', 'dr', 'prof', 
        'haji', 'h', 'hj', 'kiai', 'kyai', 'assoc', 'kak', 'bang',
        'lc', 'ma', 'm', 'pd', 'hum', 'sc', 'psi', 'si', 'hi', 'ag', 
        'st', 'ss', 'sh', 'se', 'ba', 'phd', 'i', 'ars', 'abu'
    }
    
    filtered = []
    for w in words:
        if w not in titles:
            filtered.append(w)
            
    # If filtered is empty (e.g. name was just "Abu"), revert
    if not filtered:
        return n
        
    return ' '.join(filtered)

def main():
    with open('kajianlive_ustadz.json') as f:
        kl_data = json.load(f)['ustadz']
    
    with open('asatidz_master.json') as f:
        kn_data = json.load(f)
        
    # Prepare normalized names
    kl_map = []
    for u in kl_data:
        kl_map.append({
            'raw': u,
            'norm': normalize(u['name_kajianlive'])
        })
        
    # Mapping results
    mapping = []
    unmapped = []
    
    # 1. First pass: exact normalized match
    for kn in kn_data:
        kn_name = kn['name']
        kn_norm = normalize(kn_name)
        
        match = None
        score = 0
        
        # Exact norm match
        for kl in kl_map:
            if kl['norm'] == kn_norm:
                match = kl['raw']
                score = 1.0
                break
                
        # 2. Second pass: partial match / highest score
        if not match:
            best_kl = None
            best_score = 0
            
            for kl in kl_map:
                # Require at least one word overlap
                kn_words = set(kn_norm.split())
                kl_words = set(kl['norm'].split())
                
                if kn_words & kl_words:
                    s = similar(kn_norm, kl['norm'])
                    # If one is fully contained in another
                    if kn_norm in kl['norm'] or kl['norm'] in kn_norm:
                        s += 0.2 # Boost score
                    
                    if s > best_score:
                        best_score = s
                        best_kl = kl['raw']
                        
            if best_score > 0.7:
                match = best_kl
                score = best_score
                
        if match:
            mapping.append({
                'kajian_net': {
                    'id': kn['id'],
                    'name': kn_name,
                    'count': kn.get('count', 0)
                },
                'kajianlive': {
                    'id': match['kajianlive_id'],
                    'name': match['name_kajianlive'],
                    'url': match['bio_url']
                },
                'match_score': round(score, 3)
            })
        else:
            unmapped.append({
                'kajian_net': {
                    'id': kn['id'],
                    'name': kn_name
                }
            })
            
    # Sort mapping
    mapping.sort(key=lambda x: x['match_score'], reverse=True)
    
    result = {
        'stats': {
            'total_kajian_net': len(kn_data),
            'total_kajianlive': len(kl_data),
            'mapped': len(mapping),
            'unmapped': len(unmapped),
            'match_rate': f"{len(mapping)/len(kn_data):.1%}"
        },
        'mapping': mapping,
        'unmapped_kajian_net': unmapped
    }
    
    with open('kajianlive_mapping.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        
    print(f"Selesai! Mapping tersimpan ke kajianlive_mapping.json")
    print(f"Total kajian.net : {result['stats']['total_kajian_net']}")
    print(f"Berhasil di-map : {result['stats']['mapped']} ({result['stats']['match_rate']})")
    print(f"Tidak ter-map   : {result['stats']['unmapped']}")
    
    print("\nSample 5 Mapping Terbaik:")
    for m in mapping[:5]:
        print(f"✓ {m['kajian_net']['name']:<30} -> {m['kajianlive']['name']}")
        
    print("\nSample 5 Mapping Terlemah (Score < 1.0):")
    weak = [m for m in mapping if m['match_score'] < 1.0]
    for m in weak[-5:]:
        print(f"? {m['match_score']:.2f} | {m['kajian_net']['name']:<30} -> {m['kajianlive']['name']}")

if __name__ == '__main__':
    main()
