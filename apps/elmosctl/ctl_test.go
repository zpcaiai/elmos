package main

import (
	"bytes"
	"strings"
	"testing"
)

func TestMutationRequiresExplicitEvidenceAndConfirmation(t *testing.T) {
	var out, err bytes.Buffer
	code := Run([]string{"install"}, &out, &err)
	if code != 3 {
		t.Fatalf("expected code 3 for install without flags, got %d", code)
	}
	if !strings.Contains(err.String(), "APPROVED_EVIDENCE_AND_CONFIRMATION_REQUIRED") {
		t.Fatalf("expected error message to contain APPROVED_EVIDENCE_AND_CONFIRMATION_REQUIRED, got %s", err.String())
	}

	out.Reset()
	err.Reset()
	code = Run([]string{"install", "--evidence-approved", "--confirm"}, &out, &err)
	if code != 0 {
		t.Fatalf("expected code 0 for confirmed install, got %d", code)
	}
	if !strings.Contains(out.String(), "ACCEPTED_FOR_EXTERNAL_EXECUTION") {
		t.Fatalf("expected status ACCEPTED_FOR_EXTERNAL_EXECUTION, got %s", out.String())
	}
}

func TestVerificationWithoutTargetIsExplicitlyNotRun(t *testing.T) {
	var out, err bytes.Buffer
	code := Run([]string{"verify"}, &out, &err)
	if code != 4 {
		t.Fatalf("expected code 4, got %d", code)
	}
	if !strings.Contains(out.String(), "NOT_RUN") {
		t.Fatalf("expected output to contain NOT_RUN, got %s", out.String())
	}
}

func TestUnknownCommand(t *testing.T) {
	var out, err bytes.Buffer
	code := Run([]string{"invalid-cmd"}, &out, &err)
	if code != 2 {
		t.Fatalf("expected code 2 for unknown command, got %d", code)
	}
	if !strings.Contains(err.String(), "UNKNOWN_COMMAND") {
		t.Fatalf("expected UNKNOWN_COMMAND error, got %s", err.String())
	}

	out.Reset()
	err.Reset()
	code = Run([]string{}, &out, &err)
	if code != 2 {
		t.Fatalf("expected code 2 for empty args, got %d", code)
	}
}

func TestReadonlyCommands(t *testing.T) {
	tests := []struct {
		cmd        string
		wantStatus string
		wantReason string
		wantCode   int
	}{
		{"preflight", "NOT_RUN", "TARGET_INSTALLATION_REQUIRED", 4},
		{"status", "NOT_CONFIGURED", "INSTALLATION_CONTEXT_REQUIRED", 4},
		{"diagnostics", "NOT_RUN", "REDACTED_DIAGNOSTIC_TARGET_REQUIRED", 4},
		{"backup", "BLOCKED", "BACKUP_TARGET_AND_KEY_REQUIRED", 4},
	}

	for _, tt := range tests {
		var out, err bytes.Buffer
		code := Run([]string{tt.cmd}, &out, &err)
		if code != tt.wantCode {
			t.Errorf("cmd %s: expected exit code %d, got %d", tt.cmd, tt.wantCode, code)
		}
		if !strings.Contains(out.String(), tt.wantStatus) {
			t.Errorf("cmd %s: expected status %s, got %s", tt.cmd, tt.wantStatus, out.String())
		}
		if !strings.Contains(out.String(), tt.wantReason) {
			t.Errorf("cmd %s: expected reason %s, got %s", tt.cmd, tt.wantReason, out.String())
		}
	}
}
