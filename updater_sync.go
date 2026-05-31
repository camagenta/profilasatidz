package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
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
	client := &http.Client{Timeout: 15 * time.Second}
	resp, err := client.Get(rawURL)
	if err != nil {
		return ""
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	return string(body)
}

func main() {
	if len(os.Args) < 2 {
		fmt.Println("Usage: go run updater_sync.go <batch_file>")
		fmt.Println("Batch file: one asatidz name per line")
		os.Exit(1)
	}

	batchFile := os.Args[1]

	// Read batch names
	batchBytes, err := os.ReadFile(batchFile)
	if err != nil {
		log.Fatal(err)
	}
	names := strings.Split(string(batchBytes), "\n")
	
	// Read existing data
	data, err := os.ReadFile("asatidz.json")
	if err != nil {
		log.Fatal(err)
	}
	var list []Asatidz
	json.Unmarshal(data, &list)

	albumPattern := regexp.MustCompile(`/kajian-audio/Ceramah/([^/]+)/(.+)`)

	processed := 0
	for _, name := range names {
		name = strings.TrimSpace(name)
		if name == "" {
			continue
		}

		// Find asatidz index
		idx := -1
		for i, a := range list {
			if strings.EqualFold(a.Name, name) {
				idx = i
				break
			}
		}
		if idx == -1 {
			log.Printf("  [WARN] Not found: %s", name)
			continue
		}

		html := fetchHTML(list[idx].SourceURL)
		if html == "" {
			log.Printf("  [ERROR] Failed: %s", name)
			continue
		}

		// Count album links
		seen := map[string]bool{}
		matches := albumPattern.FindAllStringSubmatch(html, -1)
		for _, m := range matches {
			albumName, _ := url.QueryUnescape(m[2])
			if strings.EqualFold(albumName, list[idx].Name) {
				continue
			}
			if !seen[albumName] {
				seen[albumName] = true
				list[idx].Count++
			}
		}

		// If no album links, count direct MP3
		if len(seen) == 0 {
			mp3Pattern := regexp.MustCompile(`\.mp3`)
			mp3Count := len(mp3Pattern.FindAllString(html, -1))
			if mp3Count > 0 {
				list[idx].Count = mp3Count / 2 // each file appears ~2 times
			}
		}

		processed++
		fmt.Printf("  [%d] %s: %d\n", processed, name, list[idx].Count)
		time.Sleep(300 * time.Millisecond)
	}

	// Save
	file, _ := json.MarshalIndent(list, "", "  ")
	_ = os.WriteFile("asatidz.json", file, 0644)
	fmt.Printf("\nDone. Processed %d asatidz. Saved to asatidz.json\n", processed)

	// Stats
	withCount := 0
	for _, a := range list {
		if a.Count > 0 {
			withCount++
		}
	}
	fmt.Printf("Stats: %d with count, %d zero\n", withCount, len(list)-withCount)
}
