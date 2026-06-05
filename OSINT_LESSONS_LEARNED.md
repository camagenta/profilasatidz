# OSINT Enrichment — Lesson Learned

## Masalah Utama: IP Blocking & Rate Limiting

### Apa yang terjadi
- VPS IP (43.156.90.61) diblokir oleh Google, Bing, DuckDuckGo
- Semua search engine utama return CAPTCHA atau empty results
- Hanya Wikipedia API yang berfungsi (tidak memblokir IP VPS)
- Brave Search return JS-rendered HTML yang tidak bisa di-parse

### Solusi yang bisa diterapkan

#### 1. Residential Proxy
- Gunakan proxy dengan IP residential (bukan datacenter)
- Layanan: Bright Data, Oxylabs, Smartproxy, IPRoyal
- Rotasi IP otomatis setiap request
- Cost: ~$5-15/GB untuk residential proxy

#### 2. Wikipedia API (berfungsi tanpa proxy)
- `https://id.wikipedia.org/w/api.php` — tidak memblokir IP VPS
- Rate limit: ~200 requests/second (generous)
- Bisa extract: bio, education, social media (dari external links)
- Gunakan `action=query&prop=extracts` untuk full text
- Gunakan `action=query&prop=extlinks` untuk social media links

#### 3. Direct Website Scraping
- Banyak ustadz punya website resmi dengan bio lengkap
- Pattern URL: `https://{nama}.com` atau `https://{nama}.or.id`
- Scraping langsung ke website (bypass search engine)
- Gunakan `curl` dengan User-Agent browser

#### 4. Social Media Search
- YouTube: `https://www.youtube.com/results?search_query={nama}+ustadz`
- Instagram: `https://www.instagram.com/{username}/` (need login untuk full data)
- Facebook: Graph API (need token)
- Telegram: `https://t.me/{username}` (public channel)

#### 5. Alternative Search Engines (less aggressive blocking)
- SearXNG (self-hosted search engine aggregator)
- Mojeek (less aggressive bot detection)
- Startpage (Google results via proxy)

## Rekomendasi untuk Batch 2

1. **SearXNG self-hosted** di VPS yang berbeda IP
2. **Wikipedia API** untuk yang punya article (sudah terbukti)
3. **Direct site scraping** untuk pattern URL yang diketahui
4. **Social media search** via platform-specific endpoints
5. **Rate limiting**: delay 1-2 detik antar request, randomize User-Agent

## Data yang berhasil dikumpulkan (Batch 1)
- 9 asatidz enriched dari Wikipedia + direct site
- 269 belum enriched (tidak punya Wikipedia article)
- Data tersimpan: `asatidz_enriched.json`
