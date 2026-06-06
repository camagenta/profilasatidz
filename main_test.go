package main

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// sampleData returns a fixed dataset for testing
func sampleData() []Asatidz {
	return []Asatidz{
		{Name: "Abdullah Taslim", SourceURL: "https://kajian.net/a/abdullah-taslim", Count: 382, Categories: []string{"aqidah", "fiqh"}},
		{Name: "Abdullah Zaen", SourceURL: "https://kajian.net/a/abdullah-zaen", Count: 484, Categories: []string{"tafsir", "hadits"}},
		{Name: "Abdul Hakim Amir Abdat", SourceURL: "https://kajian.net/a/abdul-hakim", Count: 133, Categories: []string{"fiqh", "usul"}},
		{Name: "Abdurrahman Thayyib", SourceURL: "https://kajian.net/a/abdurrahman-thayyib", Count: 113, Categories: []string{"tasawuf"}},
		{Name: "Abdul Barr", SourceURL: "https://kajian.net/a/abdul-barr", Count: 18, Categories: []string{"aqidah"}},
		{Name: "Abdul Haq", SourceURL: "https://kajian.net/a/abdul-haq", Count: 13, Categories: []string{}},
		{Name: "Abdullah Al Bughury", SourceURL: "https://kajian.net/a/abdullah-bughury", Count: 11, Categories: []string{"fiqh"}},
		{Name: "Abdullah Amin", SourceURL: "https://kajian.net/a/abdullah-amin", Count: 12, Categories: []string{"tafsir"}},
		{Name: "Abdullah Roy", SourceURL: "https://kajian.net/a/abdullah-roy", Count: 25, Categories: []string{"hadits", "fiqh"}},
		{Name: "Abdul Mu'thi Al Maidani", SourceURL: "https://kajian.net/a/abdul-muthi", Count: 19, Categories: []string{"aqidah"}},
		{Name: "Abdurrahim", SourceURL: "https://kajian.net/a/abdurrahim", Count: 11, Categories: []string{}},
		{Name: "Abdurrahman Attamimi", SourceURL: "https://kajian.net/a/abdurrahman-attamimi", Count: 20, Categories: []string{"usul"}},
		{Name: "Abdurrahman Ayyub", SourceURL: "https://kajian.net/a/abdurrahman-ayyub", Count: 16, Categories: []string{"tasawuf"}},
		{Name: "Abdurrahman bin Muhammad Musa Alu Nashr", SourceURL: "https://kajian.net/a/abdurrahman-nashr", Count: 27, Categories: []string{"hadits"}},
		{Name: "Abdurrauf", SourceURL: "https://kajian.net/a/abdurrauf", Count: 11, Categories: []string{"fiqh"}},
		{Name: "Ahmad Zainuddin", SourceURL: "https://kajian.net/a/ahmad-zainuddin", Count: 0, Categories: []string{}},
		{Name: "Bilal Philips", SourceURL: "https://kajian.net/a/bilal-philips", Count: 55, Categories: []string{"aqidah", "dakwah"}},
		{Name: "Yasir Qadhi", SourceURL: "https://kajian.net/a/yasir-qadhi", Count: 42, Categories: []string{"dakwah"}},
		{Name: "Nouman Ali Khan", SourceURL: "https://kajian.net/a/nouman-ali-khan", Count: 88, Categories: []string{"tafsir", "dakwah"}},
		{Name: "Omar Suleiman", SourceURL: "https://kajian.net/a/omar-suleiman", Count: 65, Categories: []string{"dakwah"}},
	}
}

// ============================================================
// Unit Tests: filter
// ============================================================

func TestFilter_ByName(t *testing.T) {
	data := sampleData()
	result := filter(data, "abdullah", "", 0)
	if len(result) != 5 {
		t.Errorf("expected 5 results for 'abdullah', got %d", len(result))
	}
}

func TestFilter_ByNameCaseInsensitive(t *testing.T) {
	data := sampleData()
	result := filter(data, "ABDULLAH", "", 0)
	if len(result) != 5 {
		t.Errorf("expected 5 results for 'ABDULLAH', got %d", len(result))
	}
}

