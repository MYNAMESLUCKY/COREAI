package auth

import (
	"net/http"
	"strings"

	"yogz/go_agent/internal/config"
)

func Middleware(cfg config.Config, next http.Handler) http.Handler {
	// If no API keys configured, allow all.
	if len(cfg.APIKeys) == 0 {
		return next
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		tok := extractBearer(r.Header.Get("Authorization"))
		if tok == "" {
			w.WriteHeader(http.StatusUnauthorized)
			_, _ = w.Write([]byte("missing api key"))
			return
		}
		for _, k := range cfg.APIKeys {
			if tok == k {
				next.ServeHTTP(w, r)
				return
			}
		}
		w.WriteHeader(http.StatusUnauthorized)
		_, _ = w.Write([]byte("invalid api key"))
	})
}

func extractBearer(v string) string {
	v = strings.TrimSpace(v)
	if v == "" {
		return ""
	}
	if strings.HasPrefix(strings.ToLower(v), "bearer ") {
		return strings.TrimSpace(v[7:])
	}
	return ""
}

func UserIDFromRequest(r *http.Request) string {
	// Minimal: treat api key as identity.
	return extractBearer(r.Header.Get("Authorization"))
}
