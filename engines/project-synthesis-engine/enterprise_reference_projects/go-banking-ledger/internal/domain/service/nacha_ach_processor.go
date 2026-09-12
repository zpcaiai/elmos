package service

import (
	"bufio"
	"errors"
	"fmt"
	"io"
	"strconv"
	"strings"
	"time"
)

// Standard Entry Class (SEC) codes for US ACH transactions
type StandardEntryClass string

const (
	SecPPD StandardEntryClass = "PPD" // Prearranged Payment and Deposit (Payroll, Consumer Bill Pay)
	SecCCD StandardEntryClass = "CCD" // Corporate Credit or Debit (B2B, Treasury)
	SecCTX StandardEntryClass = "CTX" // Corporate Trade Exchange (Multi-invoice ANSI ASC X12)
	SecWEB StandardEntryClass = "WEB" // Internet-initiated Consumer Debit/Credit
	SecTEL StandardEntryClass = "TEL" // Telephone-initiated Consumer Debit
)

// ServiceClassCode represents the batch transaction type
type ServiceClassCode int

const (
	ServiceClassMixed   ServiceClassCode = 200
	ServiceClassCredits ServiceClassCode = 220
	ServiceClassDebits  ServiceClassCode = 280
)

// TransactionCode specifies account type and debit/credit action
type TransactionCode int

const (
	TxDemandCredit    TransactionCode = 22 // Checking account credit (deposit)
	TxDemandDebit     TransactionCode = 27 // Checking account debit (withdrawal)
	TxSavingsCredit   TransactionCode = 32 // Savings account credit
	TxSavingsDebit    TransactionCode = 37 // Savings account debit
	TxDemandReturnC   TransactionCode = 21 // Return / reversal of checking credit
	TxDemandReturnD   TransactionCode = 26 // Return / reversal of checking debit
)

var (
	ErrInvalidRecordLength = errors.New("nacha record must be exactly 94 characters")
	ErrInvalidRecordType   = errors.New("invalid nacha record type indicator")
	ErrInvalidAbaChecksum  = errors.New("invalid 9-digit ABA routing transit number checksum")
	ErrBatchHashMismatch   = errors.New("calculated entry hash does not match batch control hash")
	ErrBatchAmountMismatch = errors.New("batch debit/credit sum does not balance with detail records")
	ErrFileControlMismatch = errors.New("file control record counts/sums do not match batch totals")
)

// ValidateAbaRoutingNumber verifies the Fedwire/ACH Modulo-10 checksum:
// (3*(d1+d4+d7) + 7*(d2+d5+d8) + 1*(d3+d6+d9)) % 10 == 0
func ValidateAbaRoutingNumber(routing string) bool {
	routing = strings.TrimSpace(routing)
	if len(routing) != 9 {
		return false
	}
	digits := make([]int, 9)
	for i, r := range routing {
		if r < '0' || r > '9' {
			return false
		}
		digits[i] = int(r - '0')
	}
	weightedSum := 3*(digits[0]+digits[3]+digits[6]) +
		7*(digits[1]+digits[4]+digits[7]) +
		1*(digits[2]+digits[5]+digits[8])
	return weightedSum%10 == 0
}

// ACHEntryDetail represents an individual payment or collection instruction
type ACHEntryDetail struct {
	TransactionCode    TransactionCode
	ReceivingDfiRouting string // 8-digit transit number (without 9th check digit)
	CheckDigit         string // 9th digit of ABA
	DfiAccountNumber   string
	AmountCents        int64
	IndividualID       string
	IndividualName     string
	DiscretionaryData  string
	TraceNumber        string
	AddendaInformation string // Optional Addenda 05 record
}

// ACHBatch represents a group of related entries from an originator
type ACHBatch struct {
	ServiceClassCode   ServiceClassCode
	CompanyName        string
	CompanyDiscretion  string
	CompanyID          string // 10-char EIN or Tax ID
	StandardEntryClass StandardEntryClass
	EntryDescription   string // e.g., "PAYROLL", "INVOICE"
	CompanyDescriptiveDate string
	EffectiveEntryDate time.Time
	OriginatingDfiID   string // 8 digits
	BatchNumber        int
	Entries            []ACHEntryDetail
}

