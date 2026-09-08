Option Explicit

Public Function clamp(ByVal elmos_p000_eef833120f9b0b38 As Long, ByVal upper As Long) As Long
    If (elmos_p000_eef833120f9b0b38 > upper) Then
        clamp = upper
        Exit Function
    End If
    If (elmos_p000_eef833120f9b0b38 < 0&) Then
        clamp = 0&
        Exit Function
    End If
    clamp = elmos_p000_eef833120f9b0b38
    Exit Function
End Function
