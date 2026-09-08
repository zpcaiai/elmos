Option Explicit

Public Function clamp(ByVal elmos_p000_e333a42324d21287 As Long, ByVal upper As Long) As Long
    If (elmos_p000_e333a42324d21287 > upper) Then
        clamp = upper
        Exit Function
    End If
    If (elmos_p000_e333a42324d21287 < 0&) Then
        clamp = 0&
        Exit Function
    End If
    clamp = elmos_p000_e333a42324d21287
    Exit Function
End Function
