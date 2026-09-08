Option Explicit

Public Function clamp(ByVal elmos_p000_9d17e8ab7ab7e60c As Long, ByVal upper As Long) As Long
    If (elmos_p000_9d17e8ab7ab7e60c > upper) Then
        clamp = upper
        Exit Function
    End If
    If (elmos_p000_9d17e8ab7ab7e60c < 0&) Then
        clamp = 0&
        Exit Function
    End If
    clamp = elmos_p000_9d17e8ab7ab7e60c
    Exit Function
End Function
