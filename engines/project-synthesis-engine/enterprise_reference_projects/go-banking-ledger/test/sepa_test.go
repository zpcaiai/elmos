package test

import (
	"strings"
	"testing"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/service"
)

func TestSEPAIbanValidation(t *testing.T) {
	// Valid European IBANs
	validIbans := []string{
		"DE89370400440532013000", // Germany Deutsche Bank
		"FR1420041010050500013M02606", // France BNP Paribas
		"IE29AIBK93115212345678", // Ireland AIB
		"ES9121000418450200051332", // Spain CaixaBank
		"NL91ABNA0417164300", // Netherlands ABN AMRO
	}

	for _, iban := range validIbans {
		if err := service.ValidateIBAN(iban); err != nil {
			t.Errorf("Expected valid IBAN %s to pass, got: %v", iban, err)
		}
	}

	// Space formatting should be supported
	spacedIban := "DE89 3704 0044 0532 0130 00"
	if err := service.ValidateIBAN(spacedIban); err != nil {
		t.Errorf("Expected spaced IBAN to pass, got: %v", err)
	}

	// Corrupted Checksum (changed 89 to 88)
	corrupted := "DE88370400440532013000"
	if err := service.ValidateIBAN(corrupted); err == nil {
		t.Errorf("Expected corrupted IBAN checksum to fail")
	}

	// Invalid length / formatting
	invalidFormat := "DE89"
	if err := service.ValidateIBAN(invalidFormat); err == nil {
		t.Errorf("Expected short IBAN to fail")
	}
}

func TestSEPABicValidation(t *testing.T) {
	validBics := []string{
		"DEUTDEDD",       // 8-char BIC (Deutsche Bank Frankfurt)
		"DEUTDEDDXXX",    // 11-char BIC
		"BNPAFRPP",       // BNP Paribas Paris
		"BNPAFRPPXXX",    // 11-char BNP
		"BOFAUS3N",       // Bank of America
	}

	for _, bic := range validBics {
		if err := service.ValidateBIC(bic); err != nil {
			t.Errorf("Expected valid BIC %s to pass, got: %v", bic, err)
		}
	}

	// Invalid BIC lengths and characters
	invalidBics := []string{
		"DEUT",
		"DEUTDEDDXXXX", // 12 chars
		"DEUT-EDD",     // hyphen invalid
	}

	for _, bic := range invalidBics {
		if err := service.ValidateBIC(bic); err == nil {
			t.Errorf("Expected invalid BIC %s to fail", bic)
		}
	}
}

func TestSEPASCTStandardExecution(t *testing.T) {
	sepaService := service.NewSEPACreditTransferService()

	instr := service.SEPACreditTransferInstruction{
		InstructionID:       "SEPA-SCT-2026-001",
		EndToEndID:          "E2E-EUR-001",
		SchemeType:          service.SchemeSCTStandard,
		AmountCentsEUR:      250000, // €2,500.00
		DebtorName:          "Johann Wolfgang",
		DebtorIBAN:          "DE89370400440532013000",
		DebtorBIC:           "DEUTDEDD",
		CreditorName:        "Pierre Dupont",
		CreditorIBAN:        "FR1420041010050500013M02606",
		CreditorBIC:         "BNPAFRPP",
		RemittanceInfo:      "Invoice 2026-INV-998",
		PurposeCode:         "SALA",
		InitiationTimestamp: time.Now().UTC(),
	}

	res, err := sepaService.ExecuteCreditTransfer(instr)
	if err != nil {
		t.Fatalf("Failed to execute standard SCT: %v", err)
	}

	if res.SettlementStatus != "SETTLED" {
		t.Errorf("Expected settlement status SETTLED, got %s", res.SettlementStatus)
	}
	if !strings.HasPrefix(res.ClearingNetworkRef, "STEP2-") {
		t.Errorf("Expected STEP2 clearing network prefix, got %s", res.ClearingNetworkRef)
	}
}

func TestSEPASCTInstantExecutionAndGuards(t *testing.T) {
	sepaService := service.NewSEPACreditTransferService()

	// 1. Valid SCT Instant within €100,000 threshold
	instantInstr := service.SEPACreditTransferInstruction{
		InstructionID:       "SEPA-INST-2026-002",
		EndToEndID:          "E2E-INST-002",
		SchemeType:          service.SchemeSCTInstant,
		AmountCentsEUR:      1500000, // €15,000.00
		DebtorName:          "Johann Wolfgang",
		DebtorIBAN:          "DE89370400440532013000",
		DebtorBIC:           "DEUTDEDD",
		CreditorName:        "Pierre Dupont",
		CreditorIBAN:        "FR1420041010050500013M02606",
		CreditorBIC:         "BNPAFRPP",
		RemittanceInfo:      "Instant P2P Transfer",
		PurposeCode:         "OTHR",
		InitiationTimestamp: time.Now().UTC(),
	}

	res, err := sepaService.ExecuteCreditTransfer(instantInstr)
	if err != nil {
		t.Fatalf("Failed to execute SCT Instant: %v", err)
	}
	if res.SettlementStatus != "SETTLED" {
		t.Errorf("Expected settlement status SETTLED, got %s", res.SettlementStatus)
	}
	if !strings.HasPrefix(res.ClearingNetworkRef, "TIPS-") && !strings.HasPrefix(res.ClearingNetworkRef, "RT1-") {
		t.Errorf("Expected TIPS or RT1 instant network ref, got %s", res.ClearingNetworkRef)
	}

	// 2. Reject SCT Instant exceeding €100,000 regulatory limit (€100,001 = 10000100 cents)
	excessiveInstr := instantInstr
	excessiveInstr.InstructionID = "SEPA-INST-EXCESSIVE"
	excessiveInstr.AmountCentsEUR = 10000100

	resExcess, errExcess := sepaService.ExecuteCreditTransfer(excessiveInstr)
	if errExcess == nil {
		t.Fatalf("Expected excessive SCT Instant transfer to fail with regulatory threshold error")
	}
	if resExcess.SettlementStatus != "REJECTED" || resExcess.ReasonCode != service.ReasonAM04 {
		t.Errorf("Expected REJECTED with ReasonAM04, got status %s reason %s", resExcess.SettlementStatus, resExcess.ReasonCode)
	}

	// 3. Reject invalid Creditor IBAN
	badIbanInstr := instantInstr
	badIbanInstr.InstructionID = "SEPA-INST-BAD-IBAN"
	badIbanInstr.CreditorIBAN = "FR1420041010050500013M99999" // Corrupted check digit

	resBad, errBad := sepaService.ExecuteCreditTransfer(badIbanInstr)
	if errBad == nil {
		t.Fatalf("Expected invalid creditor IBAN to fail")
	}
	if resBad.SettlementStatus != "REJECTED" || resBad.ReasonCode != service.ReasonAC01 {
		t.Errorf("Expected REJECTED with ReasonAC01 for bad IBAN")
	}
}
