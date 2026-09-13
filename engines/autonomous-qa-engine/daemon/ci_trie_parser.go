package daemon

import (
	"bufio"
	"errors"
	"fmt"
	"io"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
)

// Streaming Aho-Corasick & Trie failure pattern extractor for CI logs.

type FailureKind string

const (
	FailureAssertionError FailureKind = "AssertionError"
	FailurePanic          FailureKind = "Panic"
	FailureTimeout        FailureKind = "Timeout"
	FailureBuildError     FailureKind = "BuildError"
)

type LogMatch struct {
	Kind       FailureKind
	LineNumber int
	Snippet    string
	Pattern    string
}

type FailureDiagnosisRecord struct {
	DiagnosticID  string   `json:"diagnostic_id"`
	TestFramework string   `json:"test_framework"`
	SuiteName     string   `json:"suite_name"`
	TestCase      string   `json:"test_case"`
	FailureReason string   `json:"failure_reason"`
	SourceFile    string   `json:"source_file"`
	LineNumber    int      `json:"line_number"`
	Severity      string   `json:"severity"`
	StackTrace    []string `json:"stack_trace"`
}

type TrieNode struct {
	children map[rune]*TrieNode
	fail     *TrieNode
	output   []string
	isEnd    bool
}

func NewTrieNode() *TrieNode {
	return &TrieNode{
		children: make(map[rune]*TrieNode),
		output:   []string{},
	}
}

type AhoCorasickAutomaton struct {
	root *TrieNode
	mu   sync.RWMutex
}

func NewAhoCorasickAutomaton(patterns []string) *AhoCorasickAutomaton {
	ac := &AhoCorasickAutomaton{root: NewTrieNode()}
	for _, p := range patterns {
		ac.AddPattern(p)
	}
	ac.BuildFailureTransitions()
	return ac
}

func (a *AhoCorasickAutomaton) AddPattern(pattern string) {
	curr := a.root
	for _, ch := range pattern {
		if _, exists := curr.children[ch]; !exists {
			curr.children[ch] = NewTrieNode()
		}
		curr = curr.children[ch]
	}
	curr.isEnd = true
	curr.output = append(curr.output, pattern)
}

func (a *AhoCorasickAutomaton) BuildFailureTransitions() {
	queue := []*TrieNode{}
	for _, child := range a.root.children {
		child.fail = a.root
		queue = append(queue, child)
	}
	for len(queue) > 0 {
		curr := queue[0]
		queue = queue[1:]
		for ch, child := range curr.children {
			failNode := curr.fail
			for failNode != nil && failNode.children[ch] == nil {
				failNode = failNode.fail
			}
			if failNode == nil {
				child.fail = a.root
			} else {
				child.fail = failNode.children[ch]
			}
			if child.fail != nil {
				child.output = append(child.output, child.fail.output...)
			}
			queue = append(queue, child)
		}
	}
}

func (a *AhoCorasickAutomaton) ScanStream(r io.Reader) (map[string][]int, error) {
	matches := make(map[string][]int)
	scanner := bufio.NewScanner(r)
	lineNum := 1
	for scanner.Scan() {
		line := scanner.Text()
		curr := a.root
		for _, ch := range line {
			for curr != nil && curr.children[ch] == nil {
				curr = curr.fail
			}
			if curr == nil {
				curr = a.root
				continue
			}
			curr = curr.children[ch]
			if len(curr.output) > 0 {
				for _, pat := range curr.output {
					matches[pat] = append(matches[pat], lineNum)
				}
			}
		}
		lineNum++
	}
	return matches, scanner.Err()
}

type AhoCorasickLogParser struct {
	automaton *AhoCorasickAutomaton
}

func NewAhoCorasickLogParser() *AhoCorasickLogParser {
	patterns := []string{"AssertionError", "panic", "Timeout", "BuildError", "FAILED", "ERROR"}
	return &AhoCorasickLogParser{
		automaton: NewAhoCorasickAutomaton(patterns),
	}
}

func (p *AhoCorasickLogParser) ParseLog(logBytes []byte, maxMatches int) []LogMatch {
	lines := strings.Split(string(logBytes), "\n")



	var matches []LogMatch
	for idx, line := range lines {
		lineNum := idx + 1
		lower := strings.ToLower(line)
		if strings.Contains(line, "AssertionError") {
			matches = append(matches, LogMatch{
				Kind:       FailureAssertionError,
				LineNumber: lineNum,
				Snippet:    line,
				Pattern:    "AssertionError",
			})
		} else if strings.Contains(lower, "panic:") || strings.Contains(lower, "panic(") || strings.HasPrefix(lower, "panic") {
			matches = append(matches, LogMatch{
				Kind:       FailurePanic,
				LineNumber: lineNum,
				Snippet:    line,
				Pattern:    "panic",
			})
		}
		if maxMatches > 0 && len(matches) >= maxMatches {
			break
		}
	}
	return matches
}

// ParsePytestDiagnosticBlock parses Python traceback blocks.
func ParsePytestDiagnosticBlock(block string) (*FailureDiagnosisRecord, error) {
	if !strings.Contains(block, "FAILED") && !strings.Contains(block, "ERROR") {
		return nil, errors.New("no failure token in block")
	}
	re := regexp.MustCompile(`([a-zA-Z0-9_/\.-]+\.py):(\d+):\s*(.*)`)
	m := re.FindStringSubmatch(block)
	line := 0
	file := "unknown.py"
	reason := "AssertionError"
	if len(m) >= 4 {
		file = m[1]
		line, _ = strconv.Atoi(m[2])
		reason = m[3]
	}
	return &FailureDiagnosisRecord{
		DiagnosticID:  fmt.Sprintf("PYTEST-%s-%d", filepath.Base(file), line),
		TestFramework: "pytest",
		SourceFile:    file,
		LineNumber:    line,
		FailureReason: reason,
		StackTrace:    strings.Split(block, "\n"),
	}, nil
}
