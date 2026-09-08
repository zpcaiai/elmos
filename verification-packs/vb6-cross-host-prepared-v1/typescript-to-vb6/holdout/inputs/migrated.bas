Option Explicit

Public Function clamp(ByVal elmos_p000_dfd3b02e37382b77 As Double, ByVal upper As Double) As Double
    If (elmos_p000_dfd3b02e37382b77 > upper) Then
        clamp = upper
        Exit Function
    End If
    If (elmos_p000_dfd3b02e37382b77 < 0&) Then
        clamp = 0&
        Exit Function
    End If
    clamp = elmos_p000_dfd3b02e37382b77
    Exit Function
End Function
