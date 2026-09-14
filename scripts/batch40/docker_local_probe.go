package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
)

type control struct {
	ControlID string   `json:"controlId"`
	Status    string   `json:"status"`
	Details   []string `json:"details"`
}

type envelope struct {
	ArtifactDigest string `json:"artifactDigest"`
	BuilderID      string `json:"builderId"`
	RunnerProfile  string `json:"runnerProfile"`
	TenantID       string `json:"tenantId"`
}

type probeReport struct {
	SchemaVersion           int                 `json:"schemaVersion"`
	ProbeVersion            int                 `json:"probeVersion"`
	Status                  string              `json:"status"`
	Runtime                 map[string]any      `json:"runtime"`
	Controls                []control           `json:"controls"`
	FailedControls          []string            `json:"failedControls"`
	Corpora                 map[string][]string `json:"corpora"`
	IndependentVerification string              `json:"independentVerification"`
	CertificationStatus     string              `json:"certificationStatus"`
}

func digest(payload []byte) string {
	sum := sha256.Sum256(payload)
	return "sha256:" + hex.EncodeToString(sum[:])
}

func sign(secret, payload []byte) string {
	mac := hmac.New(sha256.New, secret)
	_, _ = mac.Write(payload)
	return hex.EncodeToString(mac.Sum(nil))
}

func verify(secret, payload []byte, signature string) bool {
	decoded, err := hex.DecodeString(signature)
	if err != nil || len(decoded) == 0 {
		return false
	}
	mac := hmac.New(sha256.New, secret)
	_, _ = mac.Write(payload)
	return hmac.Equal(decoded, mac.Sum(nil))
}

func validEnvelope(value envelope, expectedDigest, expectedTenant string) bool {
	return value.ArtifactDigest == expectedDigest &&
		value.BuilderID == "elmos-local-scratch-builder-v1" &&
		value.RunnerProfile == "nonroot-readonly-network-none-v1" &&
		value.TenantID == expectedTenant
}

func disjoint(groups ...[]string) bool {
	seen := map[string]bool{}
	for _, group := range groups {
		for _, item := range group {
			if item == "" || seen[item] {
				return false
			}
			seen[item] = true
		}
	}
	return true
}

func main() {
	artifact := []byte("elmos-b40-local-fixture:v1")
	tampered := []byte("elmos-b40-local-fixture:v1-tampered")
	secret := []byte("local-ephemeral-fixture-key-not-production")
	signature := sign(secret, artifact)
	artifactDigest := digest(artifact)
	attestation := envelope{
		ArtifactDigest: artifactDigest,
		BuilderID:      "elmos-local-scratch-builder-v1",
		RunnerProfile:  "nonroot-readonly-network-none-v1",
		TenantID:       "tenant-local-a",
	}
	downgraded := attestation
	downgraded.RunnerProfile = "privileged-network-host"
	wrongTenant := attestation
	wrongTenant.TenantID = "tenant-local-b"
	wrongSubject := attestation
	wrongSubject.ArtifactDigest = digest(tampered)

	development := []string{"dev-valid-signature-v1", "dev-valid-attestation-v1"}
	holdout := []string{"holdout-tampered-artifact-v1", "holdout-unsigned-artifact-v1"}
	representative := []string{"representative-runner-downgrade-v1", "representative-cross-tenant-v1"}
	overlap := []string{"holdout-tampered-artifact-v1"}

	controls := []control{}
	add := func(id string, passed bool, details ...string) {
		status := "FAIL"
		if passed {
			status = "PASS"
		}
		controls = append(controls, control{ControlID: id, Status: status, Details: details})
	}
	add("B40-LOCAL-SIGNATURE-VALID", verify(secret, artifact, signature), "valid local fixture signature accepted")
	add("B40-LOCAL-TAMPER-REJECTION", !verify(secret, tampered, signature), "tampered fixture rejected")
	add("B40-LOCAL-UNSIGNED-REJECTION", !verify(secret, artifact, ""), "unsigned fixture rejected")
	add("B40-LOCAL-PROVENANCE-BINDING", validEnvelope(attestation, artifactDigest, "tenant-local-a"), "exact local provenance envelope accepted")
	add("B40-LOCAL-SUBJECT-MISMATCH", !validEnvelope(wrongSubject, artifactDigest, "tenant-local-a"), "wrong subject digest rejected")
	add("B40-LOCAL-RUNNER-DOWNGRADE", !validEnvelope(downgraded, artifactDigest, "tenant-local-a"), "runner-profile downgrade rejected")
	add("B40-LOCAL-TENANT-ISOLATION", !validEnvelope(wrongTenant, artifactDigest, "tenant-local-a"), "cross-tenant evidence rejected")
	add("B40-LOCAL-CORPUS-SEPARATION", disjoint(development, holdout, representative) && !disjoint(development, holdout, overlap), "three local fixture corpora are disjoint and overlap is rejected")
	add("B40-LOCAL-NONROOT", os.Geteuid() != 0 && os.Getegid() != 0, fmt.Sprintf("effective uid=%d gid=%d", os.Geteuid(), os.Getegid()))
	writeErr := os.WriteFile("/b40-rootfs-write-probe", []byte("must-fail"), 0o600)
	add("B40-LOCAL-READONLY-ROOTFS", writeErr != nil, "write to container root filesystem rejected")

	failed := []string{}
	for _, item := range controls {
		if item.Status != "PASS" {
			failed = append(failed, item.ControlID)
		}
	}
	status := "PASS"
	if len(failed) > 0 {
		status = "BLOCKED"
	}
	report := probeReport{
		SchemaVersion: 1,
		ProbeVersion:  1,
		Status:        status,
		Runtime: map[string]any{
			"effectiveUid":                os.Geteuid(),
			"effectiveGid":                os.Getegid(),
			"rootFilesystemWriteRejected": writeErr != nil,
		},
		Controls:       controls,
		FailedControls: failed,
		Corpora: map[string][]string{
			"development":    development,
			"holdout":        holdout,
			"representative": representative,
		},
		IndependentVerification: "NOT_RUN",
		CertificationStatus:     "NOT_CERTIFIED",
	}
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(report); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	if status != "PASS" {
		os.Exit(2)
	}
}
