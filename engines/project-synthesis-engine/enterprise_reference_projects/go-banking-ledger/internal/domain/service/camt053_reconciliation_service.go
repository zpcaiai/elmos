package service

import (
	"encoding/xml"
	"fmt"
	"math"
	"strings"
	"time"
)

// Camt053DetailedMessage represents the ISO 20022 Bank-to-Customer Statement (camt.053.001.08)
type Camt053DetailedMessage struct {
	XMLName xml.Name                      `xml:"BkToCstmrStmt"`
	Xmlns   string                        `xml:"xmlns,attr"`
	GrpHdr  CamtGroupHeader               `xml:"GrpHdr"`
	Stmt    []BankToCustomerStatementInfo `xml:"Stmt"`
}

type CamtGroupHeader struct {
	MsgId   string `xml:"MsgId"`
	CreDtTm string `xml:"CreDtTm"`
}

type BankToCustomerStatementInfo struct {
	Id           string          `xml:"Id"`
	ElctrncSeqNb int             `xml:"ElctrncSeqNb"`
	CreDtTm      string          `xml:"CreDtTm"`
	Acct         CamtAccountInfo `xml:"Acct"`
	Bal          []CamtBalance   `xml:"Bal"`
	Ntry         []CamtEntry     `xml:"Ntry"`
}

type CamtAccountInfo struct {
	Id   CamtAccountId `xml:"Id"`
	Ccy  string        `xml:"Ccy"`
	Ownr *CamtParty    `xml:"Ownr,omitempty"`
	Svcr *CamtAgent    `xml:"Svcr,omitempty"`
}

type CamtAccountId struct {
	IBAN string `xml:"IBAN,omitempty"`
	Othr *struct {
		Id string `xml:"Id"`
	} `xml:"Othr,omitempty"`
}

type CamtParty struct {
	Nm string `xml:"Nm"`
}

type CamtAgent struct {
	FinInstnId struct {
		BICFI string `xml:"BICFI,omitempty"`
		Nm    string `xml:"Nm,omitempty"`
	} `xml:"FinInstnId"`
}

type CamtBalance struct {
	Tp struct {
		CdOrPrtry struct {
			Cd string `xml:"Cd"` // OPBD (Opening Booked), CLBD (Closing Booked), CLAV (Closing Available)
		} `xml:"CdOrPrtry"`
	} `xml:"Tp"`
	Amt       AmountWithCurrency `xml:"Amt"`
	CdtDbtInd string             `xml:"CdtDbtInd"` // CRDT or DBIT
	Dt        struct {
		Dt string `xml:"Dt"` // YYYY-MM-DD
	} `xml:"Dt"`
}

type CamtEntry struct {
	NtryRef   string             `xml:"NtryRef"`
	Amt       AmountWithCurrency `xml:"Amt"`
	CdtDbtInd string             `xml:"CdtDbtInd"` // CRDT (Credit / Deposit), DBIT (Debit / Withdrawal)
	Sts       string             `xml:"Sts"`       // BOOK (Booked), PDNG (Pending)
	BookgDt   struct {
		Dt string `xml:"Dt"`
	} `xml:"BookgDt"`
	ValDt struct {
		Dt string `xml:"Dt"`
	} `xml:"ValDt"`
	BkTxCd    BankTransactionCode `xml:"BkTxCd"`
	NtryDtls  []EntryDetails      `xml:"NtryDtls"`
}

type BankTransactionCode struct {
	Domn struct {
		Cd   string `xml:"Cd"` // e.g. PMNT
		Fmly struct {
			Cd    string `xml:"Cd"`    // e.g. ICDT (Issued Credit Transfer)
			SubFmlyCd string `xml:"SubFmlyCd"` // e.g. ESCT (SEPA Credit Transfer)
		} `xml:"Fmly"`
	} `xml:"Domn"`
}

type EntryDetails struct {
	TxDtls []TransactionDetails `xml:"TxDtls"`
}

type TransactionDetails struct {
	Refs struct {
		EndToEndId string `xml:"EndToEndId,omitempty"`
		UETR       string `xml:"UETR,omitempty"`
		AcctSvcrRef string `xml:"AcctSvcrRef,omitempty"`
	} `xml:"Refs"`
	Amt       AmountWithCurrency `xml:"Amt"`
	CdtDbtInd string             `xml:"CdtDbtInd"`
	RltdPties *RelatedParties    `xml:"RltdPties,omitempty"`
}

