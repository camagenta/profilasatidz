package main

import (
	"encoding/json"
	"html/template"
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

type PageData struct {
	Asatidz    []Asatidz
	Total      int
	Page       int
	PageSize   int
	TotalPages int
	Pages      []int
	Query      string
	Sort       string
	Category   string
	MinCount   int
	PageSizeOpt []int
	Categories []string
}

var (
	tmpl        *template.Template
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
		// Search filter
		if q != "" && !strings.Contains(strings.ToLower(a.Name), q) {
			continue
		}
		// Category filter
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
		// Min count filter
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
	default: // alpha_asc
		sort.Slice(data, func(i, j int) bool { return data[i].Name < data[j].Name })
	}
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

	pages := make([]int, totalPages)
	for i := 0; i < totalPages; i++ {
		pages[i] = i + 1
	}

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
		PageSizeOpt: []int{5, 10, 15, 20, 25, 50},
		Categories: extractCategories(asatidzData),
	}
}

func parseParams(r *http.Request) (query, sort, category string, minCount, page, pageSize int) {
	query = r.URL.Query().Get("value")
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

	funcMap := template.FuncMap{
		"add": func(a, b int) int { return a + b },
		"sub": func(a, b int) int { return a - b },
	}
	tmpl = template.Must(template.New("").Funcs(funcMap).ParseFiles("index.html"))

	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		dataMutex.RLock()
		defer dataMutex.RUnlock()
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		pageData := paginate(asatidzData, 1, 15)
		tmpl.ExecuteTemplate(w, "index.html", pageData)
	})

	http.HandleFunc("/api/search", func(w http.ResponseWriter, r *http.Request) {
		query, sort, category, minCount, page, pageSize := parseParams(r)

		dataMutex.RLock()
		filtered := filter(asatidzData, query, category, minCount)
		dataMutex.RUnlock()

		sortData(filtered, sort)

		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		pageData := paginate(filtered, page, pageSize)
		pageData.Query = query
		pageData.Sort = sort
		pageData.Category = category
		pageData.MinCount = minCount
		tmpl.ExecuteTemplate(w, "results", pageData)
	})

	http.HandleFunc("/api/reload", func(w http.ResponseWriter, r *http.Request) {
		loadData()
		w.Write([]byte("OK"))
	})

	log.Println("Server running at http://localhost:8080")
	http.ListenAndServe(":8080", nil)
}
