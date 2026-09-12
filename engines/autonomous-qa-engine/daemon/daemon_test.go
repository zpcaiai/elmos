package daemon

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestGitHubHMACVerification(t *testing.T) {
	secret := "super-secure-webhook-secret-key-123"
	payload := []byte(`{"action":"opened","pull_request":{"id":42}}`)

	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(payload)
	validSig := "sha256=" + hex.EncodeToString(mac.Sum(nil))

	if !VerifyGitHubHMAC(payload, validSig, secret) {
		t.Errorf("expected valid HMAC verification to succeed")
	}

	if VerifyGitHubHMAC(payload, "sha256=badbadbadbad", secret) {
		t.Errorf("expected invalid HMAC to fail")
	}

	if VerifyGitHubHMAC([]byte(`{"tampered":true}`), validSig, secret) {
		t.Errorf("expected tampered payload to fail")
	}
}

func TestGitLabTokenVerification(t *testing.T) {
	token := "gl-secret-token-xyz"
	if !VerifyGitLabToken(token, token) {
		t.Errorf("expected exact token to match")
	}
	if VerifyGitLabToken("wrong-token", token) {
		t.Errorf("expected wrong token to fail")
	}
}

func TestAhoCorasickCIParser(t *testing.T) {
	parser := NewAhoCorasickLogParser()

	sampleLog := []byte(`[INFO] Starting test suite
[ERROR] AssertionError: expected 42 but got 0 at calculator_test.py:15
[INFO] Running next test
panic: runtime error: invalid memory address or nil pointer dereference
[INFO] Suite finished`)

	matches := parser.ParseLog(sampleLog, 2)
	if len(matches) < 2 {
		t.Fatalf("expected at least 2 failure matches, got %d", len(matches))
	}

	foundAssertion := false
	foundPanic := false
	for _, m := range matches {
		if m.Kind == FailureAssertionError {
			foundAssertion = true
			if m.LineNumber != 2 {
				t.Errorf("expected AssertionError at line 2, got line %d", m.LineNumber)
			}
		}
		if m.Kind == FailurePanic {
			foundPanic = true
			if m.LineNumber != 4 {
				t.Errorf("expected Panic at line 4, got line %d", m.LineNumber)
			}
		}
	}

	if !foundAssertion {
		t.Errorf("expected to find AssertionError")
	}
	if !foundPanic {
		t.Errorf("expected to find Panic")
	}
}

func TestGoASTSafeTransformer(t *testing.T) {
	transformer := NewGoASTSafeTransformer()

	src := []byte(`package sample

import "testing"

func TestAdd(t *testing.T) {
	val := 10
	if val != 10 {
		t.Errorf("expected 10")
	}
	t.Fatalf("critical failure")
}
`)

	if err := transformer.ValidateGoSyntax("sample.go", src); err != nil {
		t.Fatalf("syntax validation failed: %v", err)
	}

	count, err := transformer.CountAssertions("sample.go", src)
	if err != nil {
		t.Fatalf("count assertions failed: %v", err)
	}
	if count != 2 {
		t.Errorf("expected 2 assertions, got %d", count)
	}

	renamed, err := transformer.ReplaceIdentifierInFunction("sample.go", src, "TestAdd", "val", "computed")
	if err != nil {
		t.Fatalf("renaming failed: %v", err)
	}
	if !stringContains(string(renamed), "computed :=") {
		t.Errorf("expected renamed identifier in source:\n%s", string(renamed))
	}
}

func TestProcessSandboxExecution(t *testing.T) {
	sandbox := NewProcessSandbox(5*time.Second, 1024*1024)
	res, err := sandbox.Execute(context.Background(), "", nil, "echo", "elmos-sandbox-ok")
	if err != nil {
		t.Fatalf("sandbox execution failed: %v", err)
	}
	if res.ExitCode != 0 {
		t.Errorf("expected exit code 0, got %d", res.ExitCode)
	}
	if !stringContains(res.Stdout, "elmos-sandbox-ok") {
		t.Errorf("expected stdout to contain test string, got %q", res.Stdout)
	}
}

func TestMerkleDirectoryAuditor(t *testing.T) {
	tempDir, err := os.MkdirTemp("", "merkle-test-*")
	if err != nil {
		t.Fatalf("failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tempDir)

	f1 := filepath.Join(tempDir, "file1.txt")
	f2 := filepath.Join(tempDir, "file2.txt")
	_ = os.WriteFile(f1, []byte("hello world"), 0644)
	_ = os.WriteFile(f2, []byte("autonomous qa"), 0644)

	auditor := NewMerkleDirectoryAuditor()
	root1, digests, err := auditor.ComputeDirectoryMerkleRoot(tempDir)
	if err != nil {
		t.Fatalf("merkle computation failed: %v", err)
	}
	if len(digests) != 2 {
		t.Errorf("expected 2 file digests, got %d", len(digests))
	}
	if len(root1) != 64 {
		t.Errorf("expected 64-char sha256 merkle root, got %s", root1)
	}

	match, err := auditor.VerifyTamper(tempDir, root1)
	if err != nil || !match {
		t.Errorf("expected tamper verification to match: %v", err)
	}

	// Tamper with file
	_ = os.WriteFile(f1, []byte("tampered content"), 0644)
	tamperMatch, _ := auditor.VerifyTamper(tempDir, root1)
	if tamperMatch {
		t.Errorf("expected tampered directory to fail verification")
	}
}

func stringContains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || (len(s) > 0 && len(substr) > 0 && (hasPrefix(s, substr) || stringContains(s[1:], substr))))
}

func hasPrefix(s, prefix string) bool {
	return len(s) >= len(prefix) && s[0:len(prefix)] == prefix
}
