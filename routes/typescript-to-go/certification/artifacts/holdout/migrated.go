package main

func clamp(value float64, upper float64) float64 {
    if (value > upper) {
        return upper
    }
    if (value < 0) {
        return 0
    }
    return value
}
