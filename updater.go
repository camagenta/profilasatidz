package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/url"
	"os"
	"regexp"
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

func normalizeURL(raw string) string {
	u, err := url.Parse(raw)
	if err != nil {
		return raw
	}
	u.Path = strings.TrimSuffix(u.Path, "/")
	u.RawQuery = ""
	u.Fragment = ""
	return u.String()
}

func main() {
	data, err := os.ReadFile("asatidz.json")
	if err != nil {
		log.Fatal(err)
	}

	var list []Asatidz
	json.Unmarshal(data, &list)

	for i := range list {
		list[i].Count = 0
	}

	// Build map with MULTIPLE URL variants
	urlMap := map[string]int{}
	debugNames := map[string]bool{
		"Abu Karimah 'Askariy": true,
		"Abu Rifqi Asrofi":     true,
		"Agus Hasan Bashori":   true,
		"Fadlan Fahamsyah":      true,
		"Syaikh Ali bin Salim Bukayyir Al-Yamani": true,
	}
	for i, a := range list {
		if a.SourceURL == "" {
			continue
		}
		norm := normalizeURL(a.SourceURL)
		urlMap[norm] = i
		// Also store raw
		urlMap[a.SourceURL] = i
		// Also store without https
		urlMap[strings.Replace(norm, "https://", "http://", 1)] = i
	}

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
	albumPattern := regexp.MustCompile(`/kajian-audio/Ceramah/([^/]+)/(.+)`)
	albumSeen := map[int]map[string]bool{}

	c.OnResponse(func(r *colly.Response) {
		reqURL := normalizeURL(r.Request.URL.String())
		mu.Lock()
		_, ok := urlMap[reqURL]
		if !ok {
			// Check if URL contains "Karimah" or "Rifqi" etc
			if strings.Contains(reqURL, "Karimah") || strings.Contains(reqURL, "Rifqi") ||
				strings.Contains(reqURL, "Bashori") || strings.Contains(reqURL, "Fahamsyah") ||
				strings.Contains(reqURL, "Bukayyir") {
				fmt.Printf("  [RESPONSE] URL not in map: %s\n", reqURL)
				// Print all map keys that contain "Karimah"
				for k := range urlMap {
					if strings.Contains(k, "Karimah") {
						fmt.Printf("  [MAP KEY] %s\n", k)
					}
				}
			}
		}
		mu.Unlock()
	})

	c.OnHTML("a", func(e *colly.HTMLElement) {
		href := e.Attr("href")
		text := strings.TrimSpace(e.Text)
		reqURL := normalizeURL(e.Request.URL.String())

		mu.Lock()
		defer mu.Unlock()

		idx, ok := urlMap[reqURL]
		if !ok {
			return
		}

		// Debug: track specific names
		if debugNames[list[idx].Name] {
			fmt.Printf("  [DEBUG] name=%s reqURL=%s\n", list[idx].Name, reqURL)
		}

		if !strings.Contains(href, "/kajian-audio/") {
			return
		}
		if len(text) < 3 {
			return
		}

		lower := strings.ToLower(text)
		skipWords := []string{"alpha", "date", "sort", "home", "ceramah", "artists",
			"playlists", "statistics", "play", "more", "download", "kumpulan"}
		for _, w := range skipWords {
			if lower == w || strings.HasPrefix(lower, w+" ") {
				return
			}
		}

		matches := albumPattern.FindStringSubmatch(href)
		if matches != nil {
			albumName, _ := url.QueryUnescape(matches[2])
			if strings.EqualFold(albumName, list[idx].Name) {
				return
			}
			if albumSeen[idx] == nil {
				albumSeen[idx] = map[string]bool{}
			}
			if albumSeen[idx][albumName] {
				return
			}
			albumSeen[idx][albumName] = true
			list[idx].Count++
			return
		}

		if strings.Contains(href, ".mp3") || strings.Contains(href, ".mp4") {
			list[idx].Count++
		}
	})

	fmt.Println("Updating record counts (v5)...")
	visited := 0
	for _, a := range list {
		if a.SourceURL != "" && !strings.Contains(a.SourceURL, "?zs=") {
			c.Visit(a.SourceURL)
			visited++
		}
	}
	c.Wait()

	fmt.Printf("Visited %d asatidz pages.\n", visited)

	file, _ := json.MarshalIndent(list, "", "  ")
	_ = os.WriteFile("asatidz.json", file, 0644)
	fmt.Println("Done. Updated data saved to asatidz.json")

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

	if zeroCount > 0 {
		fmt.Println("\nAsatidz with count=0:")
		for _, a := range list {
			if a.Count == 0 {
				fmt.Printf("  - %s: %s\n", a.Name, a.SourceURL)
			}
		}
	}
}
