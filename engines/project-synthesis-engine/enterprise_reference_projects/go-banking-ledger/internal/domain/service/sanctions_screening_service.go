package service

import (
	"fmt"
	"math"
	"strings"
	"time"
	"unicode"
)

// SanctionAction represents the enforcement action determined by the screening engine.
type SanctionAction string

const (
	ActionPass   SanctionAction = "PASS"
	ActionReview SanctionAction = "MANUAL_REVIEW_REQUIRED"
	ActionBlock  SanctionAction = "BLOCKED_TRANSACTION"
)

// SanctionListType specifies the regulatory authority / source of the watch list.
type SanctionListType string

const (
	ListOFAC_SDN SanctionListType = "OFAC_SDN"
	ListEU_FSF   SanctionListType = "EU_FINANCIAL_SANCTIONS"
	ListUN_SC    SanctionListType = "UN_SECURITY_COUNCIL"
	ListPEP      SanctionListType = "POLITICALLY_EXPOSED_PERSONS"
)

// WatchlistEntity represents a sanctioned individual, organization, or vessel.
type WatchlistEntity struct {
	ID             string
	PrimaryName    string
	Aliases        []string
	EntityType     string // INDIVIDUAL, ENTITY, VESSEL
	CountryCodes   []string
	ListType       SanctionListType
	Programs       []string
	DateOfBirth    string
	NationalIDNum  string
}

// ScreeningRequest contains the transaction parties to be evaluated.
type ScreeningRequest struct {
	TransactionID    string
	DebtorName       string
	DebtorCountry    string
	CreditorName     string
	CreditorCountry  string
	OriginatingBIC   string
	BeneficiaryBIC   string
	RemittanceInfo   string
}

// MatchedCandidate represents an individual match candidate found during screening.
type MatchedCandidate struct {
	EntityID         string
	MatchedName      string
	InputName        string
	ListType         SanctionListType
	ConfidenceScore  float64 // 0.0 to 1.0
	MatchReason      string
}

// ScreeningResult summarizes the outcome of the sanctions screening evaluation.
type ScreeningResult struct {
	TransactionID   string
	Action          SanctionAction
	Matches         []MatchedCandidate
	BlockedCountries []string
	EvaluatedAt     time.Time
	ExecutionTimeMs int64
}

// SanctionsScreeningEngine provides high-throughput real-time name matching.
type SanctionsScreeningEngine struct {
	watchlist        []WatchlistEntity
	embargoedCountries map[string]bool
	exactMatchThreshold float64
	fuzzyMatchThreshold float64
}

func NewSanctionsScreeningEngine() *SanctionsScreeningEngine {
	engine := &SanctionsScreeningEngine{
		watchlist:        make([]WatchlistEntity, 0),
		embargoedCountries: map[string]bool{
			"IR": true, // Iran
			"KP": true, // North Korea
			"CU": true, // Cuba
			"SY": true, // Syria
			"RU": false, // Sectoral sanctions
		},
		exactMatchThreshold: 0.95,
		fuzzyMatchThreshold: 0.82,
	}
	engine.seedStandardSanctionsList()
	return engine
}

// AddWatchlistEntity registers an entity into the screening memory database.
func (e *SanctionsScreeningEngine) AddWatchlistEntity(entity WatchlistEntity) {
	e.watchlist = append(e.watchlist, entity)
}

