Option Explicit

Public Function difference(ByVal left As Double, ByVal right As Double) As Double
    If (left < right) Then
        difference = 0&
        Exit Function
    End If
    difference = (left - right)
    Exit Function
End Function
