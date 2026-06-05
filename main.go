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

type Source struct {
	ID      string `json:"id"`
	URL     string `json:"url"`
	Title   string `json:"title"`
	Sitename string `json:"sitename"`
	Snippet string `json:"snippet"`
	Accessed string `json:"accessed"`
}

type Asatidz struct {
	Name              string            `json:"name"`
	Slug              string            `json:"slug"`
	Id                string            `json:"id"`
	SourceURL         string            `json:"source_url"`
	Count             int               `json:"count"`
	Categories        []string          `json:"categories"`
	Bio               string            `json:"bio"`
	BioSource         string            `json:"bio_source"`
	BioQuote          string            `json:"bio_quote"`
	Education         []string          `json:"education"`
	EducationSource   string            `json:"education_source"`
	EducationQuote    string            `json:"education_quote"`
	Expertise         []string          `json:"expertise"`
	ExpertiseSource   string            `json:"expertise_source"`
	ExpertiseQuote    string            `json:"expertise_quote"`
	Karya             []string          `json:"kary"`
	KaryaSource       string            `json:"kary_source"`
	KaryaQuote        string            `json:"kary_quote"`
	SocialMedia       map[string]string `json:"social_media"`
	Sources           []Source          `json:"sources"`
	Foto              string            `json:"foto"`
	Jabatan           string            `json:"jabatan"`
	Completeness      int               `json:"completeness"`
}

// MasterEntry is the lightweight index entry for list/table rendering.
type MasterEntry struct {
	Id           string   `json:"id"`
	Name         string   `json:"name"`
	Slug         string   `json:"slug"`
	SourceURL    string   `json:"source_url"`
	Count        int      `json:"count"`
	Categories   []string `json:"categories"`
	HasBio       bool     `json:"has_bio"`
	HasFoto      bool     `json:"has_foto"`
	HasDetail    bool     `json:"has_detail"`
	Completeness int      `json:"completeness"`
}

type PageInfo struct {
	Number     int
	IsEllipsis bool
}

type PageData struct {
	Asatidz    []Asatidz
	Total      int
	Page       int
	PageSize   int
	TotalPages int
	Pages      []PageInfo
	HasPrev    bool
	HasNext    bool
	Query      string
	Sort       string
	Category   string
	MinCount   int
	Categories []string
}

var (
	asatidzData []Asatidz           // full data for list/table (loaded from master or enriched)
	detailData  map[string]Asatidz  // cache: slug → detail (loaded on-demand from detail/)
	dataMutex   sync.RWMutex
	detailDir   = "detail"
)

func loadMaster() {
	// Try loading from detail directory first
	if _, err := os.Stat("asatidz_master.json"); err == nil {
		data, err := os.ReadFile("asatidz_master.json")
		if err != nil {
			log.Fatal("Gagal baca asatidz_master.json:", err)
		}
		var master []map[string]interface{}
		json.Unmarshal(data, &master)
		
		// Convert to Asatidz (with completeness score derived from master flags)
		asatidzData = make([]Asatidz, len(master))
		for i, m := range master {
			a := Asatidz{
				Name:      m["name"].(string),
				SourceURL: m["source_url"].(string),
				Count:     int(m["count"].(float64)),
			}
			// Read id if present
			if idVal, ok := m["id"].(string); ok {
				a.Id = idVal
				a.Slug = idVal // also set slug for backward compat
			}
			// Compute completeness from master flags
			if hasBio, ok := m["has_bio"].(bool); ok && hasBio {
				a.Completeness += 35
			}
			if hasFoto, ok := m["has_foto"].(bool); ok && hasFoto {
				a.Completeness += 25
			}
			// has_detail can be bool true or non-empty array
			if hd, ok := m["has_detail"]; ok {
				switch v := hd.(type) {
				case bool:
					if v {
						a.Completeness += 25
					}
				case []interface{}:
					if len(v) > 0 {
						a.Completeness += 25
					}
				}
			}
			if a.Count > 0 {
				a.Completeness += 15
			}
			asatidzData[i] = a
		}
		detailData = make(map[string]Asatidz)
		log.Printf("Loaded %d master entries", len(asatidzData))
	} else {
		// Fallback: load enriched data
		loadEnriched()
	}
}

