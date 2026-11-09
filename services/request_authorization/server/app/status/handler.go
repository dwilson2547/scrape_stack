package status

import (
	"encoding/json"
	"net/http"

	"github.com/dwilson/request-auth/pool"
)

type response struct {
	Pools []pool.PoolStatus `json:"pools"`
}

// Handler returns a http.HandlerFunc that serves live pool state as JSON.
func Handler(manager *pool.Manager) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(response{Pools: manager.AllStatuses()})
	}
}
