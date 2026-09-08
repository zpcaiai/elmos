package holdout

func clamp(value int64, upper int64) int64 {
	if value > upper {
		return upper
	}
	if value < 0 {
		return 0
	}
	return value
}
