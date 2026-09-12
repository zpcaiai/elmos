package test

import (
	"testing"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/service"
)

func TestCamt053XMLParsingAndBalanceConservation(t *testing.T) {
	xmlSample := `<?xml version="1.0" encoding="UTF-8"?>
<BkToCstmrStmt xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08">
  <GrpHdr>
    <MsgId>CAMT-053-20260615-001</MsgId>
    <CreDtTm>2026-06-15T18:00:00Z</CreDtTm>
  </GrpHdr>
  <Stmt>
    <Id>STMT-20260615-DE89370400440532013000</Id>
    <ElctrncSeqNb>152</ElctrncSeqNb>
    <CreDtTm>2026-06-15T18:00:00Z</CreDtTm>
    <Acct>
      <Id>
        <IBAN>DE89370400440532013000</IBAN>
      </Id>
      <Ccy>EUR</Ccy>
    </Acct>
    <Bal>
      <Tp>
        <CdOrPrtry>
          <Cd>OPBD</Cd>
        </CdOrPrtry>
      </Tp>
      <Amt Ccy="EUR">10000000.00</Amt>
      <CdtDbtInd>CRDT</CdtDbtInd>
      <Dt>
        <Dt>2026-06-15</Dt>
      </Dt>
    </Bal>
    <Bal>
      <Tp>
        <CdOrPrtry>
          <Cd>CLBD</Cd>
        </CdOrPrtry>
      </Tp>
      <Amt Ccy="EUR">11500000.00</Amt>
      <CdtDbtInd>CRDT</CdtDbtInd>
      <Dt>
        <Dt>2026-06-15</Dt>
      </Dt>
    </Bal>
    <Ntry>
      <NtryRef>NTRY-001</NtryRef>
      <Amt Ccy="EUR">2500000.00</Amt>
      <CdtDbtInd>CRDT</CdtDbtInd>
      <Sts>BOOK</Sts>
      <BookgDt><Dt>2026-06-15</Dt></BookgDt>
      <ValDt><Dt>2026-06-15</Dt></ValDt>
      <BkTxCd>
        <Domn>
          <Cd>PMNT</Cd>
          <Fmly>
            <Cd>ICDT</Cd>
            <SubFmlyCd>ESCT</SubFmlyCd>
          </Fmly>
        </Domn>
      </BkTxCd>
      <NtryDtls>
        <TxDtls>
          <Refs>
            <EndToEndId>E2E-SEPA-CREDIT-9901</EndToEndId>
            <UETR>c3f91802-e2a8-4e8c-a6e5-470081d3f9b2</UETR>
          </Refs>
          <Amt Ccy="EUR">2500000.00</Amt>
          <CdtDbtInd>CRDT</CdtDbtInd>
        </TxDtls>
      </NtryDtls>
    </Ntry>
    <Ntry>
      <NtryRef>NTRY-002</NtryRef>
      <Amt Ccy="EUR">1000000.00</Amt>
      <CdtDbtInd>DBIT</CdtDbtInd>
      <Sts>BOOK</Sts>
      <BookgDt><Dt>2026-06-15</Dt></BookgDt>
      <ValDt><Dt>2026-06-15</Dt></ValDt>
      <BkTxCd>
        <Domn>
          <Cd>PMNT</Cd>
          <Fmly>
            <Cd>OCDT</Cd>
            <SubFmlyCd>TIPS</SubFmlyCd>
          </Fmly>
        </Domn>
      </BkTxCd>
      <NtryDtls>
        <TxDtls>
          <Refs>
            <EndToEndId>E2E-TIPS-OUT-8812</EndToEndId>
          </Refs>
          <Amt Ccy="EUR">1000000.00</Amt>
          <CdtDbtInd>DBIT</CdtDbtInd>
        </TxDtls>
      </NtryDtls>
    </Ntry>
  </Stmt>
</BkToCstmrStmt>`

	svc := service.NewCamt053ReconciliationService()
	msg, err := svc.ParseCamt053XML([]byte(xmlSample))
	if err != nil {
		t.Fatalf("Failed to parse camt.053 XML: %v", err)
	}

	stmt := &msg.Stmt[0]
	if stmt.Acct.Id.IBAN != "DE89370400440532013000" {
		t.Errorf("Expected IBAN DE89370400440532013000, got %s", stmt.Acct.Id.IBAN)
	}

	// Prepare exact internal ledger matches
	ledger := []service.InternalLedgerTransaction{
		{
			JournalEntryId: "J-01",
			AccountId:      "DE89370400440532013000",
			ReferenceId:    "E2E-SEPA-CREDIT-9901",
			AmountCents:    250000000, // €2,500,000.00
			IsCredit:       true,
			ValueDate:      time.Now(),
			Description:    "Inbound SEPA wholesale settlement",
		},
		{
			JournalEntryId: "J-02",
			AccountId:      "DE89370400440532013000",
			ReferenceId:    "E2E-TIPS-OUT-8812",
			AmountCents:    100000000, // €1,000,000.00
			IsCredit:       false,
			ValueDate:      time.Now(),
			Description:    "Outbound TIPS instant payment",
		},
	}

	report, err := svc.ReconcileDailyStatement(stmt, ledger)
	if err != nil {
		t.Fatalf("Reconciliation failed: %v", err)
	}

	if !report.StatementBalanceConserved {
		t.Errorf("Statement balance equation not conserved: Stated=%d, Calc=%d",
			report.StatedClosingBalanceCents, report.CalculatedClosingBalanceCents)
	}

	if !report.IsFullyReconciled {
		t.Errorf("Expected full reconciliation: Matched=%d, UnmatchedBank=%d, UnmatchedLedger=%d",
			report.MatchedEntriesCount, len(report.UnmatchedBankEntries), len(report.UnmatchedLedgerEntries))
	}

	if report.MatchedEntriesCount != 2 {
		t.Errorf("Expected 2 matched entries, got %d", report.MatchedEntriesCount)
	}

	if report.NetReconciliationVarianceCents != 0 {
		t.Errorf("Expected 0 net variance, got %d", report.NetReconciliationVarianceCents)
	}
}

