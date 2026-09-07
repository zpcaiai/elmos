package equivalencemodule

func calculate(subtotal int64, tax int64) int64 {
	if subtotal < 0 { return 0 }
	return subtotal + tax
}

func clamp(value int64, minimum int64, maximum int64) int64 {
	if value < minimum { return minimum }
	if value > maximum { return maximum }
	return value
}

func difference(left int64, right int64) int64 { return left - right }

func clampNumber(value float64, minimum float64, maximum float64) float64 {
	if value < minimum { return minimum }
	if value > maximum { return maximum }
	return value
}

func both(left bool, right bool) bool { return left && right }
