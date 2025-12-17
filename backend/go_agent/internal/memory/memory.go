package memory

import (
	"context"
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"sort"
	"sync"
	"time"

	"yogz/go_agent/internal/config"
	"yogz/go_agent/internal/ollama"
)

type Entry struct {
	Text   string    `json:"text"`
	Vector []float64 `json:"vector"`
	TS     time.Time `json:"ts"`
	UserID string    `json:"user_id"`
	Kind   string    `json:"kind"`
}

type Store struct {
	cfg    config.Config
	ollama *ollama.Client
	mu     sync.Mutex
	items  []Entry
	path   string
}

func NewStore(cfg config.Config) *Store {
	path := filepath.Join(".", "agent_memory_vectors.json")
	s := &Store{cfg: cfg, ollama: ollama.New(cfg.OllamaHost), path: path}
	s.load()
	return s
}

func (s *Store) Add(ctx context.Context, e Entry) error {
	vec, err := s.ollama.Embed(ctx, s.cfg.EmbedModel, e.Text)
	if err != nil {
		return err
	}
	e.Vector = vec
	e.TS = time.Now().UTC()

	s.mu.Lock()
	s.items = append(s.items, e)
	// keep last N to limit growth
	if len(s.items) > 500 {
		s.items = s.items[len(s.items)-500:]
	}
	s.mu.Unlock()

	s.save()
	return nil
}

func (s *Store) Query(ctx context.Context, q string, k int) []string {
	if k <= 0 {
		k = 4
	}
	qv, err := s.ollama.Embed(ctx, s.cfg.EmbedModel, q)
	if err != nil {
		return nil
	}
	s.mu.Lock()
	items := append([]Entry(nil), s.items...)
	s.mu.Unlock()

	type scored struct {
		t string
		s float64
	}
	sc := make([]scored, 0, len(items))
	for _, it := range items {
		if len(it.Vector) == 0 {
			continue
		}
		cs := cosine(qv, it.Vector)
		sc = append(sc, scored{t: it.Text, s: cs})
	}
	sort.Slice(sc, func(i, j int) bool { return sc[i].s > sc[j].s })
	if len(sc) > k {
		sc = sc[:k]
	}
	out := make([]string, 0, len(sc))
	for _, x := range sc {
		out = append(out, x.t)
	}
	return out
}

func cosine(a, b []float64) float64 {
	if len(a) == 0 || len(b) == 0 {
		return 0
	}
	n := len(a)
	if len(b) < n {
		n = len(b)
	}
	var dot, na, nb float64
	for i := 0; i < n; i++ {
		dot += a[i] * b[i]
		na += a[i] * a[i]
		nb += b[i] * b[i]
	}
	den := math.Sqrt(na)*math.Sqrt(nb)
	if den == 0 {
		return 0
	}
	return dot / den
}

func (s *Store) load() {
	b, err := os.ReadFile(s.path)
	if err != nil {
		return
	}
	var items []Entry
	if err := json.Unmarshal(b, &items); err != nil {
		return
	}
	s.items = items
}

func (s *Store) save() {
	s.mu.Lock()
	items := append([]Entry(nil), s.items...)
	s.mu.Unlock()
	b, err := json.MarshalIndent(items, "", "  ")
	if err != nil {
		return
	}
	_ = os.WriteFile(s.path, b, 0600)
}
