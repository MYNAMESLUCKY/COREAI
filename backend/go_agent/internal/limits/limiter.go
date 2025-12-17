package limits

import (
	"net"
	"net/http"
	"strings"
	"sync"
	"time"

	"golang.org/x/time/rate"
)

type KeyedLimiter struct {
	mu       sync.Mutex
	limiters map[string]*rate.Limiter
	rate     rate.Limit
	burst    int
	window   time.Duration
}

func NewKeyedLimiter(perMin int) *KeyedLimiter {
	if perMin <= 0 {
		perMin = 60
	}
	lim := rate.Limit(float64(perMin) / 60.0)
	return &KeyedLimiter{
		limiters: map[string]*rate.Limiter{},
		rate:     lim,
		burst:    perMin,
		window:   time.Minute,
	}
}

func (k *KeyedLimiter) get(key string) *rate.Limiter {
	k.mu.Lock()
	defer k.mu.Unlock()
	l, ok := k.limiters[key]
	if !ok {
		l = rate.NewLimiter(k.rate, k.burst)
		k.limiters[key] = l
	}
	return l
}

func ClientKey(r *http.Request) string {
	if auth := r.Header.Get("Authorization"); auth != "" {
		return auth
	}
	ip := r.Header.Get("X-Forwarded-For")
	if ip == "" {
		host, _, err := net.SplitHostPort(r.RemoteAddr)
		if err == nil {
			ip = host
		} else {
			ip = r.RemoteAddr
		}
	}
	ip = strings.TrimSpace(strings.Split(ip, ",")[0])
	if ip == "" {
		ip = "unknown"
	}
	return ip
}

func (k *KeyedLimiter) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		key := ClientKey(r)
		lim := k.get(key)
		if !lim.Allow() {
			w.WriteHeader(http.StatusTooManyRequests)
			_, _ = w.Write([]byte("rate limit exceeded"))
			return
		}
		next.ServeHTTP(w, r)
	})
}
