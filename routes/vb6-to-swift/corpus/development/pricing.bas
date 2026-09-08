Option Explicit

Public Function calculate(ByVal subtotal As Long, ByVal tax As Long) As Long
    If subtotal < 0& Then
        calculate = 0&
        Exit Function
    End If
    calculate = subtotal + tax
End Function
