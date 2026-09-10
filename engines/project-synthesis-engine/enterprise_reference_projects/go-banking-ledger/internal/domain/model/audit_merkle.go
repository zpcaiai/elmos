package model

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
)

// ProofDirection represents whether the companion proof node is on the left or right.
type ProofDirection string

const (
	ProofLeft  ProofDirection = "LEFT"
	ProofRight ProofDirection = "RIGHT"
)

// AuditNode represents an intermediate or leaf node in the Merkle audit tree.
type AuditNode struct {
	Hash   []byte
	Left   *AuditNode
	Right  *AuditNode
	IsLeaf bool
	Index  int
}

// AuditProof contains the cryptographic path necessary to prove leaf membership in a Merkle root.
type AuditProof struct {
	LeafIndex   int              `json:"leaf_index"`
	TargetHash  string           `json:"target_hash"`
	RootHash    string           `json:"root_hash"`
	ProofSteps  []ProofStep      `json:"proof_steps"`
}

// ProofStep holds a single sibling hash and its relative position.
type ProofStep struct {
	SiblingHash string         `json:"sibling_hash"`
	Direction   ProofDirection `json:"direction"`
}

// MerkleAuditTree builds an immutable binary audit tree over a sequence of hashes.
type MerkleAuditTree struct {
	Leaves []*AuditNode
	Root   *AuditNode
}

// BuildMerkleTree constructs a Merkle tree from a slice of hex-encoded hashes.
func BuildMerkleTree(leafHexHashes []string) (*MerkleAuditTree, error) {
	if len(leafHexHashes) == 0 {
		return nil, errors.New("cannot build merkle tree with zero leaves")
	}

	var currentLevel []*AuditNode
	for idx, h := range leafHexHashes {
		decoded, err := hex.DecodeString(h)
		if err != nil {
			return nil, fmt.Errorf("invalid leaf hash at index %d: %w", idx, err)
		}
		currentLevel = append(currentLevel, &AuditNode{
			Hash:   decoded,
			IsLeaf: true,
			Index:  idx,
		})
	}

	leaves := make([]*AuditNode, len(currentLevel))
	copy(leaves, currentLevel)

	for len(currentLevel) > 1 {
		var nextLevel []*AuditNode
		for i := 0; i < len(currentLevel); i += 2 {
			if i+1 < len(currentLevel) {
				left := currentLevel[i]
				right := currentLevel[i+1]
				parentHash := hashChildren(left.Hash, right.Hash)
				nextLevel = append(nextLevel, &AuditNode{
					Hash:  parentHash,
					Left:  left,
					Right: right,
				})
			} else {
				// Odd count: duplicate the last leaf
				left := currentLevel[i]
				parentHash := hashChildren(left.Hash, left.Hash)
				nextLevel = append(nextLevel, &AuditNode{
					Hash:  parentHash,
					Left:  left,
					Right: left,
				})
			}
		}
		currentLevel = nextLevel
	}

	return &MerkleAuditTree{
		Leaves: leaves,
		Root:   currentLevel[0],
	}, nil
}

func hashChildren(left, right []byte) []byte {
	combined := append(left, right...)
	h := sha256.Sum256(combined)
	return h[:]
}

// RootHex returns the hex-encoded string of the root hash.
func (m *MerkleAuditTree) RootHex() string {
	if m == nil || m.Root == nil {
		return ""
	}
	return hex.EncodeToString(m.Root.Hash)
}

// GenerateProof creates a cryptographically verifiable inclusion proof for a leaf at index.
func (m *MerkleAuditTree) GenerateProof(leafIndex int) (*AuditProof, error) {
	if leafIndex < 0 || leafIndex >= len(m.Leaves) {
		return nil, errors.New("leaf index out of bounds")
	}

	var steps []ProofStep
	targetNode := m.Leaves[leafIndex]
	targetHex := hex.EncodeToString(targetNode.Hash)

	// Traverse upwards by re-building sibling path
	currentLevel := m.Leaves
	currentIndex := leafIndex

	for len(currentLevel) > 1 {
		var nextLevel []*AuditNode
		var siblingIndex int
		var dir ProofDirection

		if currentIndex%2 == 0 {
			siblingIndex = currentIndex + 1
			dir = ProofRight
		} else {
			siblingIndex = currentIndex - 1
			dir = ProofLeft
		}

		var siblingHash []byte
		if siblingIndex < len(currentLevel) {
			siblingHash = currentLevel[siblingIndex].Hash
		} else {
			// Duplicated node for odd element
			siblingHash = currentLevel[currentIndex].Hash
		}

		steps = append(steps, ProofStep{
			SiblingHash: hex.EncodeToString(siblingHash),
			Direction:   dir,
		})

		// Roll up to next level
		for i := 0; i < len(currentLevel); i += 2 {
			if i+1 < len(currentLevel) {
				parentHash := hashChildren(currentLevel[i].Hash, currentLevel[i+1].Hash)
				nextLevel = append(nextLevel, &AuditNode{Hash: parentHash})
			} else {
				parentHash := hashChildren(currentLevel[i].Hash, currentLevel[i].Hash)
				nextLevel = append(nextLevel, &AuditNode{Hash: parentHash})
			}
		}

		currentIndex = currentIndex / 2
		currentLevel = nextLevel
	}

	return &AuditProof{
		LeafIndex:   leafIndex,
		TargetHash:  targetHex,
		RootHash:    m.RootHex(),
		ProofSteps:  steps,
	}, nil
}

// VerifyProof verifies that targetHash belongs to the Merkle tree with rootHash using proof steps.
func VerifyProof(proof *AuditProof) bool {
	if proof == nil || len(proof.ProofSteps) == 0 {
		return false
	}

	currentHash, err := hex.DecodeString(proof.TargetHash)
	if err != nil {
		return false
	}

	for _, step := range proof.ProofSteps {
		siblingHash, err := hex.DecodeString(step.SiblingHash)
		if err != nil {
			return false
		}

		if step.Direction == ProofRight {
			currentHash = hashChildren(currentHash, siblingHash)
		} else {
			currentHash = hashChildren(siblingHash, currentHash)
		}
	}

	expectedRoot, err := hex.DecodeString(proof.RootHash)
	if err != nil {
		return false
	}

	return bytes.Equal(currentHash, expectedRoot)
}
