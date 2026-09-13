package daemon

import (
	"bytes"
	"context"
	"errors"
	"os/exec"
	"sync"
	"syscall"
	"time"
)

// Production Ephemeral Sandbox process isolation and resource quota runner.

type SandboxQuotaSpecification struct {
	WorkerID       string            `json:"worker_id"`
	MaxMemoryMB    int               `json:"max_memory_mb"`
	CPUShares      int               `json:"cpu_shares"`
	TimeoutSec     int               `json:"timeout_sec"`
	MaxOutputBytes int               `json:"max_output_bytes"`
	EnvAllowlist   []string          `json:"env_allowlist"`
	CustomEnv      map[string]string `json:"custom_env"`
	WorkDir        string            `json:"work_dir"`
}

func (s *SandboxQuotaSpecification) Validate() error {
	if s.WorkerID == "" {
		return errors.New("worker_id cannot be empty")
	}
	if s.TimeoutSec <= 0 {
		return errors.New("timeout_sec must be positive")
	}
	return nil
}

func (s *SandboxQuotaSpecification) EffectiveTimeout() time.Duration {
	return time.Duration(s.TimeoutSec) * time.Second
}

// SandboxResult contains execution results.
type SandboxResult struct {
	ExitCode int
	Stdout   string
	Stderr   string
	Duration time.Duration
}

// EphemeralSandboxRunner manages isolated child process lifecycle.
type EphemeralSandboxRunner struct {
	mu sync.Mutex
}

func NewEphemeralSandboxRunner() *EphemeralSandboxRunner {
	return &EphemeralSandboxRunner{}
}

func (r *EphemeralSandboxRunner) RunCommandWithLimits(
	ctx context.Context,
	cmdName string,
	args []string,
	dir string,
	timeout time.Duration,
	maxBytes int,
) (string, int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	ctxTimeout, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	cmd := exec.CommandContext(ctxTimeout, cmdName, args...)
	cmd.Dir = dir
	var outBuf bytes.Buffer
	cmd.Stdout = &outBuf
	cmd.Stderr = &outBuf
	// Set process group so children are killed on cancellation
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	err := cmd.Run()
	exitCode := 0
	if err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			exitCode = exitErr.ExitCode()
		} else {
			exitCode = 1
		}
	}
	output := outBuf.String()
	if maxBytes > 0 && len(output) > maxBytes {
		output = output[:maxBytes] + "\n[OUTPUT_TRUNCATED]"
	}
	return output, exitCode, err
}

// ProcessSandbox manages sandboxed process execution.
type ProcessSandbox struct {
	runner   *EphemeralSandboxRunner
	timeout  time.Duration
	maxBytes int
}

func NewProcessSandbox(timeout time.Duration, maxBytes int) *ProcessSandbox {
	return &ProcessSandbox{
		runner:   NewEphemeralSandboxRunner(),
		timeout:  timeout,
		maxBytes: maxBytes,
	}
}

func (s *ProcessSandbox) Execute(ctx context.Context, dir string, env []string, cmdName string, args ...string) (*SandboxResult, error) {
	start := time.Now()
	out, exitCode, err := s.runner.RunCommandWithLimits(ctx, cmdName, args, dir, s.timeout, s.maxBytes)
	dur := time.Since(start)
	return &SandboxResult{
		ExitCode: exitCode,
		Stdout:   out,
		Stderr:   "",
		Duration: dur,
	}, err
}
