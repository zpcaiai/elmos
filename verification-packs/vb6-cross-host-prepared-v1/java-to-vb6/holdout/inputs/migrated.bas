Option Explicit

Public Function clamp(ByVal elmos_p000_1f0b13e56dc4f6e4 As Long, ByVal upper As Long) As Long
    If (elmos_p000_1f0b13e56dc4f6e4 > upper) Then
        clamp = upper
        Exit Function
    End If
    If (elmos_p000_1f0b13e56dc4f6e4 < 0&) Then
        clamp = 0&
        Exit Function
    End If
    clamp = elmos_p000_1f0b13e56dc4f6e4
    Exit Function
End Function