func loadEnriched() {
	data, err := os.ReadFile("asatidz_enriched.json")
	if err != nil {
		// Fallback to original
		data, err = os.ReadFile("asatidz.json")
		if err != nil {
			log.Fatal("Gagal baca asatidz.json:", err)
		}
	}
	dataMutex.Lock()
	json.Unmarshal(data, &asatidzData)
	dataMutex.Unlock()
	detailData = make(map[string]Asatidz)
	log.Printf("Loaded %d asatidz", len(asatidzData))
}

// Backward compat: loadData tries master first
func loadData() {
	loadMaster()
}

// slugify converts a name to a URL-safe slug.
func slugify(name string) string {
	s := strings.ToLower(name)
	var result strings.Builder
	for _, c := range s {
		if (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-' || c == ' ' {
			result.WriteRune(c)
		}
	}
	s = result.String()
	s = strings.Join(strings.Fields(s), "-")
	return strings.Trim(s, "-")
}

// loadDetail loads a single asatidz detail from detail/{id}.json.
// The id parameter is the profile's unique id (e.g. "kajian-abdullah-roy").
// Returns cached version if available.
func loadDetail(id string) (Asatidz, error) {
	// Check cache first
	dataMutex.RLock()
	if d, ok := detailData[id]; ok {
		dataMutex.RUnlock()
		return d, nil
	}
	dataMutex.RUnlock()

	// Load from file: try id-based path first, then fallback to slug-based
	path := detailDir + "/" + id + ".json"
	data, err := os.ReadFile(path)
	if err != nil {
		// Fallback: try without kajian- prefix for backward compat
		if strings.HasPrefix(id, "kajian-") {
			fallbackPath := detailDir + "/" + strings.TrimPrefix(id, "kajian-") + ".json"
			data, err = os.ReadFile(fallbackPath)
		}
		if err != nil {
			return Asatidz{}, err
		}
	}

	var detail Asatidz
	if err := json.Unmarshal(data, &detail); err != nil {
		return Asatidz{}, err
	}

	// Cache it
	dataMutex.Lock()
	detailData[id] = detail
	dataMutex.Unlock()

	return detail, nil
}

func countEnriched() int {
	count := 0
	for _, a := range asatidzData {
		if a.Bio != "" {
			count++
		}
	}
	return count
}

