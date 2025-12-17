package agent

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"sync"
	"unicode"
	"time"

	"yogz/go_agent/internal/config"
	"yogz/go_agent/internal/memory"
	"yogz/go_agent/internal/ollama"
	"yogz/go_agent/internal/tools"
	"yogz/go_agent/internal/tokens"
	"yogz/go_agent/internal/ui"
)

type Agent struct {
	mu     sync.RWMutex
	cfg    config.Config
	ollama *ollama.Client
	mem    *memory.Store
}

func New(cfg config.Config) *Agent {
	return &Agent{
		cfg:    cfg,
		ollama: ollama.New(cfg.OllamaHost),
		mem:    memory.NewStore(cfg),
	}
}

func (a *Agent) GetModel() string {
	a.mu.RLock()
	defer a.mu.RUnlock()
	return a.cfg.Model
}

func (a *Agent) SetModel(m string) {
	m = strings.TrimSpace(m)
	if m == "" {
		return
	}
	a.mu.Lock()
	a.cfg.Model = m
	a.mu.Unlock()
}

func (a *Agent) Status() map[string]any {
	a.mu.RLock()
	defer a.mu.RUnlock()
	return map[string]any{
		"model":            a.cfg.Model,
		"ollama":           a.cfg.OllamaHost,
		"max_input_chars":  a.cfg.MaxInputChars,
		"max_output_chars": a.cfg.MaxOutputChars,
		"fs_enabled":       a.cfg.EnableFS,
		"allow_dirs":       a.cfg.AllowDirs,
	}
}

func (a *Agent) FSSettings() (bool, []string) {
	a.mu.RLock()
	defer a.mu.RUnlock()
	return a.cfg.EnableFS, append([]string(nil), a.cfg.AllowDirs...)
}

func (a *Agent) Ask(ctx context.Context, userID string, question string) (string, error) {
	question = strings.TrimSpace(question)
	if question == "" {
		return "", fmt.Errorf("empty question")
	}

	a.mu.RLock()
	cfg := a.cfg
	a.mu.RUnlock()

	question = tokens.ClampChars(question, cfg.MaxInputChars)

	retrieved := a.mem.Query(ctx, question, 4)
	prompt := BuildPrompt(retrieved, question)

	start := time.Now()
	ans, err := a.ollama.Generate(ctx, cfg.Model, prompt)
	if err != nil {
		return "", err
	}
	_ = start
	ans = tokens.ClampChars(strings.TrimSpace(ans), cfg.MaxOutputChars)

	_ = a.mem.Add(ctx, memory.Entry{Text: "USER: " + question + "\nASSISTANT: " + ans, UserID: userID, Kind: "chat"})
	return ans, nil
}

func BuildPrompt(mem []string, question string) string {
	b := strings.Builder{}
	b.WriteString("You are a terminal-based coding assistant. Be concise and practical.\n")
	if len(mem) > 0 {
		b.WriteString("Relevant memory:\n")
		for _, m := range mem {
			b.WriteString("- ")
			b.WriteString(m)
			b.WriteString("\n")
		}
	}
	b.WriteString("\nUser: ")
	b.WriteString(question)
	b.WriteString("\nAssistant:")
	return b.String()
}

