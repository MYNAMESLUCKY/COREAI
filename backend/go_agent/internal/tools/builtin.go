package tools

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"yogz/go_agent/internal/security"
)

type HelpTool struct {
	Reg *Registry
}

func (t *HelpTool) Name() string { return "help" }

func (t *HelpTool) Help() string { return "/help" }

func (t *HelpTool) Run(ctx context.Context, rt *Runtime, args []string) (string, error) {
	_ = ctx
	_ = rt
	if t.Reg == nil {
		return "help unavailable", nil
	}
	b := strings.Builder{}
	b.WriteString("Commands:\n")
	for _, name := range t.Reg.Names() {
		tool, _ := t.Reg.Get(name)
		b.WriteString("/")
		b.WriteString(name)
		if h := strings.TrimSpace(tool.Help()); h != "" {
			b.WriteString(" - ")
			b.WriteString(h)
		}
		b.WriteString("\n")
	}
	b.WriteString("/exit - exit\n")
	return strings.TrimSpace(b.String()), nil
}

type StatusTool struct{}

func (t *StatusTool) Name() string { return "status" }

func (t *StatusTool) Help() string { return "/status" }

func (t *StatusTool) Run(ctx context.Context, rt *Runtime, args []string) (string, error) {
	_ = ctx
	_ = args
	if rt == nil || rt.GetStatus == nil {
		return "status unavailable", nil
	}
	st := rt.GetStatus()
	b, err := json.MarshalIndent(st, "", "  ")
	if err != nil {
		return "status unavailable", nil
	}
	return string(b), nil
}

type ModelTool struct{}

func (t *ModelTool) Name() string { return "model" }

func (t *ModelTool) Help() string { return "/model <name>" }

func (t *ModelTool) Run(ctx context.Context, rt *Runtime, args []string) (string, error) {
	_ = ctx
	if rt == nil {
		return "model unavailable", nil
	}
	if len(args) == 0 {
		if rt.GetModel == nil {
			return "model unavailable", nil
		}
		return fmt.Sprintf("model: %s", rt.GetModel()), nil
	}
	if rt.SetModel == nil {
		return "model unavailable", nil
	}
	m := strings.TrimSpace(strings.Join(args, " "))
	if m == "" {
		return "usage: /model <name>", nil
	}
	// Basic validation against known models
	known := []string{
		"gpt-oss:120b-cloud",
		"deepseek-v3.1:671b-cloud",
		"qwen3-coder:480b-cloud",
		"llama3.1:8b",
		"llama3.1:70b",
		"mistral:7b",
		"codellama:7b",
	}
	valid := false
	for _, k := range known {
		if m == k {
			valid = true
			break
		}
	}
	if !valid {
		return fmt.Sprintf("unknown model: %s (known: %v)", m, known), nil
	}
	rt.SetModel(m)
	return fmt.Sprintf("model: %s", m), nil
}

type LSTool struct{}

func (t *LSTool) Name() string { return "ls" }

func (t *LSTool) Help() string { return "/ls [path]" }

func (t *LSTool) Run(ctx context.Context, rt *Runtime, args []string) (string, error) {
	_ = ctx
	if rt == nil {
		return "filesystem unavailable", nil
	}
	if !rt.EnableFS {
		return "filesystem disabled (set AGENT_ENABLE_FS=true)", nil
	}
	path := "."
	if len(args) > 0 {
		path = strings.TrimSpace(strings.Join(args, " "))
		if path == "" {
			path = "."
		}
	}
	abs, ok := security.IsPathAllowed(path, rt.AllowDirs)
	if !ok {
		return "path not allowed", nil
	}
	ents, err := os.ReadDir(abs)
	if err != nil {
		return "ls failed", nil
	}
	type item struct {
		Name string `json:"name"`
		Type string `json:"type"`
		Size int64  `json:"size_bytes"`
	}
	items := make([]item, 0, len(ents))
	for _, e := range ents {
		it := item{Name: e.Name()}
		if e.IsDir() {
			it.Type = "dir"
			it.Size = 0
		} else {
			it.Type = "file"
			info, err := e.Info()
			if err == nil {
				it.Size = info.Size()
			}
		}
		items = append(items, it)
	}
	sort.Slice(items, func(i, j int) bool {
		if items[i].Type != items[j].Type {
			return items[i].Type < items[j].Type
		}
		return strings.ToLower(items[i].Name) < strings.ToLower(items[j].Name)
	})
	out := map[string]any{
		"path":  filepath.Clean(abs),
		"items": items,
	}
	b, err := json.MarshalIndent(out, "", "  ")
	if err != nil {
		return "ls failed", nil
	}
	return string(b), nil
}
