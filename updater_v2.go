package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"math/rand"
	"net/http"
	"net/url"
	"os"
	"regexp"
	"strings"
	"time"
)

type Asatidz struct {
	Name      string `json:"name"`
	SourceURL string `json:"source_url"`
	Count     int    `json:"count"`
}

func fetchHTML(rawURL string) string {
	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Get(rawURL)
	if err != nil {
		return ""
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	return string(body)
}

func main() {
	data, err := os.ReadFile("asatidz.json")
	if err != nil {
		log.Fatal(err)
	}
	var list []Asatidz
	json.Unmarshal(data, &list)

	// Don't reset — only update those with wrong counts
	// Reset all to 0
	for i := range list {
		list[i].Count = 0
	}

	albumPattern := regexp.MustCompile(`/kajian-audio/Ceramah/([^/]+)/([^"]+)`)

	fmt.Println("Re-counting all asatiedz...")
	processed := 0

	for i := range list {
		if list[i].SourceURL == "" {
			continue
		}

		html := fetchHTML(list[i].SourceURL)
		if html == "" {
			log.Printf("  [SKIP] %s", list[i].Name)
			continue
		}

		seen := map[string]bool{}
		matches := albumPattern.FindAllStringSubmatch(html, -1)
		for _, m := range matches {
			matchAsatidz, _ := url.QueryUnescape(m[1])
			albumName, _ := url.QueryUnescape(m[2])
			// Strip query parameters
			if qIdx := strings.Index(albumName, "?"); qIdx >= 0 {
				albumName = albumName[:qIdx]
			}
			albumName = strings.TrimRight(albumName, "')]")
			albumName = strings.TrimSpace(albumName)
			// Skip if album name matches asatidz name, or album is empty
			if strings.EqualFold(albumName, list[i].Name) || albumName == "" {
				continue
			}
			// Skip HTML fragments (from malformed regex matches)
			if strings.ContainsAny(albumName, "<>{}") {
				continue
			}
			// CRITICAL: Only count if this album actually belongs to THIS asatidz
			// (regex matches other asatidz' albums from sidebar widgets)
			if !strings.EqualFold(matchAsatidz, list[i].Name) {
				continue
			}
			if !seen[albumName] {
				seen[albumName] = true
				list[i].Count++
			}
		}

		if len(seen) == 0 {
			mp3Pattern := regexp.MustCompile(`\.mp3`)
			mp3Count := len(mp3Pattern.FindAllString(html, -1))
			if mp3Count > 0 {
				list[i].Count = mp3Count / 2
			}
		}

		processed++

		// Save checkpoint every 50
		if processed%50 == 0 {
			file, _ := json.MarshalIndent(list, "", "  ")
			_ = os.WriteFile("asatidz.json", file, 0644)
			fmt.Printf("  [CHECKPOINT] %d processed. Saved.\n", processed)
		}

		// Random delay 100-300ms
		delay := time.Duration(100+rand.Intn(200)) * time.Millisecond
		time.Sleep(delay)
	}

	// Final save
	file, _ := json.MarshalIndent(list, "", "  ")
	_ = os.WriteFile("asatidz.json", file, 0644)
	fmt.Printf("Done. Processed %d/%d\n", processed, len(list))

	zero := 0
	for _, a := range list {
		if a.Count == 0 {
			zero++
		}
	}
	fmt.Printf("Zero: %d\n", zero)
}