func (a *Agent) RunCLI(ctx context.Context) error {
	fmt.Println("AI Terminal Agent")
	fmt.Println("Commands: /help /status /model /ls /run /py /exit")

	reg := tools.NewRegistry()
	help := &tools.HelpTool{Reg: reg}
	reg.Register(help)
	reg.Register(&tools.StatusTool{})
	reg.Register(&tools.ModelTool{})
	reg.Register(&tools.LSTool{})
	reg.Register(&tools.RunTool{})
	reg.Register(&tools.PythonTool{})

	rt := &tools.Runtime{
		GetStatus: func() map[string]any {
			return a.Status()
		},
		GetModel: func() string { return a.GetModel() },
		SetModel: func(m string) { a.SetModel(m) },

		EnableFS: func() bool { ok, _ := a.FSSettings(); return ok }(),
		AllowDirs: func() []string { _, dirs := a.FSSettings(); return dirs }(),
		PythonToolsURL: func() string {
			a.mu.RLock()
			defer a.mu.RUnlock()
			return a.cfg.PythonToolsURL
		}(),
	}

	scanner := bufio.NewScanner(os.Stdin)
	// Avoid truncated input (default token limit is 64K) which can corrupt commands.
	scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024)
	for {
		select {
		case <-ctx.Done():
			return nil
		default:
		}

		fmt.Print("\n>>> ")
		ui.FadeInPrompt(">>> ")
		if !scanner.Scan() {
			if err := scanner.Err(); err != nil && err != io.EOF {
				return err
			}
			return nil
		}
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		if line == "/exit" || strings.EqualFold(line, "exit") || strings.EqualFold(line, "quit") {
			return nil
		}

		if strings.HasPrefix(line, "/") {
			name, args := parseCommand(line)
			// Show badge for explicit commands
			if name == "run" {
				fmt.Print(ui.Badge("RUN", "green"))
			} else if name == "ls" {
				fmt.Print(ui.Badge("LS", "blue"))
			} else if name == "py" {
				fmt.Print(ui.Badge("PY", "yellow"))
			}
			out, err := reg.Run(ctx, rt, name, args)
			if err != nil {
				fmt.Println(ui.Badge("ERROR", "red"), err)
				continue
			}
			if strings.TrimSpace(out) != "" {
				fmt.Println(out)
			}
			continue
		}

		// Auto-route common filesystem listing questions to /ls so we don't
		// generate shell commands in the answer.
		if shouldAutoLS(line) {
			fmt.Print(ui.Badge("LS", "blue"))
			out, err := reg.Run(ctx, rt, "ls", nil)
			if err != nil {
				fmt.Println("error:", err)
				continue
			}
			if strings.TrimSpace(out) != "" {
				fmt.Println(out)
			}
			continue
		}

		// Auto-route common "what files are in this directory/folder/dict" queries to /run dir
		if shouldAutoRunDir(line) {
			fmt.Print(ui.Badge("AUTO", "yellow"))
			out, err := reg.Run(ctx, rt, "run", []string{"dir"})
			if err != nil {
				fmt.Println("error:", err)
				continue
			}
			if strings.TrimSpace(out) != "" {
				fmt.Println(out)
			}
			continue
		}

		// Fallback to Python service for any remaining natural-language queries
		out, err := ui.Spinner("Thinking...", func() (string, error) {
			return callPythonService(ctx, rt.PythonToolsURL, line, rt.GetModel())
		})
		if err == nil && out != "" {
			// If the response looks like a JSON plan, execute it
			if strings.HasPrefix(strings.TrimSpace(out), "{") {
				if planOut, planErr := executeJSONPlan(ctx, rt, out); planErr == nil && planOut != "" {
					fmt.Println(planOut)
					continue
				}
			}
			fmt.Println(out)
			continue
		} else if err != nil {
			fmt.Println(ui.Badge("ERROR", "red"), err)
		}

		ans, err := a.Ask(ctx, "cli", line)
		if err != nil {
			fmt.Println("error:", err)
			continue
		}
		fmt.Println(sanitizeForTerminal(ans))
	}
}

func executeJSONPlan(ctx context.Context, rt *tools.Runtime, jsonStr string) (string, error) {
	var plan struct {
		Action    string   `json:"action"`
		Command   string   `json:"command"`
		Arguments []string `json:"arguments"`
	}
	if err := json.Unmarshal([]byte(jsonStr), &plan); err != nil {
		return "", fmt.Errorf("invalid plan JSON")
	}
	switch plan.Action {
	case "run":
		// Prefer command field if present, otherwise construct from arguments
		cmd := plan.Command
		if cmd == "" && len(plan.Arguments) > 0 {
			cmd = strings.Join(plan.Arguments, " ")
		}
		if cmd == "" {
			return "", fmt.Errorf("run plan missing command")
		}
		// Normalize heredoc-style commands for Windows
		cmd = normalizeCommand(cmd)
		runTool := &tools.RunTool{}
		return runTool.Run(ctx, rt, strings.Fields(cmd))
	default:
		return "", fmt.Errorf("unsupported plan action: %s", plan.Action)
	}
}

func normalizeCommand(cmd string) string {
	// Simple heuristic: if it looks like a Python heredoc, convert to -c
	if strings.Contains(cmd, "<<'PY'") {
		start := strings.Index(cmd, "<<'PY'")
		if start == -1 {
			return cmd
		}
		start += len("<<'PY'")
		end := strings.Index(cmd[start:], "PY")
		if end == -1 {
			return cmd
		}
		code := strings.TrimSpace(cmd[start : start+end])
		// Escape quotes and wrap in -c
		code = strings.ReplaceAll(code, `"`, `\"`)
		return fmt.Sprintf("python -c \"%s\"", code)
	}
	// Normalize python3 to python on Windows
	if strings.HasPrefix(cmd, "python3 ") {
		return "python " + cmd[7:]
	}
	return cmd
}

