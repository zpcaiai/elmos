package protocol

import "time"

type RegisterRequest struct {
	Name         string   `json:"name"`
	Version      string   `json:"version"`
	Capabilities []string `json:"capabilities"`
}

type RegisterResponse struct {
	RunnerID string `json:"runnerId"`
	Status   string `json:"status"`
}

type HeartbeatRequest struct {
	Status string `json:"status"`
}

type ClaimJobResponse struct {
	JobID          string    `json:"jobId"`
	JobType        string    `json:"jobType"`
	Payload        string    `json:"payload"`
	LeaseExpiresAt time.Time `json:"leaseExpiresAt"`
	CommitToken    string    `json:"commitToken"`
}

type CompleteJobRequest struct {
	CommitToken   string `json:"commitToken"`
	Status        string `json:"status"`
	OutputPayload string `json:"outputPayload"`
	ArtifactPath  string `json:"artifactPath"`
}
