package main

import (
	"encoding/json"
	"html/template"
	"log"
	"math"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
)

type Asatidz struct {
	Name      string `json:"name"`
	SourceURL string `json:"source_url"`
	Count     int    `json:"count"`
}

type PageData struct {
	Asatidz    []Asatidz
	Total      int
	Page       int
	PageSize   int
	TotalPages int
	Pages      []int
	Query      string
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

	// Generate page numbers
	pages := make([]int, totalPages)
	for i := 0; i < totalPages; i++ {
		pages[i] = i + 1
	}

	return PageData{
		Asatidz:    list[start:end],
		Total:      total,
		Page:       page,
		PageSize:   pageSize,
		TotalPages: totalPages,
		Pages:      pages,
		Query:      "",
	}
}

func main() {
	loadData()

	// Register template funcs
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
		query := strings.ToLower(r.URL.Query().Get("value"))

		// Parse page
		page, _ := strconv.Atoi(r.URL.Query().Get("page"))
		if page < 1 {
			page = 1
		}

		// Parse page size
		pageSize, _ := strconv.Atoi(r.URL.Query().Get("size"))
		if pageSize < 1 {
			pageSize = 15
		}

		// Filter
		var filtered []Asatidz
		dataMutex.RLock()
		for _, a := range asatidzData {
			if query == "" || strings.Contains(strings.ToLower(a.Name), query) {
				filtered = append(filtered, a)
			}
		}
		dataMutex.RUnlock()

		// Paginate
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		pageData := paginate(filtered, page, pageSize)
		pageData.Query = query
		tmpl.ExecuteTemplate(w, "results", pageData)
	})

	http.HandleFunc("/api/reload", func(w http.ResponseWriter, r *http.Request) {
		loadData()
		w.Write([]byte("OK"))
	})

	log.Println("Server running at http://localhost:8080")
	http.ListenAndServe(":8080", nil)
}
