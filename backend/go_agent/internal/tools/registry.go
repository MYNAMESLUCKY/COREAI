package tools

import (
	"context"
	"fmt"
	"sort"
	"strings"
)

type Registry struct {
	tools map[string]Tool
}

func NewRegistry(ts ...Tool) *Registry {
	r := &Registry{tools: map[string]Tool{}}
	for _, t := range ts {
		r.Register(t)
	}
	return r
}

func (r *Registry) Register(t Tool) {
	if t == nil {
		return
	}
	name := strings.ToLower(strings.TrimSpace(t.Name()))
	if name == "" {
		return
	}
	r.tools[name] = t
}

func (r *Registry) Get(name string) (Tool, bool) {
	name = strings.ToLower(strings.TrimSpace(name))
	t, ok := r.tools[name]
	return t, ok
}

func (r *Registry) Names() []string {
	out := make([]string, 0, len(r.tools))
	for k := range r.tools {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

func (r *Registry) Run(ctx context.Context, rt *Runtime, name string, args []string) (string, error) {
	t, ok := r.Get(name)
	if !ok {
		return "", fmt.Errorf("unknown command: %s", name)
	}
	return t.Run(ctx, rt, args)
}