func TestFilter_ByCategory(t *testing.T) {
	data := sampleData()
	result := filter(data, "", "fiqh", 0)
	if len(result) != 5 {
		t.Errorf("expected 5 results for category 'fiqh', got %d", len(result))
	}
}

func TestFilter_ByMinCount(t *testing.T) {
	data := sampleData()
	result := filter(data, "", "", 50)
	if len(result) != 7 {
		t.Errorf("expected 7 results for min_count=50, got %d", len(result))
	}
}

func TestFilter_Combined(t *testing.T) {
	data := sampleData()
	result := filter(data, "abdurrahman", "", 15)
	// abdurrahman thayyib(113), attamimi(20), ayyub(16), nashr(27) — all >= 15
	if len(result) != 4 {
		t.Errorf("expected 4 results for 'abdurrahman' + min_count=15, got %d", len(result))
	}
}

func TestFilter_NoMatch(t *testing.T) {
	data := sampleData()
	result := filter(data, "zzzznonexistent", "", 0)
	if len(result) != 0 {
		t.Errorf("expected 0 results, got %d", len(result))
	}
}

func TestFilter_EmptyQuery(t *testing.T) {
	data := sampleData()
	result := filter(data, "", "", 0)
	if len(result) != len(data) {
		t.Errorf("expected all %d results, got %d", len(data), len(result))
	}
}

// ============================================================
// Unit Tests: sortData
// ============================================================

func TestSort_AlphaAsc(t *testing.T) {
	data := sampleData()
	sortData(data, "alpha_asc")
	if data[0].Name != "Abdul Barr" {
		t.Errorf("expected first to be 'Abdul Barr', got '%s'", data[0].Name)
	}
}

func TestSort_AlphaDesc(t *testing.T) {
	data := sampleData()
	sortData(data, "alpha_desc")
	if data[0].Name != "Yasir Qadhi" {
		t.Errorf("expected first to be 'Yasir Qadhi', got '%s'", data[0].Name)
	}
}

func TestSort_CountDesc(t *testing.T) {
	data := sampleData()
	sortData(data, "count_desc")
	if data[0].Count != 484 {
		t.Errorf("expected first count 484, got %d", data[0].Count)
	}
}

func TestSort_CountAsc(t *testing.T) {
	data := sampleData()
	sortData(data, "count_asc")
	if data[0].Count != 0 {
		t.Errorf("expected first count 0, got %d", data[0].Count)
	}
}

func TestSort_DefaultIsAlphaAsc(t *testing.T) {
	data := sampleData()
	sortData(data, "")
	if data[0].Name != "Abdul Barr" {
		t.Errorf("expected default sort first='Abdul Barr', got '%s'", data[0].Name)
	}
}

// ============================================================
// Unit Tests: generatePageRange
// ============================================================

func TestPageRange_FirstPage(t *testing.T) {
	pages := generatePageRange(1, 19)
	// Near beginning: 1, 2, 3, ..., 19
	if pages[0].Number != 1 {
		t.Errorf("expected first page=1, got %d", pages[0].Number)
	}
	if pages[len(pages)-1].Number != 19 {
		t.Errorf("expected last page=19, got %d", pages[len(pages)-1].Number)
	}
	// Should have ellipsis
	hasEllipsis := false
	for _, p := range pages {
		if p.IsEllipsis {
			hasEllipsis = true
		}
	}
	if !hasEllipsis {
		t.Error("expected ellipsis in first page range")
	}
}

func TestPageRange_MiddlePage(t *testing.T) {
	pages := generatePageRange(10, 19)
	// Middle: 1, ..., 9, 10, 11, ..., 19
	if pages[0].Number != 1 {
		t.Errorf("expected first=1, got %d", pages[0].Number)
	}
	// Should have 10 in the middle
	found := false
	for _, p := range pages {
		if p.Number == 10 {
			found = true
		}
	}
	if !found {
		t.Error("expected page 10 in middle range")
	}
	// Should have 2 ellipses
	ellipsisCount := 0
	for _, p := range pages {
		if p.IsEllipsis {
			ellipsisCount++
		}
	}
	if ellipsisCount != 2 {
		t.Errorf("expected 2 ellipsis, got %d", ellipsisCount)
	}
}