func loadDataFromSlice(data []Asatidz) {
	dataMutex.Lock()
	asatidzData = data
	dataMutex.Unlock()
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
	// Max 4 visible: 1, (ellipsis), up to 2 near current, (ellipsis), last
	// Near current: show current and 1 neighbor on each side (max 3 middle)
	// But cap total non-ellipsis at 4: 1 + 2 middle + last
	if total <= 7 {
		// Small total: show all pages
		var pages []PageInfo
		for i := 1; i <= total; i++ {
			pages = append(pages, PageInfo{Number: i})
		}
		return pages
	}

	// Determine which pages to show (excluding 1 and total)
	// Show current and up to 1 on each side = 3 middle max
	// But we want max 4 total, so: 1 + at most 2 middle + total
	// Strategy: show current page + 1 after (or 1 before if at end)
	start := current
	end := current + 1
	if end > total-1 {
		end = total - 1
		start = current - 1
		if start < 2 {
			start = 2
		}
	}

	// At beginning: show 1, 2, 3, ..., total
	if current <= 3 {
		start = 2
		end = 3
	}
	// At end: show 1, ..., total-2, total-1, total
	if current >= total-2 {
		start = total - 2
		end = total - 1
	}

	var pages []PageInfo
	pages = append(pages, PageInfo{Number: 1})

	if start > 2 {
		pages = append(pages, PageInfo{IsEllipsis: true})
	}

	for i := start; i <= end; i++ {
		if i > 1 && i < total {
			pages = append(pages, PageInfo{Number: i})
		}
	}

	if end < total-1 {
		pages = append(pages, PageInfo{IsEllipsis: true})
	}

	pages = append(pages, PageInfo{Number: total})

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

// renderResults renders the table + pagination HTML fragment (used by both / and /api/search)
func renderResults(w http.ResponseWriter, pageData PageData) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")

	fmt.Fprintf(w, `<p class="text-sm text-gray-500 mb-3">Menampilkan %d dari %d asatidz`, len(pageData.Asatidz), pageData.Total)
	if pageData.TotalPages > 1 {
		fmt.Fprintf(w, ` — Halaman %d dari %d`, pageData.Page, pageData.TotalPages)
	}
	fmt.Fprintf(w, `</p><div class="bg-white rounded-lg shadow overflow-hidden mb-4"><table class="w-full text-left text-sm"><thead class="bg-gray-50 border-b-2 border-gray-200"><tr><th class="px-4 py-3 font-semibold text-gray-600 w-20"></th><th class="px-4 py-3 font-semibold text-gray-600 cursor-pointer hover:text-blue-600 select-none" hx-get="/api/search" hx-target="#results-container" hx-include="[name='q'],[name='size'],[name='cat'],[name='min_count']" hx-vals='{"sort":"%s"}'>Nama Asatidz<span class="ml-1 text-xs">%s</span></th><th class="px-4 py-3 font-semibold text-gray-600 text-center w-24 cursor-pointer hover:text-blue-600 select-none" hx-get="/api/search" hx-target="#results-container" hx-include="[name='q'],[name='size'],[name='cat'],[name='min_count']" hx-vals='{"sort":"%s"}'>Kajian<span class="ml-1 text-xs">%s</span></th></tr></thead><tbody class="divide-y divide-gray-100">`,
		nextSortAlpha(pageData.Sort), sortIndicatorAlpha(pageData.Sort),
		nextSortCount(pageData.Sort), sortIndicatorCount(pageData.Sort))
	for _, a := range pageData.Asatidz {
		// Heatmap button: greener/bluer = more complete, gray = minimal
		btnClass := "text-xs px-2 py-1 rounded cursor-default bg-gray-100 text-gray-400"
		btnTitle := "Belum ada profil"
		btnText := "profil"
		if a.Completeness >= 70 {
			// Penuh: bio + foto + detail → green
			btnClass = "text-xs px-2 py-1 rounded font-semibold cursor-pointer bg-green-500 text-white hover:bg-green-600 shadow-sm"
			btnTitle = "Profil lengkap"
			btnText = "profil"
		} else if a.Completeness >= 40 {
			// Parsial: bio ada tapi belum lengkap → blue
			btnClass = "text-xs px-2 py-1 rounded font-medium cursor-pointer bg-blue-400 text-white hover:bg-blue-500"
			btnTitle = "Lihat profil"
			btnText = "profil"
		} else if a.Bio != "" {
			// Minimal: bio only → yellow/warm
			btnClass = "text-xs px-2 py-1 rounded cursor-pointer bg-yellow-300 text-yellow-900 hover:bg-yellow-400"
			btnTitle = "Profil tersedia"
			btnText = "profil"
		}
		fmt.Fprintf(w, `<tr class="hover:bg-blue-50 transition-colors"><td class="px-4 py-3 text-center"><button class="%s" onclick="showDetail('%s')" title="%s">%s</button></td><td class="px-4 py-3 font-medium text-gray-800">%s</td><td class="px-4 py-3 text-center">`, btnClass, a.Name, btnTitle, btnText, a.Name)
		if a.Count > 0 {
			fmt.Fprintf(w, `<span class="inline-block bg-blue-100 text-blue-700 text-xs font-bold px-2 py-1 rounded-full">%d</span>`, a.Count)
		} else {
			fmt.Fprintf(w, `<span class="text-gray-300">-</span>`)
		}
		fmt.Fprintf(w, `</td></tr>`)
	}
	fmt.Fprintf(w, `</tbody></table></div>`)

	if pageData.TotalPages > 1 {
		fmt.Fprintf(w, `<div class="flex items-center justify-center gap-1 whitespace-nowrap">`)
		if pageData.HasPrev {
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
		if pageData.HasNext {
			fmt.Fprintf(w, `<button class="px-3 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50" hx-get="/api/search" hx-target="#results-container" hx-vals='{"page": "%d"}' hx-include="[name='q'],[name='size'],[name='sort'],[name='cat'],[name='min_count']">Next →</button>`, pageData.Page+1)
		} else {
			fmt.Fprintf(w, `<span class="px-3 py-2 text-sm border border-gray-200 rounded text-gray-300 cursor-not-allowed">Next →</span>`)
		}
		fmt.Fprintf(w, `</div>`)
	}
}


func renderDetailProfile(w http.ResponseWriter, a Asatidz) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")

	_ = a.Count // used in kajianSection below

	// Helper: footnote marker (superscript number)
	fn := func(id string) string {
		return fmt.Sprintf(` <sup class="text-xs text-gray-400"><a href="#ref-%s" class="hover:text-blue-600">[%s]</a></sup>`, id, id)
	}

	// Bio section — footnote only, no blockquote
	bioContent := ""
	if a.Bio == "" {
		bioContent = "<span class='text-gray-400 text-sm italic'>Belum ada biografi tersedia</span>"
	} else {
		bioContent = fmt.Sprintf(`<p class="text-sm text-gray-700 leading-relaxed">%s</p>`, a.Bio)
	}
	bioFN := ""
	if a.Bio != "" && len(a.Sources) > 0 {
		srcIdx := 0
		for i, s := range a.Sources {
			if s.URL == a.BioSource {
				srcIdx = i
				break
			}
		}
		bioFN = fn(a.Sources[srcIdx].ID)
	}
	bioSection := fmt.Sprintf(`<div><h3 class="text-sm font-semibold text-gray-600 mb-2">Biografi%s</h3>%s</div>`, bioFN, bioContent)

	// Education section — footnote in header only
	eduSection := ""
	if len(a.Education) > 0 {
		srcIdx := 1 % len(a.Sources) // default: 2nd source (or 1st if only 1)
		for i, s := range a.Sources {
			if s.URL == a.EducationSource {
				srcIdx = i
				break
			}
		}
		eduFN := fn(a.Sources[srcIdx].ID)
		eduSection = fmt.Sprintf(`<div class="mt-4"><h3 class="text-sm font-semibold text-gray-600 mb-2">Pendidikan%s</h3><ul class="list-disc list-inside text-sm text-gray-700 space-y-1">`, eduFN)
		for _, e := range a.Education {
			eduSection += fmt.Sprintf(`<li>%s</li>`, e)
		}
		eduSection += `</ul></div>`
	}

	// Expertise section — footnote in header only
	expSection := ""
	if len(a.Expertise) > 0 {
		srcIdx := 2 % len(a.Sources) // default: 3rd source (wraps around)
		for i, s := range a.Sources {
			if s.URL == a.ExpertiseSource {
				srcIdx = i
				break
			}
		}
		expFN := fn(a.Sources[srcIdx].ID)
		expSection = fmt.Sprintf(`<div class="mt-4"><h3 class="text-sm font-semibold text-gray-600 mb-2">Topik Keahlian%s</h3><div class="flex flex-wrap gap-2">`, expFN)
		for _, ex := range a.Expertise {
			expSection += fmt.Sprintf(`<span class="px-2 py-1 bg-blue-50 text-blue-700 text-xs rounded-full border border-blue-200">%s</span>`, ex)
		}
		expSection += `</div></div>`
	}

	// Social media section
	socSection := ""
	smIcons := map[string][2]string{
		"youtube":       {"YouTube", "M23.5 6.19a3.02 3.02 0 0 0-2.12-2.14C19.75 3.5 12 3.5 12 3.5s-7.75 0-9.38.55A3.02 3.02 0 0 0 .5 6.19 31.6 31.6 0 0 0 0 12a31.6 31.6 0 0 0 .5 5.81 3.02 3.02 0 0 0 2.12 2.14c1.63.55 9.38.55 9.38.55s7.75 0 9.38-.55a3.02 3.02 0 0 0 2.12-2.14A31.6 31.6 0 0 0 24 12a31.6 31.6 0 0 0-.5-5.81z"},
		"facebook":      {"Facebook", "M24 12c0-6.627-5.373-12-12-12S0 5.373 0 12c0 5.99 4.388 10.954 10.125 11.854V15.47H7.078V12h3.047V9.356c0-3.007 1.792-4.668 4.533-4.668 1.312 0 2.686.234 2.686.234v2.953H15.83c-1.491 0-1.956.925-1.956 1.875V12h3.328l-.532 3.47h-2.796v8.384C19.612 22.954 24 17.99 24 12z"},
		"instagram":     {"Instagram", "M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 1 0 0 12.324 6.162 6.162 0 0 0 0-12.324zM12 16a4 4 0 1 1 0-8 4 4 0 0 1 0 8zm6.406-11.845a1.44 1.44 0 1 0 0 2.881 1.44 1.44 0 0 0 0-2.881z"},
		"twitter":       {"Twitter", "M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"},
		"telegram":      {"Telegram", "M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.479.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"},
		"website":       {"Website", "M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm0 22C6.477 22 2 17.523 2 12S6.477 2 12 2s10 4.477 10 10-4.477 10-10 10zm-1-11v6h2v-6h-2zm0-4v2h2V7h-2z"},
		"youtube_video": {"YouTube", "M23.5 6.19a3.02 3.02 0 0 0-2.12-2.14C19.75 3.5 12 3.5 12 3.5s-7.75 0-9.38.55A3.02 3.02 0 0 0 .5 6.19 31.6 31.6 0 0 0 0 12a31.6 31.6 0 0 0 .5 5.81 3.02 3.02 0 0 0 2.12 2.14c1.63.55 9.38.55 9.38.55s7.75 0 9.38-.55a3.02 3.02 0 0 0 2.12-2.14A31.6 31.6 0 0 0 24 12a31.6 31.6 0 0 0-.5-5.81z"},
	}

	sm := a.SocialMedia
	if len(sm) > 0 {
		socSection = `<div class="mt-4"><h3 class="text-sm font-semibold text-gray-600 mb-2">Media Sosial</h3><div class="flex flex-wrap gap-2">`
		for _, key := range []string{"youtube", "facebook", "instagram", "twitter", "telegram", "website", "youtube_video"} {
			if url, ok := sm[key+"_url"]; ok && url != "" {
				info := smIcons[key]
				label := info[0]
				socSection += fmt.Sprintf(`<a href="%s" target="_blank" rel="noopener" class="flex items-center gap-1.5 px-3 py-1.5 bg-gray-100 hover:bg-gray-200 rounded-lg text-xs text-gray-700 transition-colors font-medium">%s</a>`, url, label)
			} else if url, ok := sm[key]; ok && url != "" && !strings.Contains(url, "_") {
				info := smIcons[key]
				label := info[0]
				socSection += fmt.Sprintf(`<a href="%s" target="_blank" rel="noopener" class="flex items-center gap-1.5 px-3 py-1.5 bg-gray-100 hover:bg-gray-200 rounded-lg text-xs text-gray-700 transition-colors font-medium">%s</a>`, url, label)
			}
		}
		socSection += `</div></div>`
	}

	// Karya section
	karyaSection := ""
	if len(a.Karya) > 0 {
		karyaFN := ""
		if a.KaryaSource != "" {
			for i, s := range a.Sources {
				if s.URL == a.KaryaSource {
					karyaFN = fn(a.Sources[i].ID)
					break
				}
			}
		}
		karyaSection = fmt.Sprintf(`<div class="mt-4"><h3 class="text-sm font-semibold text-gray-600 mb-2">Karya <span class="text-xs font-normal text-gray-400">(Buku, Penelitian, Aplikasi, Program)</span>%s</h3><ul class="list-disc list-inside text-sm text-gray-700 space-y-1">`, karyaFN)
		for _, k := range a.Karya {
			karyaSection += fmt.Sprintf(`<li>%s</li>`, k)
		}
		karyaSection += `</ul></div>`
	}

	// Kajian count section
	kajianSection := ""
	if a.Count > 0 {
		kajianSection = fmt.Sprintf(`<div class="mt-4"><h3 class="text-sm font-semibold text-gray-600 mb-2">Kajian</h3><p class="text-sm text-gray-700"><span class="font-bold text-blue-600">%d</span> kajian di <a href="%s" target="_blank" rel="noopener" class="text-blue-600 hover:underline">kajian.net</a></p></div>`, a.Count, a.SourceURL)
	}

	// References section — Wikipedia-style "Daftar Pustaka"
	// Format: [1] "judul artikel" — URL (diakses YYYY-MM-DD).
	refSection := ""
	if len(a.Sources) > 0 {
		refSection = `<div class="mt-6 pt-4 border-t border-gray-200"><h3 class="text-xs font-semibold text-gray-500 mb-2 uppercase tracking-wider">Referensi</h3><ol class="list-decimal list-inside text-xs text-gray-500 space-y-1.5">`
		for _, s := range a.Sources {
			title := s.Title
			if title == "" {
				title = s.URL
			}
			accessed := s.Accessed
			if accessed == "" {
				accessed = "2026-06-03"
			}
			refSection += fmt.Sprintf(`<li id="ref-%s" class="break-words"><span class="text-gray-400">[%s]</span> <a href="%s" target="_blank" rel="noopener" class="text-blue-500 hover:underline">"%s"</a><br><span class="text-gray-400 ml-4">%s</span> <span class="text-gray-400">(diakses %s)</span>.</li>`, s.ID, s.ID, s.URL, title, s.URL, accessed)
		}
		refSection += `</ol></div>`
	}

	// Header with foto + jabatan
	fotoHTML := ""
	// Build initials
	initials := ""
	parts := strings.Fields(a.Name)
	for i, p := range parts {
		if i >= 2 {
			break
		}
		initials += strings.ToUpper(string([]rune(p)[0]))
	}
	placeholder := fmt.Sprintf(`<div class="w-16 h-16 rounded-full bg-white/20 border-2 border-white/30 flex items-center justify-center text-white text-lg font-bold shrink-0">%s</div>`, initials)
	if a.Foto != "" {
		imgTag := fmt.Sprintf(`<img src="%s" alt="%s" class="w-16 h-16 rounded-full object-cover border-2 border-white/30 shrink-0" onerror="this.style.display='none'">`, a.Foto, a.Name)
		fotoHTML = `<div class="relative w-16 h-16 shrink-0">` + imgTag + placeholder + `</div>`
	} else {
		fotoHTML = placeholder
	}

	jabatanHTML := ""
	if a.Jabatan != "" {
		jabatanHTML = fmt.Sprintf(`<span class="text-xs text-white/70 mt-0.5">%s</span>`, a.Jabatan)
	}

	fmt.Fprintf(w, `<div class="bg-white rounded-xl shadow-lg border border-gray-100 overflow-hidden relative"><button onclick="closeDetailPanel()" class="absolute top-3 right-3 p-1.5 hover:bg-white/20 rounded-full transition-colors text-white text-xl leading-none z-10">&times;</button><div class="px-6 py-4 bg-gradient-to-r from-blue-600 to-blue-700 text-white"><div class="flex items-center gap-3">%s<div class="min-w-0"><h2 class="text-lg font-bold truncate pr-8">%s</h2>%s</div></div></div><div class="p-6">%s%s%s%s%s%s%s</div></div>`,
		fotoHTML, a.Name, jabatanHTML, bioSection, eduSection, expSection, karyaSection, kajianSection, socSection, refSection)
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func nextSortAlpha(current string) string {
	if current == "alpha_asc" {
		return "alpha_desc"
	}
	return "alpha_asc"
}

func sortIndicatorAlpha(current string) string {
	if current == "alpha_asc" {
		return "↑"
	}
	if current == "alpha_desc" {
		return "↓"
	}
	return ""
}

func nextSortCount(current string) string {
	if current == "count_desc" {
		return "count_asc"
	}
	return "count_desc"
}

func sortIndicatorCount(current string) string {
	if current == "count_desc" {
		return "↓"
	}
	if current == "count_asc" {
		return "↑"
	}
	return ""
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
    <title>Profil Asatidz Sunnah</title>
    <script src="https://unpkg.com/htmx.org@1.9.10"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @keyframes pulse-ring { 0%% { transform: scale(0.8); opacity: 0.5; } 100%% { transform: scale(1.4); opacity: 0; } }
        .pulse-ring::before { content: ''; position: absolute; inset: 0; border-radius: 9999px; background: #3b82f6; animation: pulse-ring 2s ease-out infinite; z-index: -1; }
        #filter-panel-wrap { position: fixed; bottom: 6.5rem; right: 1.5rem; z-index: 9998; transition: opacity 0.2s, transform 0.2s; }
        #filter-panel-wrap.hidden { opacity: 0; transform: translateY(8px) scale(0.95); pointer-events: none; }
        #filter-panel-wrap:not(.hidden) { opacity: 1; transform: translateY(0) scale(1); }
        #filter-toggle { position: fixed !important; bottom: 2.5rem !important; right: 1.5rem !important; z-index: 9999 !important; }
    </style>
</head>
<body class="bg-gray-100 min-h-screen pb-8">
<div class="max-w-5xl mx-auto px-4 py-8">
    <h1 class="text-3xl font-bold text-gray-800 mb-6">Profil Asatidz Sunnah</h1>
    <div class="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-6 text-sm text-yellow-800 leading-relaxed">
        <p class="mb-2"><strong>⚠️ Disclaimer:</strong> Ini adalah <em>prototype</em> profil asatidz yang dikumpulkan menggunakan metode <strong>OSINT</strong> (<em>Open-Source Intelligence</em> — pengumpulan informasi dari sumber terbuka seperti Wikipedia, situs publik, dan media sosial). Data mungkin tidak lengkap atau kurang akurat.</p>
        <p>Saran dan kritik: <a href="mailto:itdakwah@gmail.com" class="text-yellow-600 underline hover:text-yellow-800">itdakwah@gmail.com</a></p>
    </div>
    <input class="w-full p-3 mb-6 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none" type="text" name="q" id="search-input" placeholder="Cari nama asatidz..." value="" hx-get="/api/search" hx-trigger="keyup changed delay:300ms, change" hx-target="#results-container" hx-include="[name='size']" hx-indicator="#spinner">
    <div id="spinner" class="htmx-indicator text-gray-400 text-sm mb-2">Mencari...</div>
    <div id="results-container">`)

		renderResults(w, pageData)

		fmt.Fprintf(w, `</div><footer class="mt-8 pt-6 border-t border-gray-200 text-center text-gray-400 text-xs"><p class="mb-1">Dibuat dengan Go + HTMX</p><p>Sumber data: <a href="https://kajian.net" target="_blank" rel="noopener" class="text-blue-400 hover:underline">kajian.net</a></p></footer></div>`)

		// Filter floating button + panel
		fmt.Fprintf(w, `
<button id="filter-toggle" class="fixed bottom-6 right-6 z-50 p-4 bg-blue-600 text-white rounded-full shadow-lg hover:bg-blue-700 transition-colors pulse-ring relative" onclick="toggleFilterPanel()">
<svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" /></svg>
</button>
<div id="filter-panel-wrap" class="hidden">
<div id="filter-panel" class="w-80 bg-white rounded-xl shadow-2xl border border-gray-100 overflow-hidden">
<div class="px-4 py-3 bg-gray-50 border-b flex items-center justify-between"><span class="font-semibold text-gray-700 text-sm">Filter</span><button onclick="clearFilters()" class="text-xs text-blue-600 hover:underline">Reset</button></div>
<div class="p-4 space-y-4">
<div><label class="block text-xs font-medium text-gray-500 mb-1">Urutkan</label><select name="sort" class="w-full p-2 border border-gray-300 rounded-lg text-sm" hx-get="/api/search" hx-trigger="change" hx-target="#results-container" hx-include="[name='q'],[name='size'],[name='cat'],[name='min_count']"><option value="alpha_asc">A → Z</option><option value="alpha_desc">Z → A</option><option value="count_desc">Kajian terbanyak</option><option value="count_asc">Kajian sedikit</option></select></div>
<div><label class="block text-xs font-medium text-gray-500 mb-1">Kategori</label><select name="cat" class="w-full p-2 border border-gray-300 rounded-lg text-sm" hx-get="/api/search" hx-trigger="change" hx-target="#results-container" hx-include="[name='q'],[name='size'],[name='sort'],[name='min_count']"><option value="">Semua</option></select></div>
<div><label class="block text-xs font-medium text-gray-500 mb-1">Minimal kajian</label><input type="number" name="min_count" min="0" placeholder="0" class="w-full p-2 border border-gray-300 rounded-lg text-sm" hx-get="/api/search" hx-trigger="keyup changed delay:500ms, change" hx-target="#results-container" hx-include="[name='q'],[name='size'],[name='sort'],[name='cat']"></div>
<div><label class="block text-xs font-medium text-gray-500 mb-1">Tampilkan</label><select name="size" class="w-full p-2 border border-gray-300 rounded-lg text-sm" hx-get="/api/search" hx-trigger="change" hx-target="#results-container" hx-include="[name='q'],[name='sort'],[name='cat'],[name='min_count']"><option value="5">5</option><option value="10">10</option><option value="15" selected>15</option><option value="20">20</option><option value="25">25</option><option value="50">50</option></select></div>
</div>
<div class="px-4 py-3 bg-gray-50 border-t"><button class="w-full py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700" onclick="toggleFilterPanel()">Terapkan</button></div>
</div>
</div><!-- /filter-panel-wrap -->
<div id="filter-backdrop" class="fixed inset-0 z-30 hidden" onclick="toggleFilterPanel()"></div>
<script>
function toggleFilterPanel(){document.getElementById('filter-panel-wrap').classList.toggle('hidden');document.getElementById('filter-backdrop').classList.toggle('hidden');}
function clearFilters(){document.querySelector('select[name="sort"]').value='alpha_asc';document.querySelector('select[name="cat"]').value='';document.querySelector('input[name="min_count"]').value='';document.querySelector('select[name="size"]').value='15';htmx.trigger('select[name="sort"]','change');}

function showDetail(name){fetch('/api/detail?name='+encodeURIComponent(name)).then(r=>r.text()).then(h=>{let p=document.getElementById('detail-panel');if(!p){p=document.createElement('div');p.id='detail-panel';p.className='fixed inset-0 z-[99999] flex items-center justify-center p-4 bg-black/50';p.innerHTML='<div class="relative z-10 w-full max-w-2xl max-h-[85vh] overflow-y-auto bg-white rounded-xl shadow-2xl" id="detail-content"></div>';p.onclick=function(e){if(e.target===p)closeDetailPanel()};document.body.appendChild(p)}document.getElementById('detail-content').innerHTML=h;history.pushState({detail:true},'')})}
function closeDetailPanel(){let p=document.getElementById('detail-panel');if(p)p.remove();if(history.state&&history.state.detail)history.back()}
document.addEventListener('keydown',function(e){if(e.key==='Escape')closeDetailPanel()});
window.addEventListener('popstate',function(e){closeDetailPanel()});

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

		renderResults(w, pageData)
	})


	http.HandleFunc("/api/detail", func(w http.ResponseWriter, r *http.Request) {
		name := r.URL.Query().Get("name")
		profileId := r.URL.Query().Get("id")
		
		// If id provided, look up by id directly
		if profileId != "" {
			detail, err := loadDetail(profileId)
			if err == nil {
				renderDetailProfile(w, detail)
				return
			}
		}
		
		if name == "" {
			http.Error(w, "Name or id required", 400)
			return
		}
		
		// Try loading from detail file by name (backward compat)
		slug := slugify(name)
		detail, err := loadDetail(slug)
		if err == nil {
			renderDetailProfile(w, detail)
			return
		}
		
		// Fallback: search in asatidzData
		dataMutex.RLock()
		defer dataMutex.RUnlock()
		for i := range asatidzData {
			if asatidzData[i].Name == name {
				renderDetailProfile(w, asatidzData[i])
				return
			}
		}
		http.Error(w, "Not found", 404)
	})

	http.HandleFunc("/api/reload", func(w http.ResponseWriter, r *http.Request) {
		loadData()
		w.Write([]byte("OK"))
	})

	log.Println("Server running at http://localhost:8080")
	http.ListenAndServe(":8080", nil)
}
