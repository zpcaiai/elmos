Option Explicit

Public Function clamp(ByVal elmos_p000_25e5a410d12dc767 As Long, ByVal upper As Long) As Long
    If (elmos_p000_25e5a410d12dc767 > upper) Then
        clamp = upper
        Exit Function
    End If
    If (elmos_p000_25e5a410d12dc767 < 0&) Then
        clamp = 0&
        Exit Function
    End If
    clamp = elmos_p000_25e5a410d12dc767
    Exit Function
End Function
