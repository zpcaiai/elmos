package executor

import (
	"os"
	"testing"

	"github.com/acme/migration-platform/runner/internal/protocol"
)

func TestExecuteEchoArtifact(t *testing.T) {
	root := t.TempDir()
	result, err := Execute(root, protocol.ClaimJobResponse{
		JobID:   "job-1",
		JobType: "echo-artifact",
		Payload: `{"hello":"world"}`,
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(result.ArtifactPath); err != nil {
		t.Fatalf("artifact missing: %v", err)
	}
}
