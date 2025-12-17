package audit

import (
	"encoding/json"
	"os"
	"sync"
	"time"
)

type Logger struct {
	mu   sync.Mutex
	path string
}

type Event struct {
	TS     string `json:"ts"`
	Kind   string `json:"kind"`
	UserID string `json:"user_id,omitempty"`
	IP     string `json:"ip,omitempty"`
	Method string `json:"method,omitempty"`
	Path   string `json:"path,omitempty"`
	Status int    `json:"status,omitempty"`
	Note   string `json:"note,omitempty"`
}

func New(path string) *Logger {
	return &Logger{path: path}
}

func (l *Logger) Write(e Event) {
	l.mu.Lock()
	defer l.mu.Unlock()

	e.TS = time.Now().UTC().Format(time.RFC3339)
	b, err := json.Marshal(e)
	if err != nil {
		return
	}

	f, err := os.OpenFile(l.path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0600)
	if err != nil {
		return
	}
	defer f.Close()
	_, _ = f.Write(append(b, '\n'))
}
