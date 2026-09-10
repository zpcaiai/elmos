package service

import (
	"encoding/xml"
	"fmt"
	"strings"
	"time"
)

// Pacs008Message represents an ISO 20022 FI Customer Credit Transfer (pacs.008.001.10)
type Pacs008Message struct {
	XMLName        xml.Name       `xml:"FIToFICstmrCdtTrf"`
	Xmlns          string         `xml:"xmlns,attr"`
	GrpHdr         GroupHeader    `xml:"GrpHdr"`
	CdtTrfTxInf    []CreditTransferTxInfo `xml:"CdtTrfTxInf"`
}

type GroupHeader struct {
	MsgId          string         `xml:"MsgId"`
	CreDtTm        string         `xml:"CreDtTm"`
	NbOfTxs        int            `xml:"NbOfTxs"`
	SttlmInf       SettlementInfo `xml:"SttlmInf"`
}

type SettlementInfo struct {
	SttlmMtd       string         `xml:"SttlmMtd"` // CLRG (Clearing), INDA (Individual Agent)
	ClrSys         *ClearingSystem `xml:"ClrSys,omitempty"`
}

type ClearingSystem struct {
	Prtry          string         `xml:"Prtry"` // FEDWIRE, CHIPS, TARGET2, SEPA
}

type CreditTransferTxInfo struct {
	PmtId          PaymentIdentification `xml:"PmtId"`
	IntrBkSttlmAmt AmountWithCurrency   `xml:"IntrBkSttlmAmt"`
	IntrBkSttlmDt  string                `xml:"IntrBkSttlmDt"` // YYYY-MM-DD
	Dbtr           PartyIdentification   `xml:"Dbtr"`
	DbtrAcct       CashAccount           `xml:"DbtrAcct"`
	DbtrAgt        BranchAndFinancialInst `xml:"DbtrAgt"`
	CdtrAgt        BranchAndFinancialInst `xml:"CdtrAgt"`
	Cdtr           PartyIdentification   `xml:"Cdtr"`
	CdtrAcct       CashAccount           `xml:"CdtrAcct"`
	RmtInf         *RemittanceInfo       `xml:"RmtInf,omitempty"`
}

type PaymentIdentification struct {
	EndToEndId     string `xml:"EndToEndId"`
	TxId           string `xml:"TxId"`
	UETR           string `xml:"UETR"` // Unique End-to-End Transaction Reference (RFC 4122 UUIDv4)
}

type AmountWithCurrency struct {
	Ccy   string  `xml:"Ccy,attr"`
	Value float64 `xml:",chardata"`
}

type PartyIdentification struct {
	Nm     string   `xml:"Nm"`
	PstlAdr *PostalAddress `xml:"PstlAdr,omitempty"`
}

type PostalAddress struct {
	Ctry   string   `xml:"Ctry,omitempty"`
	AdrLine []string `xml:"AdrLine,omitempty"`
}

type CashAccount struct {
	Id CashAccountId `xml:"Id"`
}

type CashAccountId struct {
	IBAN  string `xml:"IBAN,omitempty"`
	Othr  *OtherAccountIdentification `xml:"Othr,omitempty"`
}

type OtherAccountIdentification struct {
	Id string `xml:"Id"`
}

type BranchAndFinancialInst struct {
	FinInstnId FinancialInstitutionId `xml:"FinInstnId"`
}

type FinancialInstitutionId struct {
	BICFI string `xml:"BICFI,omitempty"`
	Nm    string `xml:"Nm,omitempty"`
}

type RemittanceInfo struct {
	Ustrd []string `xml:"Ustrd,omitempty"`
}

// Pacs002Message represents an ISO 20022 Payment Status Report (pacs.002.001.12)
type Pacs002Message struct {
	XMLName    xml.Name               `xml:"FIToFIPmtStsRpt"`
	Xmlns      string                 `xml:"xmlns,attr"`
	GrpHdr     GroupHeader            `xml:"GrpHdr"`
	TxInfAndSts []TxInfoAndStatus     `xml:"TxInfAndSts"`
}

