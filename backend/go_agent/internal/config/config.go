package config

import (
	"os"
	"strconv"
	"strings"
)

type Config struct {
	Host string
	Port int

	OllamaHost string
	Model      string
	EmbedModel string
	PythonToolsURL string
	PythonAgentEntry string

	MaxInputChars  int
	MaxOutputChars int

	RateLimitPerMin int

	APIKeys []string

	EnableFS bool
	AllowDirs []string

	AuditLogPath string
}

func Load() Config {
	cfg := Config{}
	cfg.Host = getenv("AGENT_HOST", "127.0.0.1")
	cfg.Port = getenvInt("AGENT_PORT", 8080)

	cfg.OllamaHost = strings.TrimRight(getenv("OLLAMA_HOST", "http://localhost:11434"), "/")
	cfg.Model = getenv("OLLAMA_MODEL", "deepseek-v3.1:671b-cloud")
	cfg.EmbedModel = getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text:latest")
	cfg.PythonToolsURL = strings.TrimRight(getenv("PYTOOLS_URL", "http://127.0.0.1:8787"), "/")
	cfg.PythonAgentEntry = getenv("PYTHON_AGENT_ENTRY", "")

	cfg.MaxInputChars = getenvInt("AGENT_MAX_INPUT_CHARS", 12000)
	cfg.MaxOutputChars = getenvInt("AGENT_MAX_OUTPUT_CHARS", 12000)

	cfg.RateLimitPerMin = getenvInt("AGENT_RATE_LIMIT_PER_MIN", 60)

	cfg.APIKeys = splitNonEmpty(getenv("AGENT_API_KEYS", ""))

	cfg.EnableFS = getenvBool("AGENT_ENABLE_FS", false)
	cfg.AllowDirs = splitNonEmpty(getenv("AGENT_ALLOW_DIRS", ""))
	if len(cfg.AllowDirs) == 0 {
		cfg.AllowDirs = []string{"."}
	}

	cfg.AuditLogPath = getenv("AGENT_AUDIT_LOG", "agent_audit.log")
	return cfg
}

func getenv(key, def string) string {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	return v
}

func getenvInt(key string, def int) int {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return def
	}
	return n
}

func getenvBool(key string, def bool) bool {
	v := strings.ToLower(strings.TrimSpace(os.Getenv(key)))
	if v == "" {
		return def
	}
	return v == "1" || v == "true" || v == "yes" || v == "on"
}

func splitNonEmpty(s string) []string {
	parts := strings.FieldsFunc(s, func(r rune) bool { return r == ',' || r == ';' || r == ' ' || r == '\n' || r == '\t' })
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}
