package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"

	"yogz/go_agent/internal/agent"
	"yogz/go_agent/internal/config"
	"yogz/go_agent/internal/server"
	"yogz/go_agent/internal/supervisor"
)

func main() {
	cfg := config.Load()

	mode := flag.String("mode", "cli", "cli|api")
	host := flag.String("host", cfg.Host, "API host")
	port := flag.Int("port", cfg.Port, "API port")
	flag.Parse()

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	res, err := supervisor.EnsurePythonService(ctx, cfg)
	if err != nil {
		log.Fatal(err)
	}
	defer res.Stop()
	cfg.PythonToolsURL = res.PythonURL

	ag := agent.New(cfg)

	switch *mode {
	case "cli":
		if err := ag.RunCLI(ctx); err != nil {
			log.Fatal(err)
		}
	case "api":
		srv := server.New(cfg, ag)
		addr := fmt.Sprintf("%s:%d", *host, *port)
		if err := srv.Run(ctx, addr); err != nil {
			log.Fatal(err)
		}
	default:
		fmt.Fprintln(os.Stderr, "invalid --mode; use cli or api")
		os.Exit(2)
	}
}
