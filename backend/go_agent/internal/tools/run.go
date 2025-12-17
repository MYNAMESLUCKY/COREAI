package tools

import (
	"context"
	"os"
	"os/exec"
	"runtime"
	"strings"
)

type RunTool struct{}

func (t *RunTool) Name() string { return "run" }

func (t *RunTool) Help() string { return "/run <command> [args...] – execute shell/PowerShell command" }

func (t *RunTool) Run(ctx context.Context, rt *Runtime, args []string) (string, error) {
	if len(args) == 0 {
		return "usage: /run <command> [args...]", nil
	}
	cmdLine := strings.Join(args, " ")
	var cmd *exec.Cmd
	if runtime.GOOS == "windows" {
		// Prefer PowerShell for richer experience; fallback to cmd if unavailable
		if _, err := exec.LookPath("powershell"); err == nil {
			cmd = exec.CommandContext(ctx, "powershell", "-Command", cmdLine)
		} else {
			cmd = exec.CommandContext(ctx, "cmd", "/C", cmdLine)
		}
	} else {
		// Unix-like: use sh (or bash if available)
		shell := "sh"
		if _, err := exec.LookPath("bash"); err == nil {
			shell = "bash"
		}
		cmd = exec.CommandContext(ctx, shell, "-c", cmdLine)
	}
	// Inherit the current process environment and working directory
	cmd.Env = os.Environ()
	cmd.Dir = "."
	out, err := cmd.CombinedOutput()
	res := string(out)
	if err != nil {
		// Include error text but still return whatever we got
		if res != "" {
			res = strings.TrimSpace(res) + "\n"
		}
		res += "error: " + err.Error()
	}
	return res, nil
}
