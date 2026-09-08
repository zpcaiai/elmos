Option Explicit

Public Function difference(ByVal left As Long, ByVal right As Long) As Long
    If (left < right) Then
        difference = 0&
        Exit Function
    End If
    difference = ElmosCheckedSub(left, right)
    Exit Function
End Function

Private Function ElmosCheckedSub(ByVal leftValue As Long, ByVal rightValue As Long) As Long
    Dim resultValue As Double
    resultValue = CDbl(leftValue) - CDbl(rightValue)
    If resultValue < -2147483648# Or resultValue > 2147483647# Then Err.Raise 6, "ElmosCheckedSub", "ELMOS_INTEGER_OVERFLOW"
    ElmosCheckedSub = CLng(resultValue)
End Function
