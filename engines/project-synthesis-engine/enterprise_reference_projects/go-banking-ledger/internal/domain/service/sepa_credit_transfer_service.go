package service

import (
	"errors"
	"fmt"
	"math/big"
	"regexp"
	"strings"
	"time"
)

type SEPASchemeType string

const (
	SchemeSCTStandard SEPASchemeType = "SCT_STANDARD" // Next-business-day execution
	SchemeSCTInstant  SEPASchemeType = "SCT_INSTANT"  // 10-second execution SLA
)

type SEPAReasonCode string

const (
	ReasonAC01 SEPAReasonCode = "AC01" // Incorrect IBAN or account number
	ReasonAC04 SEPAReasonCode = "AC04" // Account closed
	ReasonAC06 SEPAReasonCode = "AC06" // Blocked account
	ReasonAM04 SEPAReasonCode = "AM04" // Insufficient funds
	ReasonAB03 SEPAReasonCode = "AB03" // Settlement timeout (Instant 10s breached)
	ReasonMS03 SEPAReasonCode = "MS03" // Reason not specified
)

var (
	ErrInvalidIbanFormat   = errors.New("invalid IBAN syntax or length")
	ErrIbanChecksumFailed  = errors.New("IBAN modulo-97 checksum validation failed")
	ErrInvalidBicFormat    = errors.New("invalid BIC/SWIFT code syntax (must be 8 or 11 alphanumeric)")
	ErrNonEuroCurrency     = errors.New("SEPA transactions require EUR currency")
	ErrInstantAmountLimit  = errors.New("SCT Instant amount exceeds regulatory €100,000 threshold")
	ErrInstantSlaBreached  = errors.New("SCT Instant execution SLA 10-second deadline exceeded")
)

var (
	ibanRegex = regexp.MustCompile(`^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$`)
	bicRegex  = regexp.MustCompile(`^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$`)
)

// ValidateIBAN verifies ISO 13616 IBAN Modulo-97 algorithm
func ValidateIBAN(iban string) error {
	clean := strings.ToUpper(strings.ReplaceAll(iban, " ", ""))
	if !ibanRegex.MatchString(clean) {
		return ErrInvalidIbanFormat
	}

	// Move first 4 characters to the end
	rearranged := clean[4:] + clean[:4]

	// Convert letters A-Z to digits 10-35
	var sb strings.Builder
	for _, ch := range rearranged {
		if ch >= 'A' && ch <= 'Z' {
			sb.WriteString(fmt.Sprintf("%d", int(ch-'A')+10))
		} else {
			sb.WriteRune(ch)
		}
	}

	// Calculate Modulo 97 using arbitrary-precision integer
	n := new(big.Int)
	n.SetString(sb.String(), 10)

	rem := new(big.Int)
	rem.Mod(n, big.NewInt(97))

	if rem.Int64() != 1 {
		return ErrIbanChecksumFailed
	}
	return nil
}

// ValidateBIC verifies ISO 9362 BIC code
func ValidateBIC(bic string) error {
	clean := strings.ToUpper(strings.TrimSpace(bic))
	if !bicRegex.MatchString(clean) {
		return ErrInvalidBicFormat
	}
	return nil
}

type SEPACreditTransferInstruction struct {
	InstructionID       string
	EndToEndID          string
	SchemeType          SEPASchemeType
	AmountCentsEUR      int64 // In Euro cents (e.g. €500.00 = 50000)
	DebtorName          string
	DebtorIBAN          string
	DebtorBIC           string
	CreditorName        string
	CreditorIBAN        string
	CreditorBIC         string
	RemittanceInfo      string // Max 140 chars unstructured remittance
	PurposeCode         string // e.g. "SALA", "TAXS", "INTE"
	InitiationTimestamp time.Time
}

type SEPACreditTransferExecutionResult struct {
	InstructionID       string
	SettlementStatus    string // "SETTLED", "REJECTED", "RETURNED"
	ClearingNetworkRef  string
	ExecutionDurationMs int64
	SettledTimestamp    time.Time
	ReasonCode          SEPAReasonCode
	ErrorMessage        string
}

