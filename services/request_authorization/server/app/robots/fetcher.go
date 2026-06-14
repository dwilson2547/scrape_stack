package robots

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"
)

const fetchTimeout = 10 * time.Second

// Result holds the outcome of a robots.txt fetch.
type Result struct {
	Found        bool
	CrawlDelayMs int64
	RawContent   string
}

// Fetch retrieves robots.txt for domain and parses Crawl-delay.
// Returns Result{Found: false} when the file is absent (404) or has no Crawl-delay.
// The scheme defaults to "https" but can be overridden via ROBOTS_TXT_SCHEME env var.
func Fetch(domain string) (Result, error) {
	scheme := os.Getenv("ROBOTS_TXT_SCHEME")
	if scheme == "" {
		scheme = "https"
	}
	return fetchFromURL(fmt.Sprintf("%s://%s/robots.txt", scheme, domain))
}

func fetchFromURL(url string) (Result, error) {
	client := &http.Client{Timeout: fetchTimeout}
	resp, err := client.Get(url)
	if err != nil {
		return Result{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return Result{Found: false}, nil
	}
	if resp.StatusCode != http.StatusOK {
		return Result{}, fmt.Errorf("robots.txt fetch: HTTP %d for %s", resp.StatusCode, url)
	}

	body, err := io.ReadAll(io.LimitReader(resp.Body, 1<<16))
	if err != nil {
		return Result{}, err
	}
	raw := string(body)
	return Result{Found: true, CrawlDelayMs: parseCrawlDelay(raw), RawContent: raw}, nil
}

// parseCrawlDelay extracts the first Crawl-delay value in seconds and converts to ms.
// Returns 0 if no directive is found.
func parseCrawlDelay(content string) int64 {
	for _, line := range strings.Split(content, "\n") {
		line = strings.TrimSpace(line)
		if !strings.HasPrefix(strings.ToLower(line), "crawl-delay:") {
			continue
		}
		parts := strings.SplitN(line, ":", 2)
		if len(parts) != 2 {
			continue
		}
		val := strings.TrimSpace(parts[1])
		if f, err := strconv.ParseFloat(val, 64); err == nil && f > 0 {
			return int64(f * 1000)
		}
	}
	return 0
}
