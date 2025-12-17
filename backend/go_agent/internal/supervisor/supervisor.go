package supervisor

import (
	"context"
	"errors"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"

	"yogz/go_agent/internal/config"
)

type Result struct {
	PythonURL string
	Stop      func()
}

func EnsurePythonService(ctx context.Context, cfg config.Config) (Result, error) {
	// If user explicitly configured a URL and it's already healthy, use it.
	if strings.TrimSpace(cfg.PythonToolsURL) != "" {
		if isHealthy(ctx, strings.TrimRight(cfg.PythonToolsURL, "/")) {
			return Result{PythonURL: strings.TrimRight(cfg.PythonToolsURL, "/"), Stop: func() {}}, nil
		}
	}

	if runtime.GOOS != "windows" {
		return Result{}, fmt.Errorf("supervisor currently supports windows only")
	}

	entry, err := resolvePythonAgentEntry(cfg.PythonAgentEntry)
	if err != nil {
		return Result{}, err
	}

	port, err := freeLocalPort()
	if err != nil {
		return Result{}, err
	}
	pythonURL := fmt.Sprintf("http://127.0.0.1:%d", port)

	logFile, err := openLogFile("python_agent.log")
	if err != nil {
		return Result{}, err
	}
	// closed in Stop

	cmd := exec.CommandContext(ctx, "python", entry)
	cmd.Env = append(os.Environ(),
		"PYTHONUNBUFFERED=1",
		"PYTHON_AGENT_HOST=127.0.0.1",
		fmt.Sprintf("PYTHON_AGENT_PORT=%d", port),
	)
	cmd.Stdout = logFile
	cmd.Stderr = logFile

	if err := cmd.Start(); err != nil {
		_ = logFile.Close()
		return Result{}, err
	}

	exited := make(chan error, 1)
	go func() {
		exited <- cmd.Wait()
	}()

	stop := func() {
		_ = cmd.Process.Kill()
		select {
		case <-exited:
		case <-time.After(2 * time.Second):
		}
		_ = logFile.Close()
	}

	ready := waitHealthy(ctx, pythonURL, 60*time.Second)
	if !ready {
		select {
		case err := <-exited:
			stop()
			return Result{}, fmt.Errorf("python agent exited during startup: %v", err)
		default:
		}
		stop()
		return Result{}, fmt.Errorf("python agent service failed to start")
	}

	return Result{PythonURL: pythonURL, Stop: stop}, nil
}

func freeLocalPort() (int, error) {
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return 0, err
	}
	defer l.Close()
	addr := l.Addr().(*net.TCPAddr)
	return addr.Port, nil
}

func isHealthy(ctx context.Context, baseURL string) bool {
	c := &http.Client{Timeout: 2 * time.Second}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, strings.TrimRight(baseURL, "/")+"/status", nil)
	if err != nil {
		return false
	}
	resp, err := c.Do(req)
	if err != nil {
		return false
	}
	defer resp.Body.Close()
	return resp.StatusCode == http.StatusOK
}

func waitHealthy(ctx context.Context, baseURL string, timeout time.Duration) bool {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if isHealthy(ctx, baseURL) {
			return true
		}
		select {
		case <-ctx.Done():
			return false
		case <-time.After(300 * time.Millisecond):
		}
	}
	return false
}

func resolvePythonAgentEntry(cfgVal string) (string, error) {
	cfgVal = strings.TrimSpace(cfgVal)
	candidates := []string{}
	if cfgVal != "" {
		candidates = append(candidates, cfgVal)
	}

	exe, err := os.Executable()
	if err == nil {
		exeDir := filepath.Dir(exe)
		candidates = append(candidates,
			filepath.Join(exeDir, "python_agent_server.py"),
			filepath.Clean(filepath.Join(exeDir, "..", "python_agent_server.py")),
		)
	}

	for _, p := range candidates {
		p = filepath.Clean(p)
		if filepath.IsAbs(p) {
			if fileExists(p) {
				return p, nil
			}
			continue
		}
		// Relative: resolve against current working directory
		abs, _ := filepath.Abs(p)
		if fileExists(abs) {
			return abs, nil
		}
	}
	return "", errors.New("python agent entry not found (set PYTHON_AGENT_ENTRY)")
}

func fileExists(p string) bool {
	st, err := os.Stat(p)
	if err != nil {
		return false
	}
	return !st.IsDir()
}

func openLogFile(name string) (*os.File, error) {
	dir := os.Getenv("APPDATA")
	if strings.TrimSpace(dir) == "" {
		return nil, fmt.Errorf("APPDATA not set")
	}
	logDir := filepath.Join(dir, "Yogz", "logs")
	if err := os.MkdirAll(logDir, 0o755); err != nil {
		return nil, err
	}
	p := filepath.Join(logDir, name)
	return os.OpenFile(p, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
}
