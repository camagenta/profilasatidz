package main

import (
	"encoding/json"
	"fmt"
	"log"
	"math"
	"net/http"
	"os"
	"sort"
	"strconv"
	"strings"
	"sync"
)

type Asatidz struct {
	Name       string   `json:"name"`
	SourceURL  string   `json:"source_url"`
	Count      int      `json:"count"`
	Categories []string `json:"categories"`
}

type PageInfo struct {
	Number    int
	IsEllipsis bool
}

type PageData struct {
	Asatidz     []Asatidz
	Total       int
	Page        int
	PageSize    int
	TotalPages  int
	Pages       []PageInfo
	HasPrev     bool
	HasNext     bool
	Query       string
	Sort        string
	Category    string
	MinCount    int
	Categories  []string
}

var (
	asatidzData []Asatidz
	dataMutex   sync.RWMutex
)

func loadData() {
	data, err := os.ReadFile("asatidz.json")
	if err != nil {
		log.Fatal("Gagal baca asatidz.json:", err)
	}
	dataMutex.Lock()
	json.Unmarshal(data, &asatidzData)
	dataMutex.Unlock()
	log.Printf("Loaded %d asatidz", len(asatidzData))
}

func extractCategories(data []Asatidz) []string {
	catMap := map[string]bool{}
	for _, a := range data {
		for _, c := range a.Categories {
			catMap[c] = true
		}
	}
	cats := make([]string, 0, len(catMap))
	for c := range catMap {
		if c != "" {
			cats = append(cats, c)
		}
	}
	sort.Strings(cats)
	return cats
}

func filter(data []Asatidz, query, category string, minCount int) []Asatidz {
	var result []Asatidz
	q := strings.ToLower(query)
	for _, a := range data {
		if q != "" && !strings.Contains(strings.ToLower(a.Name), q) {
			continue
		}
		if category != "" {
			hasCat := false
			for _, c := range a.Categories {
				if c == category {
					hasCat = true
					break
				}
			}
			if !hasCat {
				continue
			}
		}
		if minCount > 0 && a.Count < minCount {
			continue
		}
		result = append(result, a)
	}
	return result
}

func sortData(data []Asatidz, sortBy string) {
	switch sortBy {
	case "alpha_desc":
		sort.Slice(data, func(i, j int) bool { return data[i].Name > data[j].Name })
	case "count_asc":
		sort.Slice(data, func(i, j int) bool { return data[i].Count < data[j].Count })
	case "count_desc":
		sort.Slice(data, func(i, j int) bool { return data[i].Count > data[j].Count })
	default:
		sort.Slice(data, func(i, j int) bool { return data[i].Name < data[j].Name })
	}
}

func generatePageRange(current, total int) []PageInfo {
	// Google-style: always show 1, last, and current neighborhood
	// Window = 1 before + current + 1 after = 3 visible numbers max
	window := 1
	start := current - window
	end := current + window

	// Near beginning: show 1 2 3 ... last
	if start <= 2 {
		start = 1
		end = 3
	}
	// Near end: show 1 ... (total-2) (total-1) total
	if end >= total-1 {
		end = total
		start = total - 2
		if start < 1 {
			start = 1
		}
	}

	var pages []PageInfo

	// Page 1
	pages = append(pages, PageInfo{Number: 1})

	// Ellipsis after 1
	if start > 2 {
		pages = append(pages, PageInfo{IsEllipsis: true})
	}

	// Middle range
	for i := start; i <= end; i++ {
		if i > 1 && i < total {
			pages = append(pages, PageInfo{Number: i})
		}
	}

	// Ellipsis before last
	if end < total-1 {
		pages = append(pages, PageInfo{IsEllipsis: true})
	}

	// Last page (if > 1)
	if total > 1 {
		pages = append(pages, PageInfo{Number: total})
	}

	return pages
}

func paginate(list []Asatidz, page, pageSize int) PageData {
	total := len(list)
	totalPages := int(math.Ceil(float64(total) / float64(pageSize)))
	if totalPages < 1 {
		totalPages = 1
	}
	if page < 1 {
		page = 1
	}
	if page > totalPages {
		page = totalPages
	}

	start := (page - 1) * pageSize
	end := start + pageSize
	if end > total {
		end = total
	}

	pages := generatePageRange(page, totalPages)

	listSlice := []Asatidz{}
	if start < total {
		listSlice = list[start:end]
	}

	return PageData{
		Asatidz:    listSlice,
		Total:      total,
		Page:       page,
		PageSize:   pageSize,
		TotalPages: totalPages,
		Pages:      pages,
		HasPrev:    page > 1,
		HasNext:    page < totalPages,
		Categories: extractCategories(asatidzData),
	}
}

