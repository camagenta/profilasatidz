## Ringkasan

3 enhancement untuk meningkatkan kualitas enrichment dan tampilan profil asatidz:

---

## 1. Flag + Logo Wikipedia di Sosmed

**Problem:** Tidak ada indikator visual apakah seorang asatidz punya halaman Wikipedia.

**Solusi:**
- Tambah field `has_wikipedia` (bool) dan `wikipedia_url` (string) di struct `Asatidz`
- Di admin panel dan publik profil, tampilkan logo Wikipedia:
  - ✅ **Ada Wiki** → logo nyala (warna), bisa diklik → link ke halaman Wiki
  - ❌ **Tidak ada** → logo pucat abu-abu, tidak bisa diklik
- Field ini di-set saat enrichment (Wiki match berhasil) dan di-clear saat audit menemukan Wiki match salah

**Struct changes:**

```go
type Asatidz struct {
    // ... existing fields ...
    HasWikipedia  bool   `json:"has_wikipedia"`
    WikipediaURL  string `json:"wikipedia_url"`
}
```

---

## 2. Gemini Score untuk Verifikasi Wiki Match

**Problem:** Wikipedia search sering return halaman yang salah untuk nama generik (contoh: "Abu Usamah" match ke "Abu Bakar ash-Shiddiq" karena first_para mengandung kata "Usamah"). Lesson #14 dan #17 di AGENTS.md sudah mendokumentasikan ini.

**Solusi:**
- Setelah Wiki API return candidate, sebelum save: call Gemini API untuk verifikasi
- Prompt: "Apakah halaman Wikipedia dengan title [TITLE] tentang orang yang sama dengan [QUERY_NAME]? Jawab JSON: {match: true/false, score: 0.0-1.0, reason: ...}"
- Threshold: score >= 0.8 diterima, 0.5-0.8 flag untuk review, < 0.5 ditolak
- Field baru di struct:

```go
WikiVerified   bool    `json:"wiki_verified"`
WikiScore      float64 `json:"wiki_score"`
```

- Flag `wiki_verified` di admin panel: hijau (verified), kuning (review), merah (rejected)
- Untuk profil yang sudah enriched: **backfill** — re-run verification via Gemini untuk semua existing Wiki matches

**Gemini API budget:** Free tier = 1.500 calls/hari. 130 remaining profil + ~150 existing enriched = ~280 calls untuk backfill. Sangat feasible.

---

## 3. KajianLive Enrichment via Gemini

**Problem:** Banyak asatidz yang tidak punya Wikipedia page (7/8 gagal di batch 12 Jun). KajianLive punya data bio/profil tapi perlu dirapikan dan digabung dengan data existing.

**Solusi:**
- Scrape profil dari KajianLive (sudah ada `kajianlive_mapping.json`)
- Kirim scraped text ke Gemini untuk:
  1. **Segmentasi** → pisahkan jadi: bio, pendidikan, keahlian, karya, social media
  2. **Merge** → gabungkan dengan data existing tanpa menghilangkan konten sumber terdulu
  3. **Dedup** → deteksi dan hapus duplikat antar sumber
- Data KajianLive **tidak** ditampilkan di sosmed, hanya sebagai referensi/internal
- Field `sources` sudah ada di struct, cukup tambah entry baru dengan `sitename: "KajianLive"`

---

## Urgency & Priority

| # | Fitur | Priority | Effort |
|---|-------|----------|--------|
| 1 | Wikipedia flag di sosmed | Medium | Low (UI + 2 field) |
| 2 | Gemini verification score | **High** | Medium (API integration + backfill) |
| 3 | KajianLive enrichment | Medium | Medium (scrape + Gemini merge) |

**Rekomendasi:** Kerjakan #2 dulu karena langsung impact ke kualitas data. #1 dan #3 bisa parallel setelah #2 done.

---

## Catatan Teknis

- Gemini API key: setup di `.env` sebagai `GEMINI_API_KEY` (belum ada di VPS saat ini)
- Wikipedia API: sudah ada rate limiting (3 detik antar request), Gemini call tambakan ~1-2 detik per profil
- Cron enrichment: tambah delay untuk mengakomodasi Gemini call
- Backfill existing enriched profiles: buat script terpisah, jalan sekali
