Option Explicit

Public Function clamp(ByVal elmos_p000_14837bccd0cf8f05 As Long, ByVal upper As Long) As Long
    If (elmos_p000_14837bccd0cf8f05 > upper) Then
        clamp = upper
        Exit Function
    End If
    If (elmos_p000_14837bccd0cf8f05 < 0&) Then
        clamp = 0&
        Exit Function
    End If
    clamp = elmos_p000_14837bccd0cf8f05
    Exit Function
End Function
