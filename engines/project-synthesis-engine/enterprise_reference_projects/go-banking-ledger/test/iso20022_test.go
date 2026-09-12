package test

import (
	"strings"
	"testing"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/service"
)

func TestPacs008BuildAndParseXML(t *testing.T) {
	isoEngine := service.NewISO20022Engine()

	amountCents := int64(5000000) // $50,000.00
	msg, err := isoEngine.BuildPacs008(
		"MSG-2026-001",
		"c2b6d510-9b43-4f9e-8c31-7e8c1b9201f4",
		"E2E-2026-09-10-A01",
		"TX-998877",
		time.Date(2026, 9, 10, 0, 0, 0, 0, time.UTC),
		"FEDWIRE",
		amountCents,
		"USD",
		"Acme Corporation",
		"US",
		"US12FEDW000123456789",
		"CHASUS33XXX",
		"Global Logistics Inc",
		"US",
		"US98FEDW000987654321",
		"BOFAUS3NXXX",
		"Invoice INV-40291 payment",
	)
	if err != nil {
		t.Fatalf("Failed to build pacs.008: %v", err)
	}

	xmlBytes, err := isoEngine.MarshalToXML(msg)
	if err != nil {
		t.Fatalf("Failed to marshal pacs.008 to XML: %v", err)
	}

	xmlStr := string(xmlBytes)
	if !strings.Contains(xmlStr, "<FIToFICstmrCdtTrf") {
		t.Fatalf("Expected XML root element FIToFICstmrCdtTrf, got:\n%s", xmlStr)
	}
	if !strings.Contains(xmlStr, "E2E-2026-09-10-A01") {
		t.Fatalf("Expected EndToEndId in XML, got:\n%s", xmlStr)
	}

	// Parse back from XML
	parsed, err := isoEngine.ParsePacs008(xmlBytes)
	if err != nil {
		t.Fatalf("Failed to parse pacs.008 XML: %v", err)
	}

	if parsed.GrpHdr.MsgId != "MSG-2026-001" {
		t.Fatalf("Expected MsgId MSG-2026-001, got %s", parsed.GrpHdr.MsgId)
	}
	if len(parsed.CdtTrfTxInf) != 1 {
		t.Fatalf("Expected 1 transaction info, got %d", len(parsed.CdtTrfTxInf))
	}
	if parsed.CdtTrfTxInf[0].IntrBkSttlmAmt.Value != 50000.00 {
		t.Fatalf("Expected settlement amount 50000.00, got %f", parsed.CdtTrfTxInf[0].IntrBkSttlmAmt.Value)
	}
}

func TestPacs002StatusReport(t *testing.T) {
	isoEngine := service.NewISO20022Engine()

	// Rejection report
	report := isoEngine.BuildPacs002StatusReport(
		"MSG-REJ-01",
		"ORIG-MSG-01",
		"E2E-1234",
		"TX-1234",
		false,
		"AM04", // Insufficient funds
		"Debtor account balance insufficient for transfer",
	)

	xmlBytes, err := isoEngine.MarshalToXML(report)
	if err != nil {
		t.Fatalf("Failed to marshal pacs.002 to XML: %v", err)
	}

	xmlStr := string(xmlBytes)
	if !strings.Contains(xmlStr, "<TxSts>RJCT</TxSts>") {
		t.Fatalf("Expected status RJCT in XML, got:\n%s", xmlStr)
	}
	if !strings.Contains(xmlStr, "<Cd>AM04</Cd>") {
		t.Fatalf("Expected reason AM04 in XML, got:\n%s", xmlStr)
	}
}
