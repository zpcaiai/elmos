Option Explicit

Public Function clamp(ByVal elmos_p000_8dea336387faa973 As Double, ByVal upper As Double) As Double
    If (elmos_p000_8dea336387faa973 > upper) Then
        clamp = upper
        Exit Function
    End If
    If (elmos_p000_8dea336387faa973 < 0&) Then
        clamp = 0&
        Exit Function
    End If
    clamp = elmos_p000_8dea336387faa973
    Exit Function
End Function
