package ui

import (
	"fmt"
	"time"
)

// Spinner shows a simple inline spinner while a function runs.
// It prints a message, spins, then clears the line.
func Spinner(msg string, fn func() (string, error)) (string, error) {
	spinChars := []string{"|", "/", "-", "\\"}
	i := 0
	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()

	done := make(chan struct{})
	var result string
	var err error

	go func() {
		result, err = fn()
		close(done)
	}()

	for {
		select {
		case <-done:
			fmt.Print("\r")
			return result, err
		case <-ticker.C:
			fmt.Printf("\r%s %s", spinChars[i%len(spinChars)], msg)
			i++
		}
	}
}

// Badge prints a styled badge prefix for command outputs.
func Badge(label, color string) string {
	// Simple ANSI color codes
	colors := map[string]string{
		"green":  "\033[92m",
		"red":    "\033[91m",
		"yellow": "\033[93m",
		"blue":   "\033[94m",
		"gray":   "\033[90m",
	}
	reset := "\033[0m"
	if c, ok := colors[color]; ok {
		return fmt.Sprintf("%s[%s]%s ", c, label, reset)
	}
	return fmt.Sprintf("[%s] ", label)
}

// ClearLine clears the current terminal line.
func ClearLine() {
	fmt.Print("\r\033[K")
}

// FadeInPrompt prints a subtle fade-in effect for the prompt.
func FadeInPrompt(prompt string) {
	// Simple fade: print dots then replace with prompt
	for i := 0; i < 3; i++ {
		fmt.Print(".")
		time.Sleep(60 * time.Millisecond)
	}
	ClearLine()
	fmt.Print(prompt)
}
