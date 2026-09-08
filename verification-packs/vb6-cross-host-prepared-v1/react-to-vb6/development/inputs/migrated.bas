Option Explicit

Public Function calculate(ByVal subtotal As Double, ByVal tax As Double) As Double
    If (subtotal < 0&) Then
        calculate = 0&
        Exit Function
    End If
    calculate = (subtotal + tax)
    Exit Function
End Function
