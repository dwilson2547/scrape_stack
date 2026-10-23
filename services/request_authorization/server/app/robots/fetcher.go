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
// Returns Result{Found: false} when the file is absent (404); a file without a Crawl-delay is
// Found with CrawlDelayMs 0.
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

// parseCrawlDelay returns the first Crawl-delay in the group for User-agent: *, in ms, or 0.
// A delay set only for named bots (e.g. "User-agent: GPTBot / Crawl-delay: 60") does not apply
// to us. A group is a run of User-agent lines followed by its rules; the next User-agent line
// after a rule starts a new group.
func parseCrawlDelay(content string) int64 {
	inWildcard := false
	inAgents := false // still reading the User-agent lines that open a group
	for _, line := range strings.Split(content, "\n") {
		if i := strings.Index(line, "#"); i >= 0 {
			line = line[:i]
		}
		key, val, ok := strings.Cut(line, ":")
		if !ok {
			continue
		}
		key = strings.ToLower(strings.TrimSpace(key))
		val = strings.TrimSpace(val)
		if key == "user-agent" {
			if !inAgents {
				inWildcard = false
				inAgents = true
			}
			if val == "*" {
				inWildcard = true
			}
			continue
		}
		inAgents = false
		if key != "crawl-delay" || !inWildcard {
			continue
		}
		if f, err := strconv.ParseFloat(val, 64); err == nil && f > 0 {
			return int64(f * 1000)
		}
	}
	return 0
}