func TestPageRange_LastPage(t *testing.T) {
	pages := generatePageRange(19, 19)
	// Near end: 1, ..., 17, 18, 19
	if pages[len(pages)-1].Number != 19 {
		t.Errorf("expected last=19, got %d", pages[len(pages)-1].Number)
	}
}

func TestPageRange_SmallTotal(t *testing.T) {
	pages := generatePageRange(1, 3)
	// Total=3: 1, 2, 3 — no ellipsis needed
	for _, p := range pages {
		if p.IsEllipsis {
			t.Error("no ellipsis should appear for total <= 3")
		}
	}
	if len(pages) != 3 {
		t.Errorf("expected 3 pages, got %d", len(pages))
	}
}

func TestPageRange_TotalOne(t *testing.T) {
	pages := generatePageRange(1, 1)
	if len(pages) != 1 {
		t.Errorf("expected 1 page, got %d", len(pages))
	}
	if pages[0].Number != 1 {
		t.Errorf("expected page 1, got %d", pages[0].Number)
	}
}

func TestPageRange_Max4Numbers(t *testing.T) {
	// For total=19, max visible page numbers (non-ellipsis) should be 4
	// Pattern: 1, (ellipsis), 2 middle pages, (ellipsis), 19 = 4 numbers
	for i := 1; i <= 19; i++ {
		pages := generatePageRange(i, 19)
		numCount := 0
		for _, p := range pages {
			if !p.IsEllipsis {
				numCount++
			}
		}
		if numCount > 4 {
			t.Errorf("page %d: expected max 4 numbers, got %d — %v", i, numCount, pages)
		}
	}
}

// ============================================================
// Unit Tests: paginate
// ============================================================

func TestPaginate_FirstPage(t *testing.T) {
	data := sampleData()
	pd := paginate(data, 1, 5)
	if len(pd.Asatidz) != 5 {
		t.Errorf("expected 5 items, got %d", len(pd.Asatidz))
	}
	if pd.Total != 20 {
		t.Errorf("expected total=20, got %d", pd.Total)
	}
	if pd.TotalPages != 4 {
		t.Errorf("expected 4 total pages, got %d", pd.TotalPages)
	}
	if pd.Page != 1 {
		t.Errorf("expected page=1, got %d", pd.Page)
	}
	if pd.HasPrev {
		t.Error("expected HasPrev=false on first page")
	}
	if !pd.HasNext {
		t.Error("expected HasNext=true on first page")
	}
}

func TestPaginate_LastPage(t *testing.T) {
	data := sampleData()
	pd := paginate(data, 4, 5)
	if len(pd.Asatidz) != 5 {
		t.Errorf("expected 5 items on last page, got %d", len(pd.Asatidz))
	}
	if !pd.HasPrev {
		t.Error("expected HasPrev=true on last page")
	}
	if pd.HasNext {
		t.Error("expected HasNext=false on last page")
	}
}

func TestPaginate_PageBeyondRange(t *testing.T) {
	data := sampleData()
	pd := paginate(data, 100, 5)
	if pd.Page != 4 {
		t.Errorf("expected page clamped to 4, got %d", pd.Page)
	}
}

func TestPaginate_PageZero(t *testing.T) {
	data := sampleData()
	pd := paginate(data, 0, 5)
	if pd.Page != 1 {
		t.Errorf("expected page clamped to 1, got %d", pd.Page)
	}
}

func TestPaginate_EmptyList(t *testing.T) {
	pd := paginate([]Asatidz{}, 1, 15)
	if pd.Total != 0 {
		t.Errorf("expected total=0, got %d", pd.Total)
	}
	if pd.TotalPages != 1 {
		t.Errorf("expected totalPages=1 for empty list, got %d", pd.TotalPages)
	}
	if len(pd.Asatidz) != 0 {
		t.Errorf("expected 0 items, got %d", len(pd.Asatidz))
	}
}

func TestPaginate_SinglePage(t *testing.T) {
	data := sampleData()[:3]
	pd := paginate(data, 1, 15)
	if pd.TotalPages != 1 {
		t.Errorf("expected 1 total page, got %d", pd.TotalPages)
	}
	if pd.HasPrev || pd.HasNext {
		t.Error("expected no prev/next for single page")
	}
}

