# profilasatidz

Direktori Asatidz Sunnah — profil, jumlah kajian, dan rujukan langsung ke kajian.net.

## Stack

- **Backend:** Go (standard library `net/http`)
- **Frontend:** HTMX + Tailwind CSS (CDN)
- **Data:** JSON file (with updater script)
- **Deploy:** Docker

## Struktur

```
profilasatidz/
├── main.go          # Backend + HTMX frontend
├── updater.go       # Scraper untuk update count kajian
├── index.html       # Template HTML
├── asatidz.json     # Data asatidz (~278 entries)
├── Dockerfile
├── docker-compose.yml
└── go.mod / go.sum
```

## API Endpoints

| Endpoint | Method | Response | Deskripsi |
|---|---|---|---|
| `/` | GET | HTML | Halaman utama daftar asatidz |
| `/api/search?q=nama` | GET | HTML fragment | Live search via HTMX |
| `/api/reload` | GET | OK | Reload data dari JSON |

## Data Source

- **kajian.net** — Data diambil secara otomatis menggunakan web scraper
- Update record count: `go run updater.go`
- Setiap entri mencakup: nama, URL profil kajian.net, jumlah kajian

## Development

```bash
# Run locally
go run main.go

# Update counts
go run updater.go

# Build Docker
docker build -t profilasatidz .
docker run -p 8080:8080 profilasatidz
```

## Docker Compose

```bash
docker compose up -d
```

## Roadmap

- [x] Data scraping dari kajian.net
- [x] Count kajian per asatidz
- [x] Live search (HTMX)
- [x] Docker setup
- [ ] Field OSINT (bio, pendidikan)
- [ ] SQLite migration
- [ ] Admin panel

## License

Data dari kajian.net. Proyek ini untuk keperluan dakwah dan edukasi.
