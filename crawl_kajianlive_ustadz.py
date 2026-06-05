#!/usr/bin/env python3
"""
Crawl daftar ustadz dari kajianlive.my.id
Output: kajianlive_ustadz.json — mapping lengkap {id, name, foto_file, bio_url, foto_url}

Halaman listing: daftar_ustadz.php?page=1 s/d page=146
"""
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta

JAKARTA_TZ = timezone(timedelta(hours=7))
BASE = "https://kajianlive.my.id"
OUTPUT = "kajianlive_ustadz.json"
MAX_PAGE = 146
DELAY = 1.5  # detik antar request, sopan ke server


def log(msg):
    ts = datetime.now(JAKARTA_TZ).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def curl_fetch(url, timeout=20):
    """Fetch URL pakai curl, return (html, ok)"""
    try:
        result = subprocess.run([
            "curl", "-sL", "--max-time", str(timeout),
            "--connect-timeout", "10",
            "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "-H", "Accept: text/html,application/xhtml+xml",
            "-H", "Accept-Language: id-ID,id;q=0.9",
            "--compressed",
            url
        ], capture_output=True, timeout=timeout + 10)
        text = result.stdout.decode('utf-8', errors='replace')
        return text, result.returncode == 0 and len(text) > 100
    except Exception as e:
        log(f"  curl error: {e}")
        return "", False


def parse_page(html):
    """Parse satu halaman daftar_ustadz, extract list ustadz."""
    entries = []

    # Pattern: <a ... href="bio_ustadz.php?id=XXX" title="Nama Ustadz" ...>
    # Ada 2 bentuk link per card, kita ambil yang punya title
    links = re.findall(
        r'<a\s[^>]*href=["\']bio_ustadz\.php\?id=(\d+)["\'][^>]*title=["\']([^"\']+)["\']',
        html
    )

    # Pattern foto: <img src="get_foto_ust.php?file=XXX.jpg">
    fotos = re.findall(
        r'<img\s+src=["\']get_foto_ust\.php\?file=([^"\']+)["\']',
        html
    )

    # Juga coba pattern terbalik (title sebelum href)
    links2 = re.findall(
        r'<a\s[^>]*title=["\']([^"\']+)["\'][^>]*href=["\']bio_ustadz\.php\?id=(\d+)["\']',
        html
    )
    # Normalize links2 ke format (id, name)
    for name, kid in links2:
        if (kid, name) not in links:
            links.append((kid, name))

    # Deduplicate by id
    seen = set()
    for kid, name in links:
        if kid in seen:
            continue
        seen.add(kid)
        name = name.strip()

        # Cari foto yang cocok (awali dengan id_)
        foto_file = ""
        for f in fotos:
            if f.startswith(f"{kid}_"):
                foto_file = f
                break

        entries.append({
            "kajianlive_id": int(kid),
            "name_kajianlive": name,
            "bio_url": f"{BASE}/bio_ustadz.php?id={kid}",
            "foto_file": foto_file,
            "foto_url": f"{BASE}/get_foto_ust.php?file={foto_file}" if foto_file else ""
        })

    return entries


def detect_max_page(html):
    """Deteksi halaman terakhir dari pagination."""
    # Pattern: <li class="end"><a href="daftar_ustadz.php?page=146">146</a></li>
    m = re.search(r'class=["\']end["\'][^>]*>\s*<a[^>]*>(\d+)</a>', html)
    if m:
        return int(m.group(1))
    return MAX_PAGE


def main():
    log(f"=== Crawl Daftar Ustadz KajianLive ===")

    # Fetch page 1 dulu untuk deteksi jumlah halaman
    url1 = f"{BASE}/daftar_ustadz.php?page=1"
    html1, ok = curl_fetch(url1)
    if not ok:
        log("ERROR: Gagal fetch halaman 1")
        sys.exit(1)

    max_page = detect_max_page(html1)
    log(f"Total halaman: {max_page}")

    all_ustadz = []
    seen_ids = set()

    for page in range(1, max_page + 1):
        url = f"{BASE}/daftar_ustadz.php?page={page}"
        if page == 1:
            html = html1  # sudah di-fetch
        else:
            time.sleep(DELAY)
            html, ok = curl_fetch(url)
            if not ok:
                log(f"  page {page}: GAGAL, skip")
                continue

        entries = parse_page(html)
        new_count = 0
        for e in entries:
            if e["kajianlive_id"] not in seen_ids:
                seen_ids.add(e["kajianlive_id"])
                all_ustadz.append(e)
                new_count += 1

        log(f"  page {page}/{max_page}: {new_count} ustadz baru (total: {len(all_ustadz)})")

    # Sort by id
    all_ustadz.sort(key=lambda x: x["kajianlive_id"])

    # Save
    output_path = OUTPUT
    result = {
        "crawled_at": datetime.now(JAKARTA_TZ).isoformat(),
        "source": "kajianlive.my.id/daftar_ustadz.php",
        "total_pages": max_page,
        "total_ustadz": len(all_ustadz),
        "ustadz": all_ustadz
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    log(f"=== Selesai: {len(all_ustadz)} ustadz disimpan ke {output_path} ===")


if __name__ == "__main__":
    main()