// ============================================================
// Unit Tests: extractCategories
// ============================================================

func TestExtractCategories(t *testing.T) {
	data := sampleData()
	cats := extractCategories(data)
	expected := []string{"aqidah", "dakwah", "fiqh", "hadits", "tafsir", "tasawuf", "usul"}
	if len(cats) != len(expected) {
		t.Errorf("expected %d categories, got %d: %v", len(expected), len(cats), cats)
	}
	for i, c := range cats {
		if i < len(expected) && c != expected[i] {
			t.Errorf("expected category[%d]=%s, got %s", i, expected[i], c)
		}
	}
}

func TestExtractCategories_Empty(t *testing.T) {
	cats := extractCategories([]Asatidz{})
	if len(cats) != 0 {
		t.Errorf("expected 0 categories, got %d", len(cats))
	}
}

func TestExtractCategories_NoDuplicates(t *testing.T) {
	data := []Asatidz{
		{Name: "A", Categories: []string{"fiqh", "aqidah"}},
		{Name: "B", Categories: []string{"fiqh", "aqidah"}},
	}
	cats := extractCategories(data)
	if len(cats) != 2 {
		t.Errorf("expected 2 unique categories, got %d: %v", len(cats), cats)
	}
}

// ============================================================
// Unit Tests: parseParams
// ============================================================

func TestParseParams_AllParams(t *testing.T) {
	r := httptest.NewRequest("GET", "/api/search?q=abdullah&sort=count_desc&cat=fiqh&min_count=10&page=2&size=10", nil)
	query, sort, cat, minCount, page, size := parseParams(r)
	if query != "abdullah" {
		t.Errorf("expected query='abdullah', got '%s'", query)
	}
	if sort != "count_desc" {
		t.Errorf("expected sort='count_desc', got '%s'", sort)
	}
	if cat != "fiqh" {
		t.Errorf("expected cat='fiqh', got '%s'", cat)
	}
	if minCount != 10 {
		t.Errorf("expected minCount=10, got %d", minCount)
	}
	if page != 2 {
		t.Errorf("expected page=2, got %d", page)
	}
	if size != 10 {
		t.Errorf("expected size=10, got %d", size)
	}
}

func TestParseParams_Defaults(t *testing.T) {
	r := httptest.NewRequest("GET", "/api/search", nil)
	_, sort, _, _, page, size := parseParams(r)
	if sort != "alpha_asc" {
		t.Errorf("expected default sort='alpha_asc', got '%s'", sort)
	}
	if page != 1 {
		t.Errorf("expected default page=1, got %d", page)
	}
	if size != 15 {
		t.Errorf("expected default size=15, got %d", size)
	}
}

func TestParseParams_InvalidNumbers(t *testing.T) {
	r := httptest.NewRequest("GET", "/api/search?page=abc&size=xyz", nil)
	_, _, _, _, page, size := parseParams(r)
	if page != 1 {
		t.Errorf("expected page=1 for invalid input, got %d", page)
	}
	if size != 15 {
		t.Errorf("expected size=15 for invalid input, got %d", size)
	}
}

// ============================================================
// Integration Tests: HTTP endpoints
// ============================================================

func setupTestServer() *httptest.Server {
	loadDataFromSlice(sampleData())
	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		dataMutex.RLock()
		pd := paginate(asatidzData, 1, 15)
		dataMutex.RUnlock()
		renderResults(w, pd)
	})
	mux.HandleFunc("/api/search", func(w http.ResponseWriter, r *http.Request) {
		query, sort, category, minCount, page, pageSize := parseParams(r)
		dataMutex.RLock()
		filtered := filter(asatidzData, query, category, minCount)
		dataMutex.RUnlock()
		sortData(filtered, sort)
		pd := paginate(filtered, page, pageSize)
		pd.Query = query
		pd.Sort = sort
		pd.Category = category
		pd.MinCount = minCount
		renderResults(w, pd)
	})
	mux.HandleFunc("/api/contribute", handleContribute)
	return httptest.NewServer(mux)
}

