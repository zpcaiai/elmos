package main

func difference(left float64, right float64) float64 {
    if (left < right) {
        return 0
    }
    return (left - right)
}
