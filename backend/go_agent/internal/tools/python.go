package tools

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"
)

type PythonTool struct{}

func (t *PythonTool) Name() string { return "py" }

func (t *PythonTool) Help() string { return "/py <question>" }

func (t *PythonTool) Run(ctx context.Context, rt *Runtime, args []string) (string, error) {
	if rt == nil || strings.TrimSpace(rt.PythonToolsURL) == "" {
		return "python tool server not configured (set PYTOOLS_URL)", nil
	}
	if len(args) == 0 {
		return "usage: /py <question>", nil
	}

	// Treat all args as a single natural-language query
	question := strings.Join(args, " ")
	payload := map[string]any{"question": question, "user_id": "cli", "model": rt.GetModel()}
	body, _ := json.Marshal(payload)

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(rt.PythonToolsURL, "/")+"/ask", bytes.NewReader(body))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Sprintf("python service error: %d", resp.StatusCode), nil
	}
	var out struct {
		Answer string `json:"answer"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return "", fmt.Errorf("invalid response from python service")
	}
	return out.Answer, nil
}
