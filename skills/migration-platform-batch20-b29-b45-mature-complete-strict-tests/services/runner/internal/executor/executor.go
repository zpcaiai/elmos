package executor

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/acme/migration-platform/runner/internal/client"
	"github.com/acme/migration-platform/runner/internal/protocol"
)

type Result struct {
	OutputPayload string
	ArtifactPath  string
}

func Execute(workRoot string, job protocol.ClaimJobResponse) (Result, error) {
	if job.JobType != "echo-artifact" {
		return Result{}, fmt.Errorf("%w: %s", client.ErrUnsupportedJob, job.JobType)
	}
	jobDir := filepath.Join(workRoot, job.JobID)
	if err := os.MkdirAll(jobDir, 0o750); err != nil {
		return Result{}, fmt.Errorf("create job workspace: %w", err)
	}
	artifact := map[string]any{
		"job_id":       job.JobID,
		"job_type":     job.JobType,
		"payload":      json.RawMessage(job.Payload),
		"completed_at": time.Now().UTC().Format(time.RFC3339Nano),
		"runner":       "go-runner",
	}
	data, err := json.MarshalIndent(artifact, "", "  ")
	if err != nil {
		return Result{}, fmt.Errorf("encode artifact: %w", err)
	}
	path := filepath.Join(jobDir, "artifact.json")
	if err := os.WriteFile(path, data, 0o640); err != nil {
		return Result{}, fmt.Errorf("write artifact: %w", err)
	}
	output, _ := json.Marshal(map[string]any{"message": "job executed", "bytes": len(data)})
	return Result{OutputPayload: string(output), ArtifactPath: path}, nil
}
