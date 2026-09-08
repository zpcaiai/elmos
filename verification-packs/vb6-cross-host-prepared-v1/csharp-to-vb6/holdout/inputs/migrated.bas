Option Explicit

Public Function clamp(ByVal elmos_p000_c97ea5c6fc7ad1d8 As Long, ByVal upper As Long) As Long
    If (elmos_p000_c97ea5c6fc7ad1d8 > upper) Then
        clamp = upper
        Exit Function
    End If
    If (elmos_p000_c97ea5c6fc7ad1d8 < 0&) Then
        clamp = 0&
        Exit Function
    End If
    clamp = elmos_p000_c97ea5c6fc7ad1d8
    Exit Function
End Function