type SEPACreditTransferService struct {
	maxInstantAmountCents int64
	instantSlaTimeout     time.Duration
}

func NewSEPACreditTransferService() *SEPACreditTransferService {
	return &SEPACreditTransferService{
		maxInstantAmountCents: 10000000, // €100,000.00 max for SEPA Instant
		instantSlaTimeout:     10 * time.Second,
	}
}

// ExecuteCreditTransfer processes SCT or SCT Instant payment instruction
func (s *SEPACreditTransferService) ExecuteCreditTransfer(
	instr SEPACreditTransferInstruction,
) (*SEPACreditTransferExecutionResult, error) {
	start := time.Now()

	// 1. Validate Debtor & Creditor IBANs
	if err := ValidateIBAN(instr.DebtorIBAN); err != nil {
		return &SEPACreditTransferExecutionResult{
			InstructionID:    instr.InstructionID,
			SettlementStatus: "REJECTED",
			ReasonCode:       ReasonAC01,
			ErrorMessage:     fmt.Sprintf("Debtor IBAN invalid: %v", err),
		}, err
	}
	if err := ValidateIBAN(instr.CreditorIBAN); err != nil {
		return &SEPACreditTransferExecutionResult{
			InstructionID:    instr.InstructionID,
			SettlementStatus: "REJECTED",
			ReasonCode:       ReasonAC01,
			ErrorMessage:     fmt.Sprintf("Creditor IBAN invalid: %v", err),
		}, err
	}

	// 2. Validate BICs
	if err := ValidateBIC(instr.DebtorBIC); err != nil {
		return &SEPACreditTransferExecutionResult{
			InstructionID:    instr.InstructionID,
			SettlementStatus: "REJECTED",
			ReasonCode:       ReasonAC01,
			ErrorMessage:     fmt.Sprintf("Debtor BIC invalid: %v", err),
		}, err
	}
	if err := ValidateBIC(instr.CreditorBIC); err != nil {
		return &SEPACreditTransferExecutionResult{
			InstructionID:    instr.InstructionID,
			SettlementStatus: "REJECTED",
			ReasonCode:       ReasonAC01,
			ErrorMessage:     fmt.Sprintf("Creditor BIC invalid: %v", err),
		}, err
	}

	// 3. SEPA Instant Threshold & SLA Check
	if instr.SchemeType == SchemeSCTInstant {
		if instr.AmountCentsEUR > s.maxInstantAmountCents {
			return &SEPACreditTransferExecutionResult{
				InstructionID:    instr.InstructionID,
				SettlementStatus: "REJECTED",
				ReasonCode:       ReasonAM04,
				ErrorMessage:     ErrInstantAmountLimit.Error(),
			}, ErrInstantAmountLimit
		}

		elapsed := time.Since(instr.InitiationTimestamp)
		if elapsed > s.instantSlaTimeout {
			return &SEPACreditTransferExecutionResult{
				InstructionID:    instr.InstructionID,
				SettlementStatus: "REJECTED",
				ReasonCode:       ReasonAB03,
				ErrorMessage:     ErrInstantSlaBreached.Error(),
			}, ErrInstantSlaBreached
		}
	}

	durationMs := time.Since(start).Milliseconds()

	networkPrefix := "STEP2-EU"
	if instr.SchemeType == SchemeSCTInstant {
		networkPrefix = "TIPS-EU"
	}

	return &SEPACreditTransferExecutionResult{
		InstructionID:       instr.InstructionID,
		SettlementStatus:    "SETTLED",
		ClearingNetworkRef:  fmt.Sprintf("%s-%d-%s", networkPrefix, time.Now().UnixNano(), instr.InstructionID),
		ExecutionDurationMs: durationMs,
		SettledTimestamp:    time.Now().UTC(),
		ReasonCode:          "",
		ErrorMessage:        "",
	}, nil
}