type RelatedParties struct {
	Dbtr *CamtParty `xml:"Dbtr,omitempty"`
	Cdtr *CamtParty `xml:"Cdtr,omitempty"`
}

// Internal Ledger Entry representation for bank statement reconciliation
type InternalLedgerTransaction struct {
	JournalEntryId string
	AccountId      string
	ReferenceId    string // Corresponds to EndToEndId or UETR
	AmountCents    int64
	IsCredit       bool   // true = credit, false = debit
	ValueDate      time.Time
	Description    string
}

// Reconciliation Findings and Outputs
type ReconciledPair struct {
	InternalEntryId string
	BankEntryRef    string
	EndToEndId      string
	AmountCents     int64
	ValueDate       string
}

type StatementReconciliationReport struct {
	StatementId             string
	AccountIdentifier       string
	Currency                string
	OpeningBalanceCents     int64
	StatedClosingBalanceCents int64
	CalculatedClosingBalanceCents int64
	TotalStatementCreditsCents int64
	TotalStatementDebitsCents int64
	StatementBalanceConserved bool

	MatchedEntriesCount     int
	TotalMatchedCents       int64
	MatchedPairs            []ReconciledPair

	UnmatchedBankEntries    []CamtEntry
	UnmatchedLedgerEntries  []InternalLedgerTransaction

	NetReconciliationVarianceCents int64
	IsFullyReconciled       bool
}

type Camt053ReconciliationService struct{}

func NewCamt053ReconciliationService() *Camt053ReconciliationService {
	return &Camt053ReconciliationService{}
}

// ParseCamt053XML deserializes an ISO 20022 camt.053.001.08 XML statement payload
func (s *Camt053ReconciliationService) ParseCamt053XML(xmlData []byte) (*Camt053DetailedMessage, error) {
	var msg Camt053DetailedMessage
	if err := xml.Unmarshal(xmlData, &msg); err != nil {
		return nil, fmt.Errorf("failed to parse camt.053 XML: %w", err)
	}

	if len(msg.Stmt) == 0 {
		return nil, fmt.Errorf("camt.053 statement payload contains zero Stmt elements")
	}

	return &msg, nil
}