// ScreenTransaction evaluates all parties in a transaction against watchlists and embargo rules.
func (e *SanctionsScreeningEngine) ScreenTransaction(req ScreeningRequest) ScreeningResult {
	startTime := time.Now()
	var matches []MatchedCandidate
	var blockedCountries []string

	// 1. Embargoed Country Check
	if e.embargoedCountries[strings.ToUpper(req.DebtorCountry)] {
		blockedCountries = append(blockedCountries, strings.ToUpper(req.DebtorCountry))
	}
	if e.embargoedCountries[strings.ToUpper(req.CreditorCountry)] {
		blockedCountries = append(blockedCountries, strings.ToUpper(req.CreditorCountry))
	}

	// 2. Name Matching for Debtor
	if req.DebtorName != "" {
		debtorMatches := e.searchWatchlist(req.DebtorName, "DEBTOR")
		matches = append(matches, debtorMatches...)
	}

	// 3. Name Matching for Creditor
	if req.CreditorName != "" {
		creditorMatches := e.searchWatchlist(req.CreditorName, "CREDITOR")
		matches = append(matches, creditorMatches...)
	}

	// 4. Remittance Information Scanning
	if req.RemittanceInfo != "" {
		remittanceMatches := e.searchWatchlist(req.RemittanceInfo, "REMITTANCE_INFO")
		matches = append(matches, remittanceMatches...)
	}

	// Determine enforcement action
	action := ActionPass
	if len(blockedCountries) > 0 {
		action = ActionBlock
	} else {
		for _, m := range matches {
			if m.ConfidenceScore >= e.exactMatchThreshold {
				action = ActionBlock
				break
			} else if m.ConfidenceScore >= e.fuzzyMatchThreshold {
				if action != ActionBlock {
					action = ActionReview
				}
			}
		}
	}

	elapsed := time.Since(startTime).Milliseconds()

	return ScreeningResult{
		TransactionID:   req.TransactionID,
		Action:          action,
		Matches:         matches,
		BlockedCountries: blockedCountries,
		EvaluatedAt:     time.Now().UTC(),
		ExecutionTimeMs: elapsed,
	}
}

func (e *SanctionsScreeningEngine) searchWatchlist(queryName, partyRole string) []MatchedCandidate {
	var results []MatchedCandidate
	normalizedQuery := e.normalizeString(queryName)
	if normalizedQuery == "" {
		return results
	}

	for _, entity := range e.watchlist {
		// Check primary name
		score := e.calculateSimilarity(normalizedQuery, e.normalizeString(entity.PrimaryName))
		if score >= e.fuzzyMatchThreshold {
			results = append(results, MatchedCandidate{
				EntityID:        entity.ID,
				MatchedName:     entity.PrimaryName,
				InputName:       queryName,
				ListType:        entity.ListType,
				ConfidenceScore: score,
				MatchReason:     fmt.Sprintf("%s primary name match (score: %.3f)", partyRole, score),
			})
			continue
		}

		// Check aliases
		for _, alias := range entity.Aliases {
			aliasScore := e.calculateSimilarity(normalizedQuery, e.normalizeString(alias))
			if aliasScore >= e.fuzzyMatchThreshold {
				results = append(results, MatchedCandidate{
					EntityID:        entity.ID,
					MatchedName:     alias,
					InputName:       queryName,
					ListType:        entity.ListType,
					ConfidenceScore: aliasScore,
					MatchReason:     fmt.Sprintf("%s alias match (score: %.3f)", partyRole, aliasScore),
				})
				break
			}
		}
	}

	return results
}

// normalizeString removes punctuation, collapses whitespace, and converts to uppercase.
func (e *SanctionsScreeningEngine) normalizeString(s string) string {
	var builder strings.Builder
	for _, r := range strings.ToUpper(s) {
		if unicode.IsLetter(r) || unicode.IsDigit(r) || unicode.IsSpace(r) {
			builder.WriteRune(r)
		}
	}
	return strings.Join(strings.Fields(builder.String()), " ")
}

// calculateSimilarity computes a hybrid score using Jaro-Winkler and Levenshtein distance.
func (e *SanctionsScreeningEngine) calculateSimilarity(s1, s2 string) float64 {
	if s1 == s2 {
		return 1.0
	}
	if len(s1) == 0 || len(s2) == 0 {
		return 0.0
	}

	jwScore := e.jaroWinkler(s1, s2)
	levRatio := 1.0 - (float64(e.levenshteinDistance(s1, s2)) / float64(int(math.Max(float64(len(s1)), float64(len(s2))))))

	// Weighted combination: 70% Jaro-Winkler, 30% Levenshtein ratio
	return 0.70*jwScore + 0.30*levRatio
}

