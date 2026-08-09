package client

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/acme/migration-platform/runner/internal/protocol"
)

type Client struct {
	baseURL string
	http    *http.Client
}

func New(baseURL string) *Client {
	return &Client{
		baseURL: strings.TrimRight(baseURL, "/"),
		http:    &http.Client{Timeout: 15 * time.Second},
	}
}

func (c *Client) Register(ctx context.Context, request protocol.RegisterRequest) (protocol.RegisterResponse, error) {
	var response protocol.RegisterResponse
	err := c.doJSON(ctx, http.MethodPost, "/internal/v1/runners/register", request, &response)
	return response, err
}

func (c *Client) Heartbeat(ctx context.Context, runnerID string) error {
	return c.doJSON(ctx, http.MethodPost, "/internal/v1/runners/"+runnerID+"/heartbeat",
		protocol.HeartbeatRequest{Status: "online"}, nil)
}

func (c *Client) Claim(ctx context.Context, runnerID string) (*protocol.ClaimJobResponse, error) {
	body, status, err := c.do(ctx, http.MethodPost, "/internal/v1/runners/"+runnerID+"/claim", nil)
	if err != nil {
		return nil, err
	}
	if status == http.StatusNoContent {
		return nil, nil
	}
	if status < 200 || status >= 300 {
		return nil, fmt.Errorf("claim failed with status %d: %s", status, body)
	}
	var response protocol.ClaimJobResponse
	if err := json.Unmarshal(body, &response); err != nil {
		return nil, fmt.Errorf("decode claim response: %w", err)
	}
	return &response, nil
}

func (c *Client) Complete(ctx context.Context, jobID string, request protocol.CompleteJobRequest) error {
	return c.doJSON(ctx, http.MethodPost, "/internal/v1/jobs/"+jobID+"/complete", request, nil)
}

func (c *Client) doJSON(ctx context.Context, method, path string, input any, output any) error {
	var payload []byte
	var err error
	if input != nil {
		payload, err = json.Marshal(input)
		if err != nil {
			return fmt.Errorf("encode request: %w", err)
		}
	}
	body, status, err := c.do(ctx, method, path, payload)
	if err != nil {
		return err
	}
	if status < 200 || status >= 300 {
		return fmt.Errorf("request failed with status %d: %s", status, body)
	}
	if output != nil && len(body) > 0 {
		if err := json.Unmarshal(body, output); err != nil {
			return fmt.Errorf("decode response: %w", err)
		}
	}
	return nil
}

func (c *Client) do(ctx context.Context, method, path string, payload []byte) ([]byte, int, error) {
	var reader io.Reader
	if payload != nil {
		reader = bytes.NewReader(payload)
	}
	req, err := http.NewRequestWithContext(ctx, method, c.baseURL+path, reader)
	if err != nil {
		return nil, 0, err
	}
	if payload != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	response, err := c.http.Do(req)
	if err != nil {
		return nil, 0, err
	}
	defer response.Body.Close()
	body, err := io.ReadAll(io.LimitReader(response.Body, 4<<20))
	if err != nil {
		return nil, 0, err
	}
	return body, response.StatusCode, nil
}

var ErrUnsupportedJob = errors.New("unsupported job type")
