package robots

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestParseCrawlDelay(t *testing.T) {
	tests := []struct {
		name     string
		content  string
		expected int64
	}{
		{"present", "User-agent: *\nCrawl-delay: 2\n", 2000},
		{"fractional", "User-agent: *\nCrawl-delay: 0.5\n", 500},
		{"absent", "User-agent: *\nDisallow: /\n", 0},
		{"case insensitive", "user-AGENT: *\nCRAWL-DELAY: 3\n", 3000},
		{"first wins", "User-agent: *\nCrawl-delay: 1\nCrawl-delay: 5\n", 1000},
		{"outside any group", "Crawl-delay: 4\n", 0},
		{"named bot only", "User-agent: GPTBot\nCrawl-delay: 60\n", 0},
		{"named bot before wildcard", "User-agent: CCBot\nCrawl-delay: 60\n\nUser-agent: *\nCrawl-delay: 2\n", 2000},
		{"wildcard in multi-agent group", "User-agent: GPTBot\nUser-agent: *\nCrawl-delay: 7\n", 7000},
		{"wildcard group ends at next agent", "User-agent: *\nDisallow: /x\nUser-agent: GPTBot\nCrawl-delay: 60\n", 0},
		{"trailing comment", "User-agent: * # everyone\nCrawl-delay: 2 # seconds\n", 2000},
		{"CRLF", "User-agent: *\r\nCrawl-delay: 2\r\n", 2000},
		{"midwayupull 2026-10-23", "User-agent: *\nAllow: /\nDisallow: /wp-admin/\n\n# Meta AI\nUser-agent: meta-externalagent\nCrawl-delay: 60\n\nUser-agent: ClaudeBot\nCrawl-delay: 60\nDisallow: /\n", 0},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			assert.Equal(t, tt.expected, parseCrawlDelay(tt.content))
		})
	}
}

func TestFetch_Success(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.HasSuffix(r.URL.Path, "robots.txt") {
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte("User-agent: *\nCrawl-delay: 3\n"))
		}
	}))
	defer srv.Close()

	// Override fetch URL to use test server (scheme+host only)
	result, err := fetchFromURL(srv.URL + "/robots.txt")
	require.NoError(t, err)
	assert.True(t, result.Found)
	assert.Equal(t, int64(3000), result.CrawlDelayMs)
}

func TestFetch_NotFound(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer srv.Close()

	result, err := fetchFromURL(srv.URL + "/robots.txt")
	require.NoError(t, err)
	assert.False(t, result.Found)
}