func TestIntegration_Index(t *testing.T) {
	ts := setupTestServer()
	defer ts.Close()

	resp, err := http.Get(ts.URL + "/")
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		t.Errorf("expected status 200, got %d", resp.StatusCode)
	}
	if ct := resp.Header.Get("Content-Type"); !strings.Contains(ct, "text/html") {
		t.Errorf("expected text/html, got %s", ct)
	}

	buf := make([]byte, 4096)
	n, _ := resp.Body.Read(buf)
	body := string(buf[:n])
	if !strings.Contains(body, "Abdullah Taslim") {
		t.Error("expected 'Abdullah Taslim' in response body")
	}
	if !strings.Contains(body, "Menampilkan") {
		t.Error("expected 'Menampilkan' text in response body")
	}
}

func TestIntegration_Search(t *testing.T) {
	ts := setupTestServer()
	defer ts.Close()

	resp, err := http.Get(ts.URL + "/api/search?q=abdullah")
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		t.Errorf("expected status 200, got %d", resp.StatusCode)
	}

	buf := make([]byte, 4096)
	n, _ := resp.Body.Read(buf)
	body := string(buf[:n])
	if !strings.Contains(body, "Abdullah Taslim") {
		t.Error("expected 'Abdullah Taslim' in search results")
	}
}

func TestIntegration_SearchNoMatch(t *testing.T) {
	ts := setupTestServer()
	defer ts.Close()

	resp, err := http.Get(ts.URL + "/api/search?q=zzzznonexistent")
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()

	buf := make([]byte, 4096)
	n, _ := resp.Body.Read(buf)
	body := string(buf[:n])
	if !strings.Contains(body, "Menampilkan 0 dari 0") {
		t.Errorf("expected 'Menampilkan 0 dari 0', got: %s", body)
	}
}

func TestIntegration_SearchWithFilter(t *testing.T) {
	ts := setupTestServer()
	defer ts.Close()

	resp, err := http.Get(ts.URL + "/api/search?sort=count_desc&size=5")
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()

	buf := make([]byte, 4096)
	n, _ := resp.Body.Read(buf)
	body := string(buf[:n])
	// Abdullah Zaen has highest count (484), should appear first
	if !strings.Contains(body, "Abdullah Zaen") {
		t.Error("expected 'Abdullah Zaen' (highest count) in results")
	}
}

func TestIntegration_Pagination(t *testing.T) {
	ts := setupTestServer()
	defer ts.Close()

	resp, err := http.Get(ts.URL + "/api/search?page=2&size=5")
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()

	buf := make([]byte, 4096)
	n, _ := resp.Body.Read(buf)
	body := string(buf[:n])
	if !strings.Contains(body, "Halaman 2 dari 4") {
		t.Errorf("expected 'Halaman 2 dari 4', got: %s", body)
	}
}

func TestIntegration_MinCountFilter(t *testing.T) {
	ts := setupTestServer()
	defer ts.Close()

	resp, err := http.Get(ts.URL + "/api/search?min_count=100")
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()

	buf := make([]byte, 4096)
	n, _ := resp.Body.Read(buf)
	body := string(buf[:n])
	// Should show count >= 100: abdullah taslim(382), abdullah zaen(484), abdul hakim(133), abdurrahman thayyib(113), nouman(88) — wait, 88 < 100
	// So: 382, 484, 133, 113 = 4
	if !strings.Contains(body, "Menampilkan 4 dari 4") {
		t.Errorf("expected 'Menampilkan 4 dari 4' for min_count=100, got: %s", body)
	}
}

func TestIntegration_ContributeValidation(t *testing.T) {
	ts := setupTestServer()
	defer ts.Close()

	// 1. Test GET (Method not allowed)
	resp, err := http.Get(ts.URL + "/api/contribute")
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != 405 {
		t.Errorf("expected status 405 for GET, got: %d", resp.StatusCode)
	}

	// 2. Test POST empty body
	respPost, err := http.Post(ts.URL + "/api/contribute", "application/json", strings.NewReader(`{}`))
	if err != nil {
		t.Fatal(err)
	}
	defer respPost.Body.Close()
	// Since GITHUB_TOKEN is either empty (fitur belum dikonfigurasi -> 500) or presents (validation error -> 400)
	if respPost.StatusCode != 400 && respPost.StatusCode != 500 {
		t.Errorf("expected status 400 or 500, got: %d", respPost.StatusCode)
	}
}
