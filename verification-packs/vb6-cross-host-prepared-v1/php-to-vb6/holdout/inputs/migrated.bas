Option Explicit

Public Function clamp(ByVal elmos_p000_8c8ea2b0760c4542 As Long, ByVal upper As Long) As Long
    If (elmos_p000_8c8ea2b0760c4542 > upper) Then
        clamp = upper
        Exit Function
    End If
    If (elmos_p000_8c8ea2b0760c4542 < 0&) Then
        clamp = 0&
        Exit Function
    End If
    clamp = elmos_p000_8c8ea2b0760c4542
    Exit Function
End Function