func callPythonService(ctx context.Context, pythonToolsURL, question, model string) (string, error) {
	if pythonToolsURL == "" {
		return "", fmt.Errorf("python service not configured")
	}
	payload := map[string]any{"question": question, "user_id": "cli", "model": model}
	body, _ := json.Marshal(payload)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(pythonToolsURL, "/")+"/ask", bytes.NewReader(body))
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
		return "", fmt.Errorf("python service error: %d", resp.StatusCode)
	}
	var result struct {
		Answer string `json:"answer"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return "", err
	}
	return result.Answer, nil
}

func shouldAutoRunDir(s string) bool {
	s = strings.ToLower(strings.TrimSpace(s))
	if s == "" {
		return false
	}
	// Match variants like "what files are in this directory/folder/dict"
	if strings.Contains(s, "what files") && (strings.Contains(s, "directory") || strings.Contains(s, "folder") || strings.Contains(s, "dict")) {
		return true
	}
	if strings.Contains(s, "what are the files") && (strings.Contains(s, "directory") || strings.Contains(s, "folder") || strings.Contains(s, "dict")) {
		return true
	}
	if strings.Contains(s, "files we have") && (strings.Contains(s, "directory") || strings.Contains(s, "folder") || strings.Contains(s, "dict")) {
		return true
	}
	if strings.Contains(s, "files in this") && (strings.Contains(s, "directory") || strings.Contains(s, "folder") || strings.Contains(s, "dict")) {
		return true
	}
	// Broader triggers: "in this dict", "show me what's here", "what's in here"
	if strings.Contains(s, "in this dict") {
		return true
	}
	if strings.Contains(s, "show me what") && (strings.Contains(s, "here") || strings.Contains(s, "this")) {
		return true
	}
	if strings.Contains(s, "what") && (strings.Contains(s, "here") || strings.Contains(s, "this folder") || strings.Contains(s, "this directory")) {
		return true
	}
	// New triggers: "show me files", "show files", "list files"
	if strings.Contains(s, "show me files") || strings.Contains(s, "show files") || strings.Contains(s, "list files") {
		return true
	}
	return false
}

func shouldAutoLS(s string) bool {
	s = strings.ToLower(strings.TrimSpace(s))
	if s == "" {
		return false
	}
	// Keep this intentionally conservative; we only want to intercept
	// clear "list files" intent.
	if strings.Contains(s, "list files") {
		return true
	}
	if strings.Contains(s, "files are in") && strings.Contains(s, "folder") {
		return true
	}
	if strings.Contains(s, "files are in") && strings.Contains(s, "directory") {
		return true
	}
	if strings.Contains(s, "what files") && (strings.Contains(s, "folder") || strings.Contains(s, "directory")) {
		return true
	}
	if strings.Contains(s, "what are the files") && (strings.Contains(s, "folder") || strings.Contains(s, "directory")) {
		return true
	}
	if strings.Contains(s, "files we have") && (strings.Contains(s, "folder") || strings.Contains(s, "directory")) {
		return true
	}
	if strings.Contains(s, "files in this folder") || strings.Contains(s, "files in this directory") {
		return true
	}
	if strings.HasPrefix(s, "show me the files") {
		return true
	}
	return false
}

func parseCommand(line string) (string, []string) {
	line = strings.TrimSpace(line)
	if !strings.HasPrefix(line, "/") {
		return "", nil
	}
	line = strings.TrimPrefix(line, "/")
	line = strings.TrimSpace(line)
	if line == "" {
		return "", nil
	}
	fields := strings.Fields(line)
	if len(fields) == 0 {
		return "", nil
	}
	name := strings.ToLower(fields[0])
	args := []string{}
	if len(fields) > 1 {
		args = fields[1:]
	}
	return name, args
}

func sanitizeForTerminal(s string) string {
	s = strings.TrimSpace(s)
	if s == "" {
		return ""
	}
	var b strings.Builder
	b.Grow(len(s))
	for _, r := range s {
		// Keep newlines/tabs for readability but remove other control chars that
		// can corrupt the prompt (e.g. stray \r or ANSI-like bytes).
		if r == '\n' || r == '\t' {
			b.WriteRune(r)
			continue
		}
		if unicode.IsControl(r) {
			continue
		}
		b.WriteRune(r)
	}
	return b.String()
}
