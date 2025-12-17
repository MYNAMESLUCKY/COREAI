package server

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os/exec"
	"runtime"
	"strings"
	"time"

	"yogz/go_agent/internal/agent"
	"yogz/go_agent/internal/auth"
	"yogz/go_agent/internal/config"
	"yogz/go_agent/internal/limits"
	"yogz/go_agent/internal/security"
	"yogz/go_agent/internal/tools"
	"yogz/go_agent/internal/audit"
	"yogz/go_agent/internal/tokens"
)

type Server struct {
	cfg config.Config
	ag  *agent.Agent
}

func New(cfg config.Config, ag *agent.Agent) *Server {
	return &Server{cfg: cfg, ag: ag}
}

type askRequest struct {
	Question string `json:"question"`
}

type askResponse struct {
	Answer string `json:"answer"`
	TS     string `json:"ts"`
}

func (s *Server) Run(ctx context.Context, addr string) error {
	mux := http.NewServeMux()
	aud := audit.New(s.cfg.AuditLogPath)

	reg := tools.NewRegistry()
	help := &tools.HelpTool{Reg: reg}
	reg.Register(help)
	reg.Register(&tools.StatusTool{})
	reg.Register(&tools.ModelTool{})
	reg.Register(&tools.LSTool{})
	reg.Register(&tools.PythonTool{})

	rt := &tools.Runtime{
		GetStatus: func() map[string]any { return s.ag.Status() },
		GetModel:  func() string { return s.ag.GetModel() },
		SetModel:  func(m string) { s.ag.SetModel(m) },
		EnableFS: func() bool {
			ok, _ := s.ag.FSSettings()
			return ok
		}(),
		AllowDirs: func() []string {
			_, dirs := s.ag.FSSettings()
			return dirs
		}(),
		PythonToolsURL: strings.TrimRight(s.cfg.PythonToolsURL, "/"),
	}

	mux.HandleFunc("/v1/status", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, map[string]any{
			"status":             "ok",
			"model":              s.ag.GetModel(),
			"ollama_host":         s.cfg.OllamaHost,
			"max_input_chars":     s.cfg.MaxInputChars,
			"max_output_chars":    s.cfg.MaxOutputChars,
			"rate_limit_per_min":  s.cfg.RateLimitPerMin,
			"auth_required":       len(s.cfg.APIKeys) > 0,
			"fs_enabled":          s.cfg.EnableFS,
			"allowed_directories": s.cfg.AllowDirs,
		})
	})

	mux.Handle("/v1/tools/list", auth.Middleware(s.cfg, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeErrJSON(w, http.StatusMethodNotAllowed, "method_not_allowed", "use GET")
			return
		}
		writeJSON(w, map[string]any{"tools": reg.Names()})
	})))

	type runToolRequest struct {
		Name string   `json:"name"`
		Args []string `json:"args"`
	}
	mux.Handle("/v1/tools/run", auth.Middleware(s.cfg, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeErrJSON(w, http.StatusMethodNotAllowed, "method_not_allowed", "use POST")
			return
		}
		var req runToolRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeErrJSON(w, http.StatusBadRequest, "invalid_json", "invalid json")
			return
		}
		name := strings.TrimSpace(req.Name)
		if name == "" {
			writeErrJSON(w, http.StatusBadRequest, "missing_name", "missing tool name")
			return
		}
		out, err := reg.Run(r.Context(), rt, name, req.Args)
		if err != nil {
			writeErrJSON(w, http.StatusBadRequest, "tool_error", err.Error())
			return
		}
		writeJSON(w, map[string]any{"name": name, "output": out})
	})))

	mux.Handle("/v1/ask", auth.Middleware(s.cfg, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeErrJSON(w, http.StatusMethodNotAllowed, "method_not_allowed", "use POST")
			return
		}
		var req askRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeErrJSON(w, http.StatusBadRequest, "invalid_json", "invalid json")
			return
		}
		q := tokens.ClampChars(req.Question, s.cfg.MaxInputChars)
		if q == "" {
			writeErrJSON(w, http.StatusBadRequest, "missing_question", "missing question")
			return
		}
		userID := auth.UserIDFromRequest(r)
		// Forward to Python agent service
		pyURL := strings.TrimRight(s.cfg.PythonToolsURL, "/") + "/ask"
		payload := map[string]any{"question": q, "user_id": userID}
		bodyBytes, _ := json.Marshal(payload)
		resp, err := http.Post(pyURL, "application/json", strings.NewReader(string(bodyBytes)))
		if err != nil {
			writeErrJSON(w, http.StatusBadGateway, "python_service_unavailable", "python agent service unavailable")
			return
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			writeErrJSON(w, http.StatusBadGateway, "python_service_error", "python agent service error")
			return
		}
		var pyResp askResponse
		if err := json.NewDecoder(resp.Body).Decode(&pyResp); err != nil {
			writeErrJSON(w, http.StatusInternalServerError, "invalid_python_response", "invalid response from python service")
			return
		}
		// If Python returned a JSON plan, execute it and return the result
		if strings.HasPrefix(strings.TrimSpace(pyResp.Answer), "{") {
			if planOut, err := executeJSONPlanAPI(r.Context(), s, pyResp.Answer); err == nil && planOut != "" {
				writeJSON(w, askResponse{Answer: tokens.ClampChars(planOut, s.cfg.MaxOutputChars), TS: pyResp.TS})
				return
			}
		}
		writeJSON(w, askResponse{Answer: tokens.ClampChars(pyResp.Answer, s.cfg.MaxOutputChars), TS: pyResp.TS})
	})))

	mux.Handle("/v1/fs/read", auth.Middleware(s.cfg, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !s.cfg.EnableFS {
			writeErrJSON(w, http.StatusForbidden, "fs_disabled", "filesystem disabled")
			return
		}
		if r.Method != http.MethodPost {
			writeErrJSON(w, http.StatusMethodNotAllowed, "method_not_allowed", "use POST")
			return
		}
		var req struct {
			Path string `json:"path"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeErrJSON(w, http.StatusBadRequest, "invalid_json", "invalid json")
			return
		}
		abs, ok := security.IsPathAllowed(req.Path, s.cfg.AllowDirs)
		if !ok {
			writeErrJSON(w, http.StatusForbidden, "path_not_allowed", "path not allowed")
			return
		}
		b, err := security.ReadFileLimited(abs, 256*1024)
		if err != nil {
			writeErrJSON(w, http.StatusBadRequest, "read_failed", "read failed")
			return
		}
		writeJSON(w, map[string]any{"path": abs, "content": string(b)})
	})))

	lim := limits.NewKeyedLimiter(s.cfg.RateLimitPerMin)
	h := lim.Middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		rw := &statusWriter{ResponseWriter: w, status: 200}
		mux.ServeHTTP(rw, r)
		aud.Write(audit.Event{
			Kind:   "http",
			UserID: auth.UserIDFromRequest(r),
			IP:     clientIP(r),
			Method: r.Method,
			Path:   r.URL.Path,
			Status: rw.status,
		})
	}))

	srv := &http.Server{Addr: addr, Handler: h}
	go func() {
		<-ctx.Done()
		ctx2, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = srv.Shutdown(ctx2)
	}()

	log.Println("listening on", addr)
	err := srv.ListenAndServe()
	if err == http.ErrServerClosed {
		return nil
	}
	return err
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(v)
}

func writeErrJSON(w http.ResponseWriter, code int, kind, msg string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(map[string]any{"error": map[string]any{"kind": kind, "message": msg}})
}

func executeJSONPlanAPI(ctx context.Context, s *Server, jsonStr string) (string, error) {
	var plan struct {
		Action  string `json:"action"`
		Command string `json:"command"`
	}
	if err := json.Unmarshal([]byte(jsonStr), &plan); err != nil {
		return "", fmt.Errorf("invalid plan JSON")
	}
	switch plan.Action {
	case "run":
		if plan.Command == "" {
			return "", fmt.Errorf("run plan missing command")
		}
		cmd := normalizeCommandAPI(plan.Command)
		var execCmd *exec.Cmd
		if runtime.GOOS == "windows" {
			execCmd = exec.CommandContext(ctx, "powershell", "-Command", cmd)
		} else {
			execCmd = exec.CommandContext(ctx, "sh", "-c", cmd)
		}
		out, err := execCmd.CombinedOutput()
		if err != nil {
			return fmt.Sprintf("Error: %v\nOutput: %s", err, out), nil
		}
		return string(out), nil
	default:
		return "", fmt.Errorf("unsupported plan action: %s", plan.Action)
	}
}

func normalizeCommandAPI(cmd string) string {
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
		code = strings.ReplaceAll(code, `"`, `\"`)
		return fmt.Sprintf("python -c \"%s\"", code)
	}
	return cmd
}

type statusWriter struct {
	http.ResponseWriter
	status int
}

func (w *statusWriter) WriteHeader(code int) {
	w.status = code
	w.ResponseWriter.WriteHeader(code)
}

func clientIP(r *http.Request) string {
	if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
		parts := strings.Split(xff, ",")
		return strings.TrimSpace(parts[0])
	}
	return r.RemoteAddr
}