func TestCamt053DiscrepancyDetectionWithTransitItems(t *testing.T) {
	xmlSample := `<?xml version="1.0" encoding="UTF-8"?>
<BkToCstmrStmt xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08">
  <GrpHdr><MsgId>MSG-02</MsgId><CreDtTm>2026-06-15T18:00:00Z</CreDtTm></GrpHdr>
  <Stmt>
    <Id>STMT-02</Id>
    <ElctrncSeqNb>1</ElctrncSeqNb>
    <CreDtTm>2026-06-15T18:00:00Z</CreDtTm>
    <Acct><Id><IBAN>FR7630006000011234567890189</IBAN></Id><Ccy>EUR</Ccy></Acct>
    <Bal>
      <Tp><CdOrPrtry><Cd>OPBD</Cd></CdOrPrtry></Tp>
      <Amt Ccy="EUR">5000000.00</Amt>
      <CdtDbtInd>CRDT</CdtDbtInd>
      <Dt><Dt>2026-06-15</Dt></Dt>
    </Bal>
    <Bal>
      <Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp>
      <Amt Ccy="EUR">4999500.00</Amt>
      <CdtDbtInd>CRDT</CdtDbtInd>
      <Dt><Dt>2026-06-15</Dt></Dt>
    </Bal>
    <!-- Unexpected unrecorded bank fee of €500.00 -->
    <Ntry>
      <NtryRef>FEE-MONTHLY-01</NtryRef>
      <Amt Ccy="EUR">500.00</Amt>
      <CdtDbtInd>DBIT</CdtDbtInd>
      <Sts>BOOK</Sts>
      <BookgDt><Dt>2026-06-15</Dt></BookgDt>
      <ValDt><Dt>2026-06-15</Dt></ValDt>
      <BkTxCd><Domn><Cd>PMNT</Cd><Fmly><Cd>ICHG</Cd><SubFmlyCd>CHRG</SubFmlyCd></Fmly></Domn></BkTxCd>
    </Ntry>
  </Stmt>
</BkToCstmrStmt>`

	svc := service.NewCamt053ReconciliationService()
	msg, err := svc.ParseCamt053XML([]byte(xmlSample))
	if err != nil {
		t.Fatalf("XML parse error: %v", err)
	}

	// Internal ledger has an uncleared transit payment of €15,000.00
	ledger := []service.InternalLedgerTransaction{
		{
			JournalEntryId: "J-TRANSIT-01",
			AccountId:      "FR7630006000011234567890189",
			ReferenceId:    "E2E-TRANSIT-WIRE-99",
			AmountCents:    1500000, // €15,000.00
			IsCredit:       false,
			ValueDate:      time.Now(),
			Description:    "Uncleared outbound wire payment",
		},
	}

	report, err := svc.ReconcileDailyStatement(&msg.Stmt[0], ledger)
	if err != nil {
		t.Fatalf("Reconciliation failed: %v", err)
	}

	if report.IsFullyReconciled {
		t.Errorf("Expected reconciliation discrepancy due to unmatched fee and transit payment")
	}

	if len(report.UnmatchedBankEntries) != 1 {
		t.Errorf("Expected 1 unmatched bank fee, got %d", len(report.UnmatchedBankEntries))
	}

	if len(report.UnmatchedLedgerEntries) != 1 {
		t.Errorf("Expected 1 unmatched transit payment, got %d", len(report.UnmatchedLedgerEntries))
	}

	// Bank delta = -€500 (-50,000 cents)
	// Ledger delta = -€15,000 (-1,500,000 cents)
	// Net variance = -50,000 - (-1,500,000) = +1,450,000 cents (+€14,500.00)
	if report.NetReconciliationVarianceCents != 1450000 {
		t.Errorf("Expected net variance of 1450000 cents, got %d", report.NetReconciliationVarianceCents)
	}
}
