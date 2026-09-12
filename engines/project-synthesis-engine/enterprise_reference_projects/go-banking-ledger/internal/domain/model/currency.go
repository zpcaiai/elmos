package model

import (
	"errors"
	"fmt"
	"math"
	"sync"
	"time"
)

// PostingDirection designates Debit or Credit in double-entry bookkeeping.
type PostingDirection string

const (
	DirectionDebit  PostingDirection = "DEBIT"
	DirectionCredit PostingDirection = "CREDIT"
)

// CurrencySpec specifies the metadata for an ISO-4217 compliant currency.
type CurrencySpec struct {
	Code      string `json:"code"`
	Numeric   string `json:"numeric"`
	Decimals  int    `json:"decimals"`
	Symbol    string `json:"symbol"`
	ScaleUnit int64  `json:"scale_unit"` // 10^Decimals
}

var (
	ErrUnknownCurrency = errors.New("unknown currency code")
	ErrInvalidFXRate   = errors.New("fx exchange rate must be strictly positive")
	ErrRateExpired     = errors.New("fx exchange rate has expired")
)

var defaultCurrencies = map[string]CurrencySpec{
	"USD": {Code: "USD", Numeric: "840", Decimals: 2, Symbol: "$", ScaleUnit: 100},
	"EUR": {Code: "EUR", Numeric: "978", Decimals: 2, Symbol: "€", ScaleUnit: 100},
	"GBP": {Code: "GBP", Numeric: "826", Decimals: 2, Symbol: "£", ScaleUnit: 100},
	"JPY": {Code: "JPY", Numeric: "392", Decimals: 0, Symbol: "¥", ScaleUnit: 1},
	"CNY": {Code: "CNY", Numeric: "156", Decimals: 2, Symbol: "¥", ScaleUnit: 100},
	"HKD": {Code: "HKD", Numeric: "344", Decimals: 2, Symbol: "HK$", ScaleUnit: 100},
	"SGD": {Code: "SGD", Numeric: "702", Decimals: 2, Symbol: "S$", ScaleUnit: 100},
	"AUD": {Code: "AUD", Numeric: "036", Decimals: 2, Symbol: "A$", ScaleUnit: 100},
	"CAD": {Code: "CAD", Numeric: "124", Decimals: 2, Symbol: "C$", ScaleUnit: 100},
	"CHF": {Code: "CHF", Numeric: "756", Decimals: 2, Symbol: "CHF", ScaleUnit: 100},
}

// CurrencyRegistry manages allowed system currencies and their scale units.
type CurrencyRegistry struct {
	mu         sync.RWMutex
	currencies map[string]CurrencySpec
}

func NewCurrencyRegistry() *CurrencyRegistry {
	r := &CurrencyRegistry{
		currencies: make(map[string]CurrencySpec),
	}
	for k, v := range defaultCurrencies {
		r.currencies[k] = v
	}
	return r
}

func (r *CurrencyRegistry) Register(spec CurrencySpec) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if spec.ScaleUnit == 0 {
		spec.ScaleUnit = int64(math.Pow10(spec.Decimals))
	}
	r.currencies[spec.Code] = spec
}

func (r *CurrencyRegistry) Get(code string) (CurrencySpec, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	spec, found := r.currencies[code]
	if !found {
		return CurrencySpec{}, fmt.Errorf("%w: %s", ErrUnknownCurrency, code)
	}
	return spec, nil
}

// FXRate holds an exchange rate between base currency and quote currency.
type FXRate struct {
	BaseCurrency  string    `json:"base_currency"`
	QuoteCurrency string    `json:"quote_currency"`
	Rate          float64   `json:"rate"` // Rate = Quote / Base
	EffectiveFrom time.Time `json:"effective_from"`
	ExpiresAt     time.Time `json:"expires_at"`
}

// Convert converts a base amount in minor units to quote amount in minor units using Banker's rounding.
func (fx *FXRate) Convert(baseAmount int64, baseSpec, quoteSpec CurrencySpec) (int64, error) {
	if fx.Rate <= 0 {
		return 0, ErrInvalidFXRate
	}
	now := time.Now().UTC()
	if now.After(fx.ExpiresAt) {
		return 0, ErrRateExpired
	}

	// Step 1: Base minor units to major units
	baseMajor := float64(baseAmount) / float64(baseSpec.ScaleUnit)

	// Step 2: Multiply by rate
	quoteMajor := baseMajor * fx.Rate

	// Step 3: Convert to quote minor units with Banker's Rounding (round half to even)
	quoteMinorFloat := quoteMajor * float64(quoteSpec.ScaleUnit)
	return roundHalfToEven(quoteMinorFloat), nil
}

// roundHalfToEven implements IEEE-754 round-to-nearest, ties-to-even (Banker's rounding).
func roundHalfToEven(val float64) int64 {
	floor := math.Floor(val)
	diff := val - floor

	if diff < 0.5 {
		return int64(floor)
	} else if diff > 0.5 {
		return int64(floor) + 1
	}

	// Tie break: if floor is odd, round up; if even, round down.
	floorInt := int64(floor)
	if floorInt%2 != 0 {
		return floorInt + 1
	}
	return floorInt
}

// FormatMinorUnits returns a display string like "12.34 USD" from an int64 minor unit.
func FormatMinorUnits(amount int64, spec CurrencySpec) string {
	if spec.Decimals == 0 {
		return fmt.Sprintf("%d %s", amount, spec.Code)
	}
	scale := spec.ScaleUnit
	isNegative := amount < 0
	if isNegative {
		amount = -amount
	}
	major := amount / scale
	minor := amount % scale

	formatStr := fmt.Sprintf("%%s%%d.%%0%dd %%s", spec.Decimals)
	sign := ""
	if isNegative {
		sign = "-"
	}
	return fmt.Sprintf(formatStr, sign, major, minor, spec.Code)
}
