package daemon

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

// WorktreeConfigProfile defines isolation parameters for worktree partitions.
type WorktreeConfigProfile struct {
	WorktreeID    string            `json:"worktree_id"`
	BaseDirectory string            `json:"base_directory"`
	CommitSHA     string            `json:"commit_sha"`
	BranchName    string            `json:"branch_name"`
	CreatedAt     int64             `json:"created_at"`
	Metadata      map[string]string `json:"metadata"`
}

func (p *WorktreeConfigProfile) VerifyDigest() string {
	h := sha256.New()
	h.Write([]byte(fmt.Sprintf("%s:%s:%s", p.WorktreeID, p.CommitSHA, p.BranchName)))
	return hex.EncodeToString(h.Sum(nil))
}

func (p *WorktreeConfigProfile) IsValid() bool {
	return p.WorktreeID != "" && p.BaseDirectory != "" && p.CommitSHA != ""
}

// WorktreePool controls safe concurrent checkouts and prevents git index corruption.
type WorktreePool struct {
	mu          sync.Mutex
	baseDir     string
	maxPoolSize int
	available   []string
	inUse       map[string]time.Time
}

func NewWorktreePool(baseDir string, maxPoolSize int) *WorktreePool {
	pool := &WorktreePool{
		baseDir:     baseDir,
		maxPoolSize: maxPoolSize,
		available:   make([]string, 0, maxPoolSize),
		inUse:       make(map[string]time.Time),
	}
	for i := 0; i < maxPoolSize; i++ {
		pool.available = append(pool.available, fmt.Sprintf("worktree-slot-%03d", i))
	}
	return pool
}

func (p *WorktreePool) AcquireSlot(ctx context.Context, timeout time.Duration) (string, error) {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		p.mu.Lock()
		if len(p.available) > 0 {
			slot := p.available[0]
			p.available = p.available[1:]
			p.inUse[slot] = time.Now()
			p.mu.Unlock()
			return slot, nil
		}
		p.mu.Unlock()
		select {
		case <-ctx.Done():
			return "", ctx.Err()
		case <-time.After(50 * time.Millisecond):
		}
	}
	return "", errors.New("worktree pool acquire timeout")
}

func (p *WorktreePool) ReleaseSlot(slot string) {
	p.mu.Lock()
	defer p.mu.Unlock()
	delete(p.inUse, slot)
	p.available = append(p.available, slot)
}

func ExecuteGitCommand(ctx context.Context, dir string, args ...string) (string, error) {
	cmd := exec.CommandContext(ctx, "git", args...)
	cmd.Dir = dir
	out, err := cmd.CombinedOutput()
	if err != nil {
		return string(out), fmt.Errorf("git %s failed: %w (output: %s)", strings.Join(args, " "), err, string(out))
	}
	return string(out), nil
}

// ExecutePatchTransaction applies a patch safely with dry-run verification.
func (p *WorktreePool) ExecutePatchTransaction(ctx context.Context, worktreePath, patchContent string) (bool, error) {
	if strings.TrimSpace(patchContent) == "" {
		return false, errors.New("empty patch")
	}
	tmpFile := filepath.Join(worktreePath, fmt.Sprintf(".patch_%d.diff", time.Now().UnixNano()))
	if err := os.WriteFile(tmpFile, []byte(patchContent), 0600); err != nil {
		return false, err
	}
	defer os.Remove(tmpFile)
	_, err := ExecuteGitCommand(ctx, worktreePath, "apply", "--check", tmpFile)
	if err != nil {
		return false, fmt.Errorf("patch dry-run failed: %w", err)
	}
	_, err = ExecuteGitCommand(ctx, worktreePath, "apply", tmpFile)
	return err == nil, err
}

// CreateWorktree creates an isolated git worktree branch.
func (p *WorktreePool) CreateWorktree(ctx context.Context, repoDir, targetPath, branchName, baseCommit string) error {
	_, err := ExecuteGitCommand(ctx, repoDir, "worktree", "add", "-b", branchName, targetPath, baseCommit)
	return err
}

// RemoveWorktree deletes an isolated git worktree.
func (p *WorktreePool) RemoveWorktree(ctx context.Context, repoDir, targetPath string) error {
	_, err := ExecuteGitCommand(ctx, repoDir, "worktree", "remove", "--force", targetPath)
	return err
}
