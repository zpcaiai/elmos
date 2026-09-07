package main

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"sort"
	"strings"
)

var (
	allCommands = map[string]bool{
		"preflight":     true,
		"install":       true,
		"status":        true,
		"backup":        true,
		"restore":       true,
		"import-bundle": true,
		"upgrade":       true,
		"verify":        true,
		"diagnostics":   true,
	}

	mutatingCommands = map[string]bool{
		"install":       true,
		"restore":       true,
		"import-bundle": true,
		"upgrade":       true,
	}
)

type commandStatus struct {
	Status     string `json:"status"`
	ReasonCode string `json:"reasonCode"`
}

var commandStatusMap = map[string]commandStatus{
	"preflight":   {Status: "NOT_RUN", ReasonCode: "TARGET_INSTALLATION_REQUIRED"},
	"status":      {Status: "NOT_CONFIGURED", ReasonCode: "INSTALLATION_CONTEXT_REQUIRED"},
	"verify":      {Status: "NOT_RUN", ReasonCode: "RELEASE_BUNDLE_OR_INSTALLATION_REQUIRED"},
	"diagnostics": {Status: "NOT_RUN", ReasonCode: "REDACTED_DIAGNOSTIC_TARGET_REQUIRED"},
	"backup":      {Status: "BLOCKED", ReasonCode: "BACKUP_TARGET_AND_KEY_REQUIRED"},
}

type unknownCommandResponse struct {
	Status     string   `json:"status"`
	ReasonCode string   `json:"reasonCode"`
	Commands   []string `json:"commands"`
}

type blockedCommandResponse struct {
	Command    string `json:"command"`
	Status     string `json:"status"`
	ReasonCode string `json:"reasonCode"`
}

type successCommandResponse struct {
	Command    string `json:"command"`
	Status     string `json:"status"`
	ReasonCode string `json:"reasonCode"`
}

// Run executes the CLI with the provided arguments and returns an exit code.
// Exit code conventions match io.elmos.cli.ElmosCtl:
// - 0: Accepted / success
// - 2: Unknown command or missing command
// - 3: Mutating command blocked (missing --evidence-approved or --confirm)
// - 4: Command not run, not configured, or blocked
func Run(args []string, stdout io.Writer, stderr io.Writer) int {
	if len(args) == 0 || !allCommands[args[0]] {
		var cmds []string
		for cmd := range allCommands {
			cmds = append(cmds, cmd)
		}
		sort.Strings(cmds)

		resp := unknownCommandResponse{
			Status:     "REJECTED",
			ReasonCode: "UNKNOWN_COMMAND",
			Commands:   cmds,
		}
		payload, _ := json.Marshal(resp)
		fmt.Fprintln(stderr, string(payload))
		return 2
	}

	command := args[0]
	var evidenceFlag, confirmation bool
	for _, arg := range args[1:] {
		if arg == "--evidence-approved" {
			evidenceFlag = true
		} else if arg == "--confirm" {
			confirmation = true
		}
	}

	if mutatingCommands[command] && (!evidenceFlag || !confirmation) {
		resp := blockedCommandResponse{
			Command:    command,
			Status:     "BLOCKED",
			ReasonCode: "APPROVED_EVIDENCE_AND_CONFIRMATION_REQUIRED",
		}
		payload, _ := json.Marshal(resp)
		fmt.Fprintln(stderr, string(payload))
		return 3
	}

	st, ok := commandStatusMap[command]
	if !ok {
		st = commandStatus{
			Status:     "ACCEPTED_FOR_EXTERNAL_EXECUTION",
			ReasonCode: "RUN_IN_APPROVED_PRIVATE_ENVIRONMENT",
		}
	}

	resp := successCommandResponse{
		Command:    command,
		Status:     st.Status,
		ReasonCode: st.ReasonCode,
	}
	payload, _ := json.Marshal(resp)
	fmt.Fprintln(stdout, string(payload))

	if strings.HasPrefix(st.Status, "ACCEPTED") {
		return 0
	}
	return 4
}

func main() {
	os.Exit(Run(os.Args[1:], os.Stdout, os.Stderr))
}
