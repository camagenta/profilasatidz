package main

import (
	"html/template"
	"log"
	"net/http"
	"os"
	"strings"
	"sync"

	"encoding/json"
)

type Asatidz struct {
	Name      string `json:"name"`
	SourceURL string `json:"source_url"`
	Count     int    `json:"count"`
}

var (
	tmpl         *template.Template
	asatidzData  []Asatidz
	dataMutex    sync.RWMutex
)

func loadData() {
	data, err := os.ReadFile("asatidz.json")
	if err != nil {
		log.Fatal("Gagal baca asatidz.json:", err)
	}
	json.Unmarshal(data, &asatidzData)
	log.Printf("Loaded %d asatidz", len(asatidzData))
}

func main() {
	loadData()
	tmpl = template.Must(template.ParseFiles("index.html"))

	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		dataMutex.RLock()
		defer dataMutex.RUnlock()
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		tmpl.Execute(w, asatidzData)
	})

	http.HandleFunc("/api/search", func(w http.ResponseWriter, r *http.Request) {
		query := strings.ToLower(r.URL.Query().Get("value"))
		var filtered []Asatidz
		dataMutex.RLock()
		for _, a := range asatidzData {
			if strings.Contains(strings.ToLower(a.Name), query) {
				filtered = append(filtered, a)
			}
		}
		dataMutex.RUnlock()
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		tmpl.ExecuteTemplate(w, "list", filtered)
	})

	http.HandleFunc("/api/reload", func(w http.ResponseWriter, r *http.Request) {
		loadData()
		w.Write([]byte("OK"))
	})

	log.Println("Server running at http://localhost:8080")
	http.ListenAndServe(":8080", nil)
}
