Option Explicit

Public Function clamp(ByVal elmos_p000_77b59b121580f2fc As Long, ByVal upper As Long) As Long
    If (elmos_p000_77b59b121580f2fc > upper) Then
        clamp = upper
        Exit Function
    End If
    If (elmos_p000_77b59b121580f2fc < 0&) Then
        clamp = 0&
        Exit Function
    End If
    clamp = elmos_p000_77b59b121580f2fc
    Exit Function
End Function
