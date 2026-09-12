package test

import (
	"strings"
	"testing"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/service"
)

func TestNachaAbaRoutingNumberValidation(t *testing.T) {
	// Chase NY routing: 021000021
	if !service.ValidateAbaRoutingNumber("021000021") {
		t.Fatalf("Expected valid ABA 021000021 to pass Luhn/Fedwire modulo-10")
	}

	// Bank of America NC routing: 053000196
	if !service.ValidateAbaRoutingNumber("053000196") {
		t.Fatalf("Expected valid ABA 053000196 to pass")
	}

	// Wells Fargo CA routing: 121000248
	if !service.ValidateAbaRoutingNumber("121000248") {
		t.Fatalf("Expected valid ABA 121000248 to pass")
	}

	// Corrupted ABA
	if service.ValidateAbaRoutingNumber("021000022") {
		t.Fatalf("Corrupted ABA 021000022 should fail check digit test")
	}
}

func TestNachaACHFileGenerationAndParsingRoundtrip(t *testing.T) {
	processor := service.NewNachaACHProcessor()

	file := &service.ACHFile{
		ImmediateDestination: " 021000021",
		ImmediateOrigin:      "1234567890",
		CreationTime:         time.Now().UTC(),
		FileIDModifier:       "A",
		ImmediateDestName:    "JPMORGAN CHASE BANK",
		ImmediateOriginName:  "ACME CORP PAYROLL",
		ReferenceCode:        "REF001",
		Batches: []service.ACHBatch{
			{
				ServiceClassCode:       service.ServiceClassCredits,
				CompanyName:            "ACME CORP",
				CompanyDiscretion:      "BIWEEKLY SALARY",
				CompanyID:              "1234567890",
				StandardEntryClass:     service.SecPPD,
				EntryDescription:       "PAYROLL",
				CompanyDescriptiveDate: "260910",
				EffectiveEntryDate:     time.Now().UTC().Add(24 * time.Hour),
				OriginatingDfiID:       "02100002",
				BatchNumber:            1,
				Entries: []service.ACHEntryDetail{
					{
						TransactionCode:     service.TxDemandCredit,
						ReceivingDfiRouting: "05300019",
						CheckDigit:          "6",
						DfiAccountNumber:    "9876543210",
						AmountCents:         350000, // $3,500.00
						IndividualID:        "EMP-001",
						IndividualName:      "ALICE SMITH",
						DiscretionaryData:   "S1",
						TraceNumber:         "021000020000001",
						AddendaInformation:  "DIRECT DEPOSIT SALARY FOR SEP 2026",
					},
					{
						TransactionCode:     service.TxDemandCredit,
						ReceivingDfiRouting: "12100024",
						CheckDigit:          "8",
						DfiAccountNumber:    "1122334455",
						AmountCents:         420000, // $4,200.00
						IndividualID:        "EMP-002",
						IndividualName:      "BOB JOHNSON",
						DiscretionaryData:   "S2",
						TraceNumber:         "021000020000002",
					},
				},
			},
		},
	}

	nachaText, err := processor.GenerateACHFile(file)
	if err != nil {
		t.Fatalf("Failed to generate NACHA file: %v", err)
	}

	lines := strings.Split(strings.TrimRight(nachaText, "\n"), "\n")
	if len(lines)%10 != 0 {
		t.Fatalf("NACHA file total lines (%d) must be blocked to a multiple of 10", len(lines))
	}

	for i, l := range lines {
		if len(l) != 94 {
			t.Fatalf("Line %d has length %d, expected strictly 94 characters", i+1, len(l))
		}
	}

	// Parse back
	parsed, err := processor.ParseACHFile(strings.NewReader(nachaText))
	if err != nil {
		t.Fatalf("Failed to parse generated NACHA file: %v", err)
	}

	if len(parsed.Batches) != 1 {
		t.Fatalf("Expected 1 batch, got: %d", len(parsed.Batches))
	}

	batch := parsed.Batches[0]
	if len(batch.Entries) != 2 {
		t.Fatalf("Expected 2 entries, got: %d", len(batch.Entries))
	}

	if batch.Entries[0].AmountCents != 350000 || batch.Entries[1].AmountCents != 420000 {
		t.Fatalf("Entry amounts corrupted in roundtrip")
	}

	if batch.Entries[0].AddendaInformation != "DIRECT DEPOSIT SALARY FOR SEP 2026" {
		t.Fatalf("Addenda text corrupted: got '%s'", batch.Entries[0].AddendaInformation)
	}
}