type TxInfoAndStatus struct {
	OrgnlEndToEndId string         `xml:"OrgnlEndToEndId"`
	OrgnlTxId       string         `xml:"OrgnlTxId"`
	TxSts           string         `xml:"TxSts"` // ACTC (AcceptedTechnicalValidation), ACSC (AcceptedSettlementCompleted), RJCT (Rejected)
	StsRsnInf       *StatusReason  `xml:"StsRsnInf,omitempty"`
}

type StatusReason struct {
	Rsn  ReasonCode `xml:"Rsn"`
	AddtlInf []string `xml:"AddtlInf,omitempty"`
}

type ReasonCode struct {
	Cd string `xml:"Cd"` // AC04 (ClosedAccountNumber), AM04 (InsufficientFunds), AG01 (TransactionForbidden)
}

// Camt053Message represents an ISO 20022 Bank-to-Customer Statement (camt.053.001.10)
type Camt053Message struct {
	XMLName  xml.Name           `xml:"BkToCstmrStmt"`
	Xmlns    string             `xml:"xmlns,attr"`
	GrpHdr   GroupHeader        `xml:"GrpHdr"`
	Stmt     []StatementReport  `xml:"Stmt"`
}

type StatementReport struct {
	Id          string             `xml:"Id"`
	CreDtTm     string             `xml:"CreDtTm"`
	Acct        CashAccount        `xml:"Acct"`
	Bal         []BalanceRecord    `xml:"Bal"`
	Ntry        []StatementEntry   `xml:"Ntry"`
}

type BalanceRecord struct {
	Tp      BalanceType        `xml:"Tp"`
	Amt     AmountWithCurrency `xml:"Amt"`
	CdtDbtInd string           `xml:"CdtDbtInd"` // CRDT or DBIT
	Dt      string             `xml:"Dt>Dt"`     // YYYY-MM-DD
}

type BalanceType struct {
	CdOrPrtry CodeOrProprietary `xml:"CdOrPrtry"`
}

type CodeOrProprietary struct {
	Cd string `xml:"Cd"` // OPBD (OpeningBooked), CLBD (ClosingBooked), ITBD (InterimBooked)
}

type StatementEntry struct {
	Amt        AmountWithCurrency `xml:"Amt"`
	CdtDbtInd  string             `xml:"CdtDbtInd"`
	Sts        string             `xml:"Sts"` // BOOK (Booked), PDNG (Pending)
	BookgDt    string             `xml:"BookgDt>Dt"`
	BkTxCd     BankTxCode         `xml:"BkTxCd"`
}

type BankTxCode struct {
	Domn DomainCode `xml:"Domn"`
}

type DomainCode struct {
	Cd    string `xml:"Cd"`    // PMNT (Payments)
	Fmly  FamilyCode `xml:"Fmly"`
}

type FamilyCode struct {
	Cd    string `xml:"Cd"`    // RCDT (ReceivedCreditTransfer), ICDT (IssuedCreditTransfer)
	SubFmlyCd string `xml:"SubFmlyCd"`
}

// ISO20022Engine serializes, parses, and validates ISO 20022 payments.
type ISO20022Engine struct{}

func NewISO20022Engine() *ISO20022Engine {
	return &ISO20022Engine{}
}