// ReconcileDailyStatement performs comprehensive mathematical and transaction-level reconciliation
// between the external bank statement and internal double-entry ledger entries.
func (s *Camt053ReconciliationService) ReconcileDailyStatement(
	stmt *BankToCustomerStatementInfo,
	ledgerEntries []InternalLedgerTransaction,
) (*StatementReconciliationReport, error) {
	if stmt == nil {
		return nil, fmt.Errorf("statement info cannot be nil")
	}

	acctId := stmt.Acct.Id.IBAN
	if acctId == "" && stmt.Acct.Id.Othr != nil {
		acctId = stmt.Acct.Id.Othr.Id
	}
	ccy := stmt.Acct.Ccy

	// 1. Locate Opening and Closing Booked Balances
	var opbdCents, clbdCents int64
	var foundOpbd, foundClbd bool

	for _, bal := range stmt.Bal {
		code := strings.ToUpper(bal.Tp.CdOrPrtry.Cd)
		cents := int64(math.Round(bal.Amt.Value * 100.0))
		if bal.CdtDbtInd == "DBIT" {
			cents = -cents
		}

		if code == "OPBD" {
			opbdCents = cents
			foundOpbd = true
		} else if code == "CLBD" {
			clbdCents = cents
			foundClbd = true
		}
	}

	if !foundOpbd || !foundClbd {
		return nil, fmt.Errorf("statement %s missing OPBD (Opening) or CLBD (Closing) balance", stmt.Id)
	}

	// 2. Validate Statement Mathematical Equation:
	// Calculated Closing = Opening + Sum(Credits) - Sum(Debits)
	var totalStmtCredits, totalStmtDebits int64

	for _, ntry := range stmt.Ntry {
		entryCents := int64(math.Round(ntry.Amt.Value * 100.0))
		if strings.ToUpper(ntry.CdtDbtInd) == "CRDT" {
			totalStmtCredits += entryCents
		} else {
			totalStmtDebits += entryCents
		}
	}

	calcClosing := opbdCents + totalStmtCredits - totalStmtDebits
	balanceConserved := (calcClosing == clbdCents)

	// 3. Two-Way Transaction Reconciliation Matching
	matchedPairs := make([]ReconciledPair, 0)
	unmatchedBank := make([]CamtEntry, 0)
	unmatchedLedger := make([]InternalLedgerTransaction, 0)

	matchedLedgerIndices := make(map[int]bool)
	var totalMatchedCents int64

	for _, ntry := range stmt.Ntry {
		entryCents := int64(math.Round(ntry.Amt.Value * 100.0))
		isCredit := strings.ToUpper(ntry.CdtDbtInd) == "CRDT"

		// Extract EndToEndId or UETR
		var ref string
		if len(ntry.NtryDtls) > 0 && len(ntry.NtryDtls[0].TxDtls) > 0 {
			tx := ntry.NtryDtls[0].TxDtls[0]
			if tx.Refs.EndToEndId != "" {
				ref = tx.Refs.EndToEndId
			} else if tx.Refs.UETR != "" {
				ref = tx.Refs.UETR
			} else if tx.Refs.AcctSvcrRef != "" {
				ref = tx.Refs.AcctSvcrRef
			}
		}
		if ref == "" {
			ref = ntry.NtryRef
		}

		// Find match in ledger
		matchedIdx := -1
		for idx, leg := range ledgerEntries {
			if matchedLedgerIndices[idx] {
				continue
			}

			// Match criteria: identical amount, identical direction, and reference match
			if leg.AmountCents == entryCents && leg.IsCredit == isCredit {
				if leg.ReferenceId == ref || strings.EqualFold(leg.ReferenceId, ref) {
					matchedIdx = idx
					break
				}
			}
		}

		if matchedIdx >= 0 {
			matchedLedgerIndices[matchedIdx] = true
			leg := ledgerEntries[matchedIdx]
			totalMatchedCents += entryCents
			matchedPairs = append(matchedPairs, ReconciledPair{
				InternalEntryId: leg.JournalEntryId,
				BankEntryRef:    ntry.NtryRef,
				EndToEndId:      ref,
				AmountCents:     entryCents,
				ValueDate:       ntry.ValDt.Dt,
			})
		} else {
			unmatchedBank = append(unmatchedBank, ntry)
		}
	}

	// Identify remaining unmatched ledger entries (transit deposits / uncleared disbursements)
	for idx, leg := range ledgerEntries {
		if !matchedLedgerIndices[idx] {
			unmatchedLedger = append(unmatchedLedger, leg)
		}
	}

	// Compute Net Reconciliation Variance
	var unmatchedBankDelta int64
	for _, ub := range unmatchedBank {
		c := int64(math.Round(ub.Amt.Value * 100.0))
		if strings.ToUpper(ub.CdtDbtInd) == "CRDT" {
			unmatchedBankDelta += c
		} else {
			unmatchedBankDelta -= c
		}
	}

	var unmatchedLedgerDelta int64
	for _, ul := range unmatchedLedger {
		if ul.IsCredit {
			unmatchedLedgerDelta += ul.AmountCents
		} else {
			unmatchedLedgerDelta -= ul.AmountCents
		}
	}

	netVariance := unmatchedBankDelta - unmatchedLedgerDelta
	isFullyReconciled := balanceConserved && len(unmatchedBank) == 0 && len(unmatchedLedger) == 0

	return &StatementReconciliationReport{
		StatementId:                   stmt.Id,
		AccountIdentifier:             acctId,
		Currency:                      ccy,
		OpeningBalanceCents:           opbdCents,
		StatedClosingBalanceCents:     clbdCents,
		CalculatedClosingBalanceCents: calcClosing,
		TotalStatementCreditsCents:    totalStmtCredits,
		TotalStatementDebitsCents:     totalStmtDebits,
		StatementBalanceConserved:     balanceConserved,
		MatchedEntriesCount:           len(matchedPairs),
		TotalMatchedCents:             totalMatchedCents,
		MatchedPairs:                  matchedPairs,
		UnmatchedBankEntries:          unmatchedBank,
		UnmatchedLedgerEntries:        unmatchedLedger,
		NetReconciliationVarianceCents: netVariance,
		IsFullyReconciled:             isFullyReconciled,
	}, nil
}
