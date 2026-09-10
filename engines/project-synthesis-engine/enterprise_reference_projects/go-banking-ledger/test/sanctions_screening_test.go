package test

import (
	"testing"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/service"
)

func TestSanctionsScreeningCleanPass(t *testing.T) {
	engine := service.NewSanctionsScreeningEngine()

	req := service.ScreeningRequest{
		TransactionID:   "TX-CLEAN-01",
		DebtorName:      "Alice Johnson",
		DebtorCountry:   "US",
		CreditorName:    "Bob Smith Tech Supplies",
		CreditorCountry: "GB",
		RemittanceInfo:  "Invoice 90210 laptop hardware",
	}

	res := engine.ScreenTransaction(req)
	if res.Action != service.ActionPass {
		t.Fatalf("Expected PASS action, got %s", res.Action)
	}
	if len(res.Matches) > 0 {
		t.Fatalf("Expected 0 matches, got %d", len(res.Matches))
	}
}

func TestSanctionsScreeningEmbargoedCountry(t *testing.T) {
	engine := service.NewSanctionsScreeningEngine()

	req := service.ScreeningRequest{
		TransactionID:   "TX-IRAN-01",
		DebtorName:      "Tehran Machinery Co",
		DebtorCountry:   "IR", // Iran embargoed
		CreditorName:    "Global Importer",
		CreditorCountry: "DE",
	}

	res := engine.ScreenTransaction(req)
	if res.Action != service.ActionBlock {
		t.Fatalf("Expected BLOCK action for embargoed country, got %s", res.Action)
	}
	if len(res.BlockedCountries) != 1 || res.BlockedCountries[0] != "IR" {
		t.Fatalf("Expected blocked country IR, got %v", res.BlockedCountries)
	}
}

func TestSanctionsScreeningFuzzyMatchSDN(t *testing.T) {
	engine := service.NewSanctionsScreeningEngine()

	// Transliteration of "Qassem Soleimani" -> "Ghasem Soleymani"
	req := service.ScreeningRequest{
		TransactionID:   "TX-SDN-FUZZY",
		DebtorName:      "Ordinary Trading",
		DebtorCountry:   "AE",
		CreditorName:    "Ghasem Soleimani",
		CreditorCountry: "AE",
	}

	res := engine.ScreenTransaction(req)
	if res.Action == service.ActionPass {
		t.Fatalf("Expected match to trigger review or block, got PASS")
	}
	if len(res.Matches) == 0 {
		t.Fatalf("Expected matches for SDN name match")
	}
	if res.Matches[0].EntityID != "SDN-1001" {
		t.Fatalf("Expected match with SDN-1001, got %s", res.Matches[0].EntityID)
	}
}
