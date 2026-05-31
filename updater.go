package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/gocolly/colly/v2"
)

type Asatidz struct {
	Name      string `json:"name"`
	SourceURL string `json:"source_url"`
	Count     int    `json:"count"`
}

func main() {
	// 1. Baca data existing
	data, err := os.ReadFile("asatidz.json")
	if err != nil {
		log.Fatal(err)
	}

	var list []Asatidz
	json.Unmarshal(data, &list)

	// 2. Setup Crawler
	c := colly.NewCollector(
		colly.AllowedDomains("kajian.net"),
		colly.Async(true),
	)

	c.Limit(&colly.LimitRule{
		DomainGlob:  "kajian.net",
		Parallelism: 3,
		Delay:       500 * time.Millisecond,
	})

	var mu sync.Mutex

	// Hitung link kajian: <a> yang href-nya mengandung "/kajian-audio/"
	// dan bukan link sort/filter/nav
	c.OnHTML("a", func(e *colly.HTMLElement) {
		href := e.Attr("href")
		text := strings.TrimSpace(e.Text)

		// Filter: hanya link yang mengarah ke halaman kajian audio spesifik
		if strings.Contains(href, "/kajian-audio/") && len(text) > 3 {
			// Skip sort links, nav links
			lower := strings.ToLower(text)
			if lower == "alpha" || lower == "date" || lower == "sort descending" ||
				lower == "home" || lower == "ceramah" || lower == "artists" ||
				lower == "playlists" || lower == "statistics" || lower == "play" ||
				lower == "more" || lower == "" {
				return
			}

			url := e.Request.URL.String()
			mu.Lock()
			for i := range list {
				if list[i].SourceURL == url {
					list[i].Count++
				}
			}
			mu.Unlock()
		}
	})

	// 3. Crawl setiap asatidz yang punya URL valid
	fmt.Println("Updating record counts (v2)...")
	visited := 0
	for _, a := range list {
		if a.SourceURL != "" && !strings.Contains(a.SourceURL, "?zs=") {
			c.Visit(a.SourceURL)
			visited++
		}
	}
	c.Wait()

	fmt.Printf("Visited %d asatidz pages.\n", visited)

	// 4. Save
	file, _ := json.MarshalIndent(list, "", "  ")
	_ = os.WriteFile("asatidz.json", file, 0644)
	fmt.Println("Done. Updated data saved to asatidz.json")

	// 5. Stats
	withCount := 0
	zeroCount := 0
	for _, a := range list {
		if a.Count > 0 {
			withCount++
		} else {
			zeroCount++
		}
	}
	fmt.Printf("Stats: %d with count, %d zero, %d total\n", withCount, zeroCount, len(list))
}
