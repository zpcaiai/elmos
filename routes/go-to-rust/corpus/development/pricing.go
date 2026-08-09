package pricing

func calculate(subtotal int64, tax int64) int64 {
	if subtotal < 0 {
		return 0
	}
	return subtotal + tax
}
