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
		{"fractional", "Crawl-delay: 0.5\n", 500},
		{"absent", "User-agent: *\nDisallow: /\n", 0},
		{"case insensitive", "CRAWL-DELAY: 3\n", 3000},
		{"first wins", "Crawl-delay: 1\nCrawl-delay: 5\n", 1000},
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