// jaroWinkler computes string distance with prefix scaling.
func (e *SanctionsScreeningEngine) jaroWinkler(s1, s2 string) float64 {
	jaroScore := e.jaroDistance(s1, s2)
	if jaroScore < 0.7 {
		return jaroScore
	}

	// Compute common prefix length up to 4 characters
	prefixLen := 0
	maxPrefix := int(math.Min(4.0, math.Min(float64(len(s1)), float64(len(s2)))))
	for i := 0; i < maxPrefix; i++ {
		if s1[i] == s2[i] {
			prefixLen++
		} else {
			break
		}
	}

	scalingFactor := 0.1
	return jaroScore + float64(prefixLen)*scalingFactor*(1.0-jaroScore)
}

func (e *SanctionsScreeningEngine) jaroDistance(s1, s2 string) float64 {
	len1, len2 := len(s1), len(s2)
	if len1 == 0 && len2 == 0 {
		return 1.0
	}
	if len1 == 0 || len2 == 0 {
		return 0.0
	}

	matchDistance := int(math.Max(float64(len1), float64(len2)))/2 - 1
	if matchDistance < 0 {
		matchDistance = 0
	}

	s1Matches := make([]bool, len1)
	s2Matches := make([]bool, len2)
	matches := 0

	for i := 0; i < len1; i++ {
		start := int(math.Max(0.0, float64(i-matchDistance)))
		end := int(math.Min(float64(i+matchDistance+1), float64(len2)))

		for j := start; j < end; j++ {
			if s2Matches[j] || s1[i] != s2[j] {
				continue
			}
			s1Matches[i] = true
			s2Matches[j] = true
			matches++
			break
		}
	}

	if matches == 0 {
		return 0.0
	}

	transpositions := 0
	k := 0
	for i := 0; i < len1; i++ {
		if !s1Matches[i] {
			continue
		}
		for !s2Matches[k] {
			k++
		}
		if s1[i] != s2[k] {
			transpositions++
		}
		k++
	}

	m := float64(matches)
	return (m/float64(len1) + m/float64(len2) + (m-float64(transpositions)/2.0)/m) / 3.0
}

func (e *SanctionsScreeningEngine) levenshteinDistance(s1, s2 string) int {
	r1, r2 := []rune(s1), []rune(s2)
	len1, len2 := len(r1), len(r2)

	dp := make([][]int, len1+1)
	for i := range dp {
		dp[i] = make([]int, len2+1)
		dp[i][0] = i
	}
	for j := 0; j <= len2; j++ {
		dp[0][j] = j
	}

	for i := 1; i <= len1; i++ {
		for j := 1; j <= len2; j++ {
			cost := 0
			if r1[i-1] != r2[j-1] {
				cost = 1
			}
			dp[i][j] = int(math.Min(
				float64(dp[i-1][j]+1),
				math.Min(float64(dp[i][j-1]+1), float64(dp[i-1][j-1]+cost)),
			))
		}
	}

	return dp[len1][len2]
}

func (e *SanctionsScreeningEngine) seedStandardSanctionsList() {
	e.AddWatchlistEntity(WatchlistEntity{
		ID:          "SDN-1001",
		PrimaryName: "QASSEM SOLEIMANI",
		Aliases:     []string{"GHASEM SOLEIMANI", "KASIM SULAYMANI"},
		EntityType:  "INDIVIDUAL",
		ListType:    ListOFAC_SDN,
		Programs:    []string{"IRAN-HR", "SDGT"},
	})
	e.AddWatchlistEntity(WatchlistEntity{
		ID:          "SDN-1002",
		PrimaryName: "BANK MELLI IRAN",
		Aliases:     []string{"MELLI BANK", "NATIONAL BANK OF IRAN"},
		EntityType:  "ENTITY",
		ListType:    ListOFAC_SDN,
		Programs:    []string{"NPWMD", "IRAN"},
	})
	e.AddWatchlistEntity(WatchlistEntity{
		ID:          "PEP-2001",
		PrimaryName: "ALEXANDER LUKASHENKO",
		Aliases:     []string{"ALEKSANDR LUKASHENKA"},
		EntityType:  "INDIVIDUAL",
		ListType:    ListPEP,
		Programs:    []string{"BELARUS"},
	})
}
