package daemon

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"sync"
)

// Concurrent Cryptographic Merkle Tree calculation and verification receipts.

type MerkleLeafSnapshot struct {
	RelativePath string `json:"relative_path"`
	FileSize     int64  `json:"file_size"`
	FileMode     uint32 `json:"file_mode"`
	SHA256Hash   string `json:"sha256_hash"`
	Timestamp    int64  `json:"timestamp"`
}

func (m *MerkleLeafSnapshot) Validate() error {
	if m.RelativePath == "" {
		return fmt.Errorf("relative_path cannot be empty")
	}
	if len(m.SHA256Hash) != 64 {
		return fmt.Errorf("invalid sha256 hash length: %d", len(m.SHA256Hash))
	}
	return nil
}

// MerkleTreeBuilder computes deterministic root digests across file hierarchies.
type MerkleTreeBuilder struct {
	mu sync.Mutex
}

func NewMerkleTreeBuilder() *MerkleTreeBuilder {
	return &MerkleTreeBuilder{}
}

func (b *MerkleTreeBuilder) HashFile(filePath string) (string, error) {
	f, err := os.Open(filePath)
	if err != nil {
		return "", err
	}
	defer f.Close()
	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}

func (b *MerkleTreeBuilder) ComputeDirectoryRoot(rootPath string) (string, int, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	var leafHashes []string
	err := filepath.Walk(rootPath, func(p string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if info.IsDir() {
			if info.Name() == ".git" || info.Name() == ".venv" || info.Name() == "node_modules" {
				return filepath.SkipDir
			}
			return nil
		}
		hash, hErr := b.HashFile(p)
		if hErr != nil {
			return hErr
		}
		rel, _ := filepath.Rel(rootPath, p)
		leafHashes = append(leafHashes, fmt.Sprintf("%s:%s", rel, hash))
		return nil
	})
	if err != nil {
		return "", 0, err
	}
	if len(leafHashes) == 0 {
		return "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", 0, nil
	}
	sort.Strings(leafHashes)
	h := sha256.New()
	for _, lh := range leafHashes {
		h.Write([]byte(lh))
		h.Write([]byte("\n"))
	}
	return hex.EncodeToString(h.Sum(nil)), len(leafHashes), nil
}

// MerkleDirectoryAuditor computes and audits directory integrity against tamper.
type MerkleDirectoryAuditor struct {
	builder *MerkleTreeBuilder
}

func NewMerkleDirectoryAuditor() *MerkleDirectoryAuditor {
	return &MerkleDirectoryAuditor{
		builder: NewMerkleTreeBuilder(),
	}
}

func (a *MerkleDirectoryAuditor) ComputeDirectoryMerkleRoot(dir string) (string, map[string]string, error) {
	digests := make(map[string]string)
	err := filepath.Walk(dir, func(p string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if info.IsDir() {
			if info.Name() == ".git" || info.Name() == ".venv" || info.Name() == "node_modules" {
				return filepath.SkipDir
			}
			return nil
		}
		h, err := a.builder.HashFile(p)
		if err != nil {
			return err
		}
		rel, _ := filepath.Rel(dir, p)
		digests[rel] = h
		return nil
	})
	if err != nil {
		return "", nil, err
	}
	root, _, err := a.builder.ComputeDirectoryRoot(dir)
	if err != nil {
		return "", nil, err
	}
	return root, digests, nil
}

func (a *MerkleDirectoryAuditor) VerifyTamper(dir string, expectedRoot string) (bool, error) {
	currentRoot, _, err := a.builder.ComputeDirectoryRoot(dir)
	if err != nil {
		return false, err
	}
	return currentRoot == expectedRoot, nil
}
