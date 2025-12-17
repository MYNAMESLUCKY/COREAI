package security

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
)

func IsPathAllowed(path string, allowDirs []string) (string, bool) {
	if path == "" {
		return "", false
	}
	abs, err := filepath.Abs(path)
	if err != nil {
		return "", false
	}
	abs = filepath.Clean(abs)

	for _, d := range allowDirs {
		d = strings.TrimSpace(d)
		if d == "" {
			continue
		}
		base, err := filepath.Abs(d)
		if err != nil {
			continue
		}
		base = filepath.Clean(base)
		if hasPathPrefix(abs, base) {
			return abs, true
		}
	}
	return abs, false
}

func hasPathPrefix(p, base string) bool {
	p = strings.ToLower(filepath.Clean(p))
	base = strings.ToLower(filepath.Clean(base))
	if p == base {
		return true
	}
	if !strings.HasSuffix(base, string(os.PathSeparator)) {
		base = base + string(os.PathSeparator)
	}
	return strings.HasPrefix(p, base)
}

func ReadFileLimited(path string, maxBytes int64) ([]byte, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	st, err := f.Stat()
	if err != nil {
		return nil, err
	}
	if st.Size() > maxBytes {
		return nil, errors.New("file too large")
	}
	return os.ReadFile(path)
}
