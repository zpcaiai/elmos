//go:build unix

// elmos-supervisor is a local process adapter, NOT a second fleet/lease agent.
// Java retains credentials, admission, sandbox policy and artifact publication.
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"os/signal"
	"syscall"
	"time"
)

func supervise(ctx context.Context, args []string, grace time.Duration, stdout, stderr io.Writer) int {
	if len(args) == 0 || grace <= 0 || grace > 30*time.Second {
		return 78
	}
	// No shell interpolation, environment expansion, network client or job queue.
	cmd := exec.Command(args[0], args[1:]...)
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	cmd.Stdin, cmd.Stdout, cmd.Stderr = os.Stdin, stdout, stderr
	// Java provides an explicit, scrubbed environment before starting this adapter.
	cmd.Env = os.Environ()
	cmd.WaitDelay = grace
	if err := cmd.Start(); err != nil {
		fmt.Fprintln(stderr, "supervisor: spawn failed")
		return 127
	}
	done := make(chan error, 1)
	go func() { done <- cmd.Wait() }()
	select {
	case err := <-done:
		// A shell's success must not leave ordinary background children behind.
		_ = syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
		if err == nil {
			return 0
		}
		var exit *exec.ExitError
		if errors.As(err, &exit) && exit.ExitCode() >= 0 {
			return exit.ExitCode()
		}
		return 1
	case <-ctx.Done():
		_ = syscall.Kill(-cmd.Process.Pid, syscall.SIGTERM)
		timer := time.NewTimer(grace)
		defer timer.Stop()
		// Keep the group alive through the grace interval even if its leader exits.
		<-timer.C
		_ = syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
		<-done
		if errors.Is(ctx.Err(), context.DeadlineExceeded) {
			return 124
		}
		return 130
	}
}

func main() {
	grace := flag.Duration("grace", time.Second, "process-group termination grace (0..30s)")
	flag.Parse()
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer stop()
	os.Exit(supervise(ctx, flag.Args(), *grace, os.Stdout, os.Stderr))
}
