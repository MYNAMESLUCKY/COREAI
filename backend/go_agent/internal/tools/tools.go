package tools

import (
	"context"
)

type Runtime struct {
	GetStatus func() map[string]any
	GetModel  func() string
	SetModel  func(string)

	EnableFS bool
	AllowDirs []string

	PythonToolsURL string
}

type Tool interface {
	Name() string
	Help() string
	Run(ctx context.Context, rt *Runtime, args []string) (string, error)
}