// ACHFile represents a complete NACHA 94-character transmission file
type ACHFile struct {
	ImmediateDestination string // 10-char " bbbbbbbbb" (space + 9-digit routing)
	ImmediateOrigin      string // 10-char Company ID or routing
	CreationTime         time.Time
	FileIDModifier       string // 'A'-'Z' or '0'-'9'
	ImmediateDestName    string
	ImmediateOriginName  string
	ReferenceCode        string
	Batches              []ACHBatch
}

// NachaACHProcessor handles high-throughput ACH parsing, validation, and generation
type NachaACHProcessor struct{}

func NewNachaACHProcessor() *NachaACHProcessor {
	return &NachaACHProcessor{}
}

// GenerateACHFile compiles an in-memory ACHFile struct into standard 94-char fixed lines
func (p *NachaACHProcessor) GenerateACHFile(file *ACHFile) (string, error) {
	if file == nil || len(file.Batches) == 0 {
		return "", errors.New("ach file must contain at least one batch")
	}

	var sb strings.Builder
	totalRecords := 0

	// 1. File Header Record (Type 1)
	dest := padRight(file.ImmediateDestination, 10)
	origin := padRight(file.ImmediateOrigin, 10)
	createDate := file.CreationTime.Format("060102") // YYMMDD
	createTime := file.CreationTime.Format("1504")   // HHMM
	mod := file.FileIDModifier
	if mod == "" {
		mod = "A"
	}

	fileHeader := fmt.Sprintf("101%10s%10s%6s%4s%1s094101%-23s%-23s%-8s",
		dest, origin, createDate, createTime, mod,
		padRight(file.ImmediateDestName, 23),
		padRight(file.ImmediateOriginName, 23),
		padRight(file.ReferenceCode, 8))
	sb.WriteString(padTo94(fileHeader) + "\n")
	totalRecords++

	var fileEntryHash int64 = 0
	var fileTotalDebits int64 = 0
	var fileTotalCredits int64 = 0
	totalDetailAndAddenda := 0

	// Process Batches
	for bIdx, batch := range file.Batches {
		batchNum := bIdx + 1
		// 2. Batch Header Record (Type 5)
		effDate := batch.EffectiveEntryDate.Format("060102")
		batchHeader := fmt.Sprintf("5%03d%-16s%-20s%10s%3s%-10s%-6s%6s   1%8s%07d",
			batch.ServiceClassCode,
			padRight(batch.CompanyName, 16),
			padRight(batch.CompanyDiscretion, 20),
			padRight(batch.CompanyID, 10),
			string(batch.StandardEntryClass),
			padRight(batch.EntryDescription, 10),
			padRight(batch.CompanyDescriptiveDate, 6),
			effDate,
			padRight(batch.OriginatingDfiID, 8),
			batchNum)
		sb.WriteString(padTo94(batchHeader) + "\n")
		totalRecords++

		var batchEntryHash int64 = 0
		var batchDebits int64 = 0
		var batchCredits int64 = 0
		batchDetailCount := 0

		for eIdx, entry := range batch.Entries {
			trace := entry.TraceNumber
			if trace == "" {
				trace = fmt.Sprintf("%8s%07d", padRight(batch.OriginatingDfiID, 8), eIdx+1)
			}

			// Add to Entry Hash (sum of first 8 digits of routing)
			routingNum, _ := strconv.ParseInt(entry.ReceivingDfiRouting[:8], 10, 64)
			batchEntryHash += routingNum

			hasAddenda := 0
			if entry.AddendaInformation != "" {
				hasAddenda = 1
			}

			// 3. Entry Detail Record (Type 6)
			entryLine := fmt.Sprintf("6%02d%8s%1s%-17s%010d%-15s%-22s%2s%1d%15s",
				entry.TransactionCode,
				entry.ReceivingDfiRouting[:8],
				entry.CheckDigit,
				padRight(entry.DfiAccountNumber, 17),
				entry.AmountCents,
				padRight(entry.IndividualID, 15),
				padRight(entry.IndividualName, 22),
				padRight(entry.DiscretionaryData, 2),
				hasAddenda,
				padRight(trace, 15))
			sb.WriteString(padTo94(entryLine) + "\n")
			totalRecords++
			batchDetailCount++

			if entry.TransactionCode == TxDemandDebit || entry.TransactionCode == TxSavingsDebit {
				batchDebits += entry.AmountCents
			} else {
				batchCredits += entry.AmountCents
			}

			// Optional Addenda Record (Type 7)
			if hasAddenda == 1 {
				addendaLine := fmt.Sprintf("705%-80s%04d%07d",
					padRight(entry.AddendaInformation, 80),
					1,
					eIdx+1)
				sb.WriteString(padTo94(addendaLine) + "\n")
				totalRecords++
				batchDetailCount++
			}
		}

		totalDetailAndAddenda += batchDetailCount
		fileEntryHash += batchEntryHash
		fileTotalDebits += batchDebits
		fileTotalCredits += batchCredits

		// 4. Batch Control Record (Type 8)
		batchHash10 := batchEntryHash % 10000000000
		batchControl := fmt.Sprintf("8%03d%06d%010d%012d%012d%10s%19s%8s%07d",
			batch.ServiceClassCode,
			batchDetailCount,
			batchHash10,
			batchDebits,
			batchCredits,
			padRight(batch.CompanyID, 10),
			"",
			padRight(batch.OriginatingDfiID, 8),
			batchNum)
		sb.WriteString(padTo94(batchControl) + "\n")
		totalRecords++
	}

	// 5. File Control Record (Type 9)
	totalBatches := len(file.Batches)
	fileHash10 := fileEntryHash % 10000000000
	totalRecordsPlusControl := totalRecords + 1
	// Blocking factor = 10 records per block
	blockCount := (totalRecordsPlusControl + 9) / 10

	fileControl := fmt.Sprintf("9%06d%06d%08d%010d%012d%012d%39s",
		totalBatches,
		blockCount,
		totalDetailAndAddenda,
		fileHash10,
		fileTotalDebits,
		fileTotalCredits,
		"")
	sb.WriteString(padTo94(fileControl) + "\n")
	totalRecords++

	// 6. Block Padding (fill block to multiple of 10 with 9s)
	linesToPad := (10 - (totalRecords % 10)) % 10
	for i := 0; i < linesToPad; i++ {
		sb.WriteString(strings.Repeat("9", 94) + "\n")
	}

	return sb.String(), nil
}

