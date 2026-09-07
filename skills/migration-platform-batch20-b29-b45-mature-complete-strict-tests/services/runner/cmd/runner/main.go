package main

import (
	"context"
	"errors"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/acme/migration-platform/runner/internal/client"
	"github.com/acme/migration-platform/runner/internal/executor"
	"github.com/acme/migration-platform/runner/internal/protocol"
)

func main() {
	baseURL := env("CONTROL_PLANE_URL", "http://localhost:8080")
	name := env("RUNNER_NAME", "local-runner")
	workRoot := env("RUNNER_WORK_ROOT", "./runner-work")
	pollInterval, err := time.ParseDuration(env("RUNNER_POLL_INTERVAL", "2s"))
	if err != nil {
		log.Fatalf("invalid RUNNER_POLL_INTERVAL: %v", err)
	}

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	api := client.New(baseURL)
	registration, err := retryRegister(ctx, api, protocol.RegisterRequest{
		Name:         name,
		Version:      "0.1.0",
		Capabilities: []string{"echo-artifact", "local-workspace"},
	})
	if err != nil {
		log.Fatalf("register runner: %v", err)
	}
	log.Printf("registered runner %s", registration.RunnerID)

	heartbeatTicker := time.NewTicker(10 * time.Second)
	pollTicker := time.NewTicker(pollInterval)
	defer heartbeatTicker.Stop()
	defer pollTicker.Stop()

	for {
		select {
		case <-ctx.Done():
			log.Printf("runner stopping")
			return
		case <-heartbeatTicker.C:
			if err := api.Heartbeat(ctx, registration.RunnerID); err != nil {
				log.Printf("heartbeat failed: %v", err)
			}
		case <-pollTicker.C:
			job, err := api.Claim(ctx, registration.RunnerID)
			if err != nil {
				log.Printf("claim failed: %v", err)
				continue
			}
			if job == nil {
				continue
			}
			result, executeErr := executor.Execute(workRoot, *job)
			status := "completed"
			output := result.OutputPayload
			if executeErr != nil {
				status = "failed"
				output = `{"error":"execution failed"}`
				if !errors.Is(executeErr, client.ErrUnsupportedJob) {
					log.Printf("job %s failed: %v", job.JobID, executeErr)
				}
			}
			if err := api.Complete(ctx, job.JobID, protocol.CompleteJobRequest{
				CommitToken: job.CommitToken,
				Status:      status, OutputPayload: output, ArtifactPath: result.ArtifactPath,
			}); err != nil {
				log.Printf("complete job %s failed: %v", job.JobID, err)
			}
		}
	}
}

func retryRegister(ctx context.Context, api *client.Client, request protocol.RegisterRequest) (protocol.RegisterResponse, error) {
	var lastErr error
	for attempt := 1; attempt <= 30; attempt++ {
		response, err := api.Register(ctx, request)
		if err == nil {
			return response, nil
		}
		lastErr = err
		select {
		case <-ctx.Done():
			return protocol.RegisterResponse{}, ctx.Err()
		case <-time.After(2 * time.Second):
		}
	}
	return protocol.RegisterResponse{}, lastErr
}

func env(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}
