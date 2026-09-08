Option Explicit

Public Function calculate(ByVal subtotal As Long, ByVal tax As Long) As Long
    If (subtotal < 0&) Then
        calculate = 0&
        Exit Function
    End If
    calculate = ElmosCheckedAdd(subtotal, tax)
    Exit Function
End Function

Private Function ElmosCheckedAdd(ByVal leftValue As Long, ByVal rightValue As Long) As Long
    Dim resultValue As Double
    resultValue = CDbl(leftValue) + CDbl(rightValue)
    If resultValue < -2147483648# Or resultValue > 2147483647# Then Err.Raise 6, "ElmosCheckedAdd", "ELMOS_INTEGER_OVERFLOW"
    ElmosCheckedAdd = CLng(resultValue)
End Function