func parseParams(r *http.Request) (query, sort, category string, minCount, page, pageSize int) {
	query = strings.ToLower(r.URL.Query().Get("q"))
	sort = r.URL.Query().Get("sort")
	if sort == "" {
		sort = "alpha_asc"
	}
	category = r.URL.Query().Get("cat")
	minCount, _ = strconv.Atoi(r.URL.Query().Get("min_count"))
	page, _ = strconv.Atoi(r.URL.Query().Get("page"))
	if page < 1 {
		page = 1
	}
	pageSize, _ = strconv.Atoi(r.URL.Query().Get("size"))
	if pageSize < 1 {
		pageSize = 15
	}
	return
}

func main() {
	loadData()

	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		dataMutex.RLock()
		pageData := paginate(asatidzData, 1, 15)
		dataMutex.RUnlock()

		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		fmt.Fprintf(w, `<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Direktori Asatidz Sunnah</title>
    <script src="https://unpkg.com/htmx.org@1.9.10"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @keyframes pulse-ring { 0%% { transform: scale(0.8); opacity: 0.5; } 100%% { transform: scale(1.4); opacity: 0; } }
        .pulse-ring::before { content: ''; position: absolute; inset: 0; border-radius: 9999px; background: #3b82f6; animation: pulse-ring 2s ease-out infinite; z-index: -1; }
        #filter-panel { transition: opacity 0.2s, transform 0.2s; }
        #filter-panel.hidden { opacity: 0; transform: translateY(8px) scale(0.95); pointer-events: none; }
        #filter-panel:not(.hidden) { opacity: 1; transform: translateY(0) scale(1); }
    </style>
</head>
<body class="bg-gray-100 min-h-screen pb-24">
<div class="max-w-5xl mx-auto px-4 py-8">
    <h1 class="text-3xl font-bold text-gray-800 mb-6">Direktori Asatidz Sunnah</h1>
    <input class="w-full p-3 mb-6 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none" type="text" name="q" id="search-input" placeholder="Cari nama asatidz..." value="" hx-get="/api/search" hx-trigger="keyup changed delay:300ms, change" hx-target="#results-container" hx-include="[name='size']" hx-indicator="#spinner">
    <div id="spinner" class="htmx-indicator text-gray-400 text-sm mb-2">Mencari...</div>
    <div id="results-container">`)

		fmt.Fprintf(w, `<p class="text-sm text-gray-500 mb-3">Menampilkan %d dari %d asatidz`, len(pageData.Asatidz), pageData.Total)
		if pageData.TotalPages > 1 {
			fmt.Fprintf(w, ` — Halaman %d dari %d`, pageData.Page, pageData.TotalPages)
		}
		fmt.Fprintf(w, `</p><div class="bg-white rounded-lg shadow overflow-hidden mb-4"><table class="w-full text-left text-sm"><thead class="bg-gray-50 border-b-2 border-gray-200"><tr><th class="px-4 py-3 font-semibold text-gray-600">Nama Asatidz</th><th class="px-4 py-3 font-semibold text-gray-600 text-center w-24">Kajian</th><th class="px-4 py-3 font-semibold text-gray-600 text-center w-32">Rujukan</th></tr></thead><tbody class="divide-y divide-gray-100">`)
		for _, a := range pageData.Asatidz {
			fmt.Fprintf(w, `<tr class="hover:bg-blue-50 transition-colors"><td class="px-4 py-3 font-medium text-gray-800">%s</td><td class="px-4 py-3 text-center">`, a.Name)
			if a.Count > 0 {
				fmt.Fprintf(w, `<span class="inline-block bg-blue-100 text-blue-700 text-xs font-bold px-2 py-1 rounded-full">%d</span>`, a.Count)
			} else {
				fmt.Fprintf(w, `<span class="text-gray-300">-</span>`)
			}
			fmt.Fprintf(w, `</td><td class="px-4 py-3 text-center"><a href="%s" target="_blank" rel="noopener" class="text-blue-600 hover:text-blue-800 hover:underline text-xs font-medium">↗ kajian.net</a></td></tr>`, a.SourceURL)
		}
		fmt.Fprintf(w, `</tbody></table></div>`)

		// Pagination
		if pageData.TotalPages > 1 {
			fmt.Fprintf(w, `<div class="flex items-center justify-center gap-1 whitespace-nowrap">`)
			if pageData.Page > 1 {
				fmt.Fprintf(w, `<button class="px-3 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50" hx-get="/api/search" hx-target="#results-container" hx-vals='{"page": "%d"}' hx-include="[name='q'],[name='size']">← Prev</button>`, pageData.Page-1)
			} else {
				fmt.Fprintf(w, `<span class="px-3 py-2 text-sm border border-gray-200 rounded text-gray-300 cursor-not-allowed">← Prev</span>`)
			}
			for _, p := range pageData.Pages {
			if p.IsEllipsis {
				fmt.Fprintf(w, `<span class="px-3 py-2 text-sm text-gray-400 select-none">…</span>`)
			} else if p.Number == pageData.Page {
				fmt.Fprintf(w, `<span class="px-3 py-2 text-sm bg-blue-600 text-white rounded font-medium">%d</span>`, p.Number)
			} else {
				fmt.Fprintf(w, `<button class="px-3 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50" hx-get="/api/search" hx-target="#results-container" hx-vals='{"page": "%d"}' hx-include="[name='q'],[name='size']">%d</button>`, p.Number, p.Number)
			}
		}
			if pageData.Page < pageData.TotalPages {
				fmt.Fprintf(w, `<button class="px-3 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50" hx-get="/api/search" hx-target="#results-container" hx-vals='{"page": "%d"}' hx-include="[name='q'],[name='size']">Next →</button>`, pageData.Page+1)
			} else {
				fmt.Fprintf(w, `<span class="px-3 py-2 text-sm border border-gray-200 rounded text-gray-300 cursor-not-allowed">Next →</span>`)
			}
			fmt.Fprintf(w, `</div>`)
		}

		fmt.Fprintf(w, `</div><footer class="mt-8 pt-6 border-t border-gray-200 text-center text-gray-400 text-xs"><p class="mb-1">Dibuat dengan Go + HTMX</p><p>Sumber data: <a href="https://kajian.net" target="_blank" rel="noopener" class="text-blue-400 hover:underline">kajian.net</a></p></footer></div>`)

		// Filter floating button + panel
		fmt.Fprintf(w, `
<button id="filter-toggle" class="fixed bottom-6 right-6 z-50 p-4 bg-blue-600 text-white rounded-full shadow-lg hover:bg-blue-700 transition-colors pulse-ring relative" onclick="toggleFilterPanel()">
<svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" /></svg>
</button>
<div id="filter-panel" class="fixed bottom-24 right-6 z-40 w-80 bg-white rounded-xl shadow-2xl border border-gray-100 hidden overflow-hidden">
<div class="px-4 py-3 bg-gray-50 border-b flex items-center justify-between"><span class="font-semibold text-gray-700 text-sm">Filter</span><button onclick="clearFilters()" class="text-xs text-blue-600 hover:underline">Reset</button></div>
<div class="p-4 space-y-4">
<div><label class="block text-xs font-medium text-gray-500 mb-1">Urutkan</label><select name="sort" class="w-full p-2 border border-gray-300 rounded-lg text-sm" hx-get="/api/search" hx-trigger="change" hx-target="#results-container" hx-include="[name='q'],[name='size'],[name='cat'],[name='min_count']"><option value="alpha_asc">A → Z</option><option value="alpha_desc">Z → A</option><option value="count_desc">Kajian terbanyak</option><option value="count_asc">Kajian sedikit</option></select></div>
<div><label class="block text-xs font-medium text-gray-500 mb-1">Kategori</label><select name="cat" class="w-full p-2 border border-gray-300 rounded-lg text-sm" hx-get="/api/search" hx-trigger="change" hx-target="#results-container" hx-include="[name='q'],[name='size'],[name='sort'],[name='min_count']"><option value="">Semua</option></select></div>
<div><label class="block text-xs font-medium text-gray-500 mb-1">Minimal kajian</label><input type="number" name="min_count" min="0" placeholder="0" class="w-full p-2 border border-gray-300 rounded-lg text-sm" hx-get="/api/search" hx-trigger="keyup changed delay:500ms, change" hx-target="#results-container" hx-include="[name='q'],[name='size'],[name='sort'],[name='cat']"></div>
<div><label class="block text-xs font-medium text-gray-500 mb-1">Tampilkan</label><select name="size" class="w-full p-2 border border-gray-300 rounded-lg text-sm" hx-get="/api/search" hx-trigger="change" hx-target="#results-container" hx-include="[name='q'],[name='sort'],[name='cat'],[name='min_count']"><option value="5">5</option><option value="10">10</option><option value="15" selected>15</option><option value="20">20</option><option value="25">25</option><option value="50">50</option></select></div>
</div>
<div class="px-4 py-3 bg-gray-50 border-t"><button class="w-full py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700" onclick="toggleFilterPanel()">Terapkan</button></div>
</div>
<div id="filter-backdrop" class="fixed inset-0 z-30 hidden" onclick="toggleFilterPanel()"></div>
<script>
function toggleFilterPanel(){document.getElementById('filter-panel').classList.toggle('hidden');document.getElementById('filter-backdrop').classList.toggle('hidden');}
function clearFilters(){document.querySelector('select[name="sort"]').value='alpha_asc';document.querySelector('select[name="cat"]').value='';document.querySelector('input[name="min_count"]').value='';document.querySelector('select[name="size"]').value='15';htmx.trigger('select[name="sort"]','change');}
</script>
</body></html>`)
	})

	http.HandleFunc("/api/search", func(w http.ResponseWriter, r *http.Request) {
		query, sort, category, minCount, page, pageSize := parseParams(r)

		dataMutex.RLock()
		filtered := filter(asatidzData, query, category, minCount)
		dataMutex.RUnlock()

		sortData(filtered, sort)

		pageData := paginate(filtered, page, pageSize)
		pageData.Query = query
		pageData.Sort = sort
		pageData.Category = category
		pageData.MinCount = minCount

		w.Header().Set("Content-Type", "text/html; charset=utf-8")

		// Results fragment
		fmt.Fprintf(w, `<p class="text-sm text-gray-500 mb-3">Menampilkan %d dari %d asatidz`, len(pageData.Asatidz), pageData.Total)
		if pageData.TotalPages > 1 {
			fmt.Fprintf(w, ` — Halaman %d dari %d`, pageData.Page, pageData.TotalPages)
		}
		fmt.Fprintf(w, `</p><div class="bg-white rounded-lg shadow overflow-hidden mb-4"><table class="w-full text-left text-sm"><thead class="bg-gray-50 border-b-2 border-gray-200"><tr><th class="px-4 py-3 font-semibold text-gray-600">Nama Asatidz</th><th class="px-4 py-3 font-semibold text-gray-600 text-center w-24">Kajian</th><th class="px-4 py-3 font-semibold text-gray-600 text-center w-32">Rujukan</th></tr></thead><tbody class="divide-y divide-gray-100">`)
		for _, a := range pageData.Asatidz {
			fmt.Fprintf(w, `<tr class="hover:bg-blue-50 transition-colors"><td class="px-4 py-3 font-medium text-gray-800">%s</td><td class="px-4 py-3 text-center">`, a.Name)
			if a.Count > 0 {
				fmt.Fprintf(w, `<span class="inline-block bg-blue-100 text-blue-700 text-xs font-bold px-2 py-1 rounded-full">%d</span>`, a.Count)
			} else {
				fmt.Fprintf(w, `<span class="text-gray-300">-</span>`)
			}
			fmt.Fprintf(w, `</td><td class="px-4 py-3 text-center"><a href="%s" target="_blank" rel="noopener" class="text-blue-600 hover:text-blue-800 hover:underline text-xs font-medium">↗ kajian.net</a></td></tr>`, a.SourceURL)
		}
		fmt.Fprintf(w, `</tbody></table></div>`)

		// Pagination
		if pageData.TotalPages > 1 {
			fmt.Fprintf(w, `<div class="flex items-center justify-center gap-1 whitespace-nowrap">`)
			if pageData.Page > 1 {
				fmt.Fprintf(w, `<button class="px-3 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50" hx-get="/api/search" hx-target="#results-container" hx-vals='{"page": "%d"}' hx-include="[name='q'],[name='size'],[name='sort'],[name='cat'],[name='min_count']">← Prev</button>`, pageData.Page-1)
			} else {
				fmt.Fprintf(w, `<span class="px-3 py-2 text-sm border border-gray-200 rounded text-gray-300 cursor-not-allowed">← Prev</span>`)
			}
			for _, p := range pageData.Pages {
				if p.IsEllipsis {
					fmt.Fprintf(w, `<span class="px-3 py-2 text-sm text-gray-400 select-none">…</span>`)
				} else if p.Number == pageData.Page {
					fmt.Fprintf(w, `<span class="px-3 py-2 text-sm bg-blue-600 text-white rounded font-medium">%d</span>`, p.Number)
				} else {
					fmt.Fprintf(w, `<button class="px-3 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50" hx-get="/api/search" hx-target="#results-container" hx-vals='{"page": "%d"}' hx-include="[name='q'],[name='size'],[name='sort'],[name='cat'],[name='min_count']">%d</button>`, p.Number, p.Number)
				}
			}
			if pageData.Page < pageData.TotalPages {
				fmt.Fprintf(w, `<button class="px-3 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50" hx-get="/api/search" hx-target="#results-container" hx-vals='{"page": "%d"}' hx-include="[name='q'],[name='size'],[name='sort'],[name='cat'],[name='min_count']">Next →</button>`, pageData.Page+1)
			} else {
				fmt.Fprintf(w, `<span class="px-3 py-2 text-sm border border-gray-200 rounded text-gray-300 cursor-not-allowed">Next →</span>`)
			}
			fmt.Fprintf(w, `</div>`)
		}
	})

	http.HandleFunc("/api/reload", func(w http.ResponseWriter, r *http.Request) {
		loadData()
		w.Write([]byte("OK"))
	})

	log.Println("Server running at http://localhost:8080")
	http.ListenAndServe(":8080", nil)
}