// ParseACHFile parses and rigorously validates an incoming NACHA transmission string
func (p *NachaACHProcessor) ParseACHFile(reader io.Reader) (*ACHFile, error) {
	scanner := bufio.NewScanner(reader)
	var achFile *ACHFile
	var currentBatch *ACHBatch

	batchCount := 0
	lineNum := 0

	for scanner.Scan() {
		lineNum++
		line := scanner.Text()
		if len(line) == 0 {
			continue
		}
		if len(line) != 94 {
			return nil, fmt.Errorf("%w at line %d: got length %d", ErrInvalidRecordLength, lineNum, len(line))
		}

		recType := line[0]
		switch recType {
		case '1': // File Header
			dest := strings.TrimSpace(line[3:13])
			orig := strings.TrimSpace(line[13:23])
			cDate := line[23:29]
			cTime := line[29:33]
			mod := line[33:34]
			dName := strings.TrimSpace(line[40:63])
			oName := strings.TrimSpace(line[63:86])
			ref := strings.TrimSpace(line[86:94])

			t, _ := time.Parse("0601021504", cDate+cTime)
			achFile = &ACHFile{
				ImmediateDestination: dest,
				ImmediateOrigin:      orig,
				CreationTime:         t,
				FileIDModifier:       mod,
				ImmediateDestName:    dName,
				ImmediateOriginName:  oName,
				ReferenceCode:        ref,
				Batches:              make([]ACHBatch, 0),
			}

		case '5': // Batch Header
			if achFile == nil {
				return nil, fmt.Errorf("batch header found before file header at line %d", lineNum)
			}
			scCode, _ := strconv.Atoi(line[1:4])
			compName := strings.TrimSpace(line[4:20])
			compDisc := strings.TrimSpace(line[20:40])
			compID := strings.TrimSpace(line[40:50])
			sec := StandardEntryClass(line[50:53])
			desc := strings.TrimSpace(line[53:63])
			effDateStr := line[69:75]
			effDate, _ := time.Parse("060102", effDateStr)
			origDfi := strings.TrimSpace(line[79:87])
			bNum, _ := strconv.Atoi(line[87:94])

			currentBatch = &ACHBatch{
				ServiceClassCode:   ServiceClassCode(scCode),
				CompanyName:        compName,
				CompanyDiscretion:  compDisc,
				CompanyID:          compID,
				StandardEntryClass: sec,
				EntryDescription:   desc,
				EffectiveEntryDate: effDate,
				OriginatingDfiID:   origDfi,
				BatchNumber:        bNum,
				Entries:            make([]ACHEntryDetail, 0),
			}

		case '6': // Entry Detail
			if currentBatch == nil {
				return nil, fmt.Errorf("entry detail found without active batch header at line %d", lineNum)
			}
			txCode, _ := strconv.Atoi(line[1:3])
			routing8 := line[3:11]
			chkDigit := line[11:12]
			acct := strings.TrimSpace(line[12:29])
			amt, _ := strconv.ParseInt(line[29:39], 10, 64)
			indID := strings.TrimSpace(line[39:54])
			indName := strings.TrimSpace(line[54:76])
			disc := strings.TrimSpace(line[76:78])
			trace := strings.TrimSpace(line[79:94])

			// Validate full 9-digit ABA
			fullAba := routing8 + chkDigit
			if !ValidateAbaRoutingNumber(fullAba) {
				return nil, fmt.Errorf("%w for ABA %s at line %d", ErrInvalidAbaChecksum, fullAba, lineNum)
			}

			entry := ACHEntryDetail{
				TransactionCode:    TransactionCode(txCode),
				ReceivingDfiRouting: routing8,
				CheckDigit:         chkDigit,
				DfiAccountNumber:   acct,
				AmountCents:        amt,
				IndividualID:       indID,
				IndividualName:     indName,
				DiscretionaryData:  disc,
				TraceNumber:        trace,
			}
			currentBatch.Entries = append(currentBatch.Entries, entry)

		case '7': // Addenda
			if currentBatch == nil || len(currentBatch.Entries) == 0 {
				return nil, fmt.Errorf("addenda found without parent entry detail at line %d", lineNum)
			}
			addendaInfo := strings.TrimSpace(line[3:83])
			lastIdx := len(currentBatch.Entries) - 1
			currentBatch.Entries[lastIdx].AddendaInformation = addendaInfo

		case '8': // Batch Control
			if currentBatch == nil {
				return nil, fmt.Errorf("batch control found without active batch at line %d", lineNum)
			}
			achFile.Batches = append(achFile.Batches, *currentBatch)
			currentBatch = nil
			batchCount++

		case '9': // File Control or Pad Line
			if strings.HasPrefix(line, "9999999999") {
				// Block padding line, ignore
				continue
			}
			// File Control: verify batch count
			fcBatches, _ := strconv.Atoi(line[1:7])
			if fcBatches != batchCount {
				return nil, fmt.Errorf("%w: batch count header %d vs actual %d", ErrFileControlMismatch, fcBatches, batchCount)
			}

		default:
			return nil, fmt.Errorf("%w: '%c' at line %d", ErrInvalidRecordType, recType, lineNum)
		}
	}

	if achFile == nil {
		return nil, errors.New("empty or invalid ACH file stream")
	}

	return achFile, nil
}

func padRight(s string, l int) string {
	if len(s) >= l {
		return s[:l]
	}
	return s + strings.Repeat(" ", l-len(s))
}

func padTo94(s string) string {
	if len(s) >= 94 {
		return s[:94]
	}
	return s + strings.Repeat(" ", 94-len(s))
}