// BuildPacs008 creates a fully compliant pacs.008 customer credit transfer.
func (e *ISO20022Engine) BuildPacs008(
	msgID, uetr, endToEndID, txID string,
	settlementDate time.Time,
	clearingSystemName string,
	amountCents int64,
	currency string,
	debtorName, debtorCountry, debtorAcct, debtorBIC string,
	creditorName, creditorCountry, creditorAcct, creditorBIC string,
	remittanceUnstructured string,
) (*Pacs008Message, error) {
	if msgID == "" || endToEndID == "" {
		return nil, fmt.Errorf("msgID and endToEndID are required")
	}

	amountDecimal := float64(amountCents) / 100.0

	var rmt *RemittanceInfo
	if remittanceUnstructured != "" {
		rmt = &RemittanceInfo{
			Ustrd: []string{remittanceUnstructured},
		}
	}

	msg := &Pacs008Message{
		Xmlns: "urn:iso:std:iso:20022:tech:xsd:pacs.008.001.10",
		GrpHdr: GroupHeader{
			MsgId:   msgID,
			CreDtTm: time.Now().UTC().Format(time.RFC3339),
			NbOfTxs: 1,
			SttlmInf: SettlementInfo{
				SttlmMtd: "CLRG",
				ClrSys:   &ClearingSystem{Prtry: clearingSystemName},
			},
		},
		CdtTrfTxInf: []CreditTransferTxInfo{
			{
				PmtId: PaymentIdentification{
					EndToEndId: endToEndID,
					TxId:       txID,
					UETR:       uetr,
				},
				IntrBkSttlmAmt: AmountWithCurrency{
					Ccy:   string(amount.Currency()),
					Value: amountDecimal,
				},
				IntrBkSttlmDt: settlementDate.Format("2006-01-02"),
				Dbtr: PartyIdentification{
					Nm: debtorName,
					PstlAdr: &PostalAddress{
						Ctry: debtorCountry,
					},
				},
				DbtrAcct: CashAccount{
					Id: CashAccountId{
						IBAN: debtorAcct,
					},
				},
				DbtrAgt: BranchAndFinancialInst{
					FinInstnId: FinancialInstitutionId{
						BICFI: debtorBIC,
					},
				},
				CdtrAgt: BranchAndFinancialInst{
					FinInstnId: FinancialInstitutionId{
						BICFI: creditorBIC,
					},
				},
				Cdtr: PartyIdentification{
					Nm: creditorName,
					PstlAdr: &PostalAddress{
						Ctry: creditorCountry,
					},
				},
				CdtrAcct: CashAccount{
					Id: CashAccountId{
						IBAN: creditorAcct,
					},
				},
				RmtInf: rmt,
			},
		},
	}

	return msg, nil
}

// MarshalToXML converts an ISO 20022 message struct to indented XML bytes.
func (e *ISO20022Engine) MarshalToXML(v interface{}) ([]byte, error) {
	output, err := xml.MarshalIndent(v, "", "  ")
	if err != nil {
		return nil, fmt.Errorf("failed to marshal ISO 20022 XML: %w", err)
	}
	header := []byte(xml.Header)
	return append(header, output...), nil
}

// ParsePacs008 deserializes raw XML into a Pacs008Message.
func (e *ISO20022Engine) ParsePacs008(data []byte) (*Pacs008Message, error) {
	var msg Pacs008Message
	if err := xml.Unmarshal(data, &msg); err != nil {
		return nil, fmt.Errorf("failed to parse pacs.008 XML: %w", err)
	}
	if !strings.Contains(msg.Xmlns, "pacs.008") {
		return nil, fmt.Errorf("XML namespace is not pacs.008: %s", msg.Xmlns)
	}
	return &msg, nil
}

// BuildPacs002StatusReport generates an acceptance or rejection status report.
func (e *ISO20022Engine) BuildPacs002StatusReport(
	msgID, origMsgID, origEndToEndID, origTxID string,
	accepted bool,
	rejectionReasonCode string,
	rejectionDetail string,
) *Pacs002Message {
	statusCode := "ACSC" // Accepted Settlement Completed
	var reasonInfo *StatusReason

	if !accepted {
		statusCode = "RJCT" // Rejected
		reasonInfo = &StatusReason{
			Rsn: ReasonCode{Cd: rejectionReasonCode},
			AddtlInf: []string{rejectionDetail},
		}
	}

	return &Pacs002Message{
		Xmlns: "urn:iso:std:iso:20022:tech:xsd:pacs.002.001.12",
		GrpHdr: GroupHeader{
			MsgId:   msgID,
			CreDtTm: time.Now().UTC().Format(time.RFC3339),
			NbOfTxs: 1,
		},
		TxInfAndSts: []TxInfoAndStatus{
			{
				OrgnlEndToEndId: origEndToEndID,
				OrgnlTxId:       origTxID,
				TxSts:           statusCode,
				StsRsnInf:       reasonInfo,
			},
		},
	}
}
