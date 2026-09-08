Option Explicit

Public Function clamp(ByVal elmos_p000_4b633ab633208330 As Long, ByVal upper As Long) As Long
    If (elmos_p000_4b633ab633208330 > upper) Then
        clamp = upper
        Exit Function
    End If
    If (elmos_p000_4b633ab633208330 < 0&) Then
        clamp = 0&
        Exit Function
    End If
    clamp = elmos_p000_4b633ab633208330
    Exit Function
End Function
