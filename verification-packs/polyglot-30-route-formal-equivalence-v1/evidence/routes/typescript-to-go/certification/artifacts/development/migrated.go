package main

func calculate(subtotal float64, tax float64) float64 {
    if (subtotal < 0) {
        return 0
    }
    return (subtotal + tax)
}
