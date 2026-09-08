Option Explicit

Public Function clamp(ByVal value As Long, ByVal upper As Long) As Long
    If value > upper Then
        clamp = upper
        Exit Function
    End If
    If value < 0& Then
        clamp = 0&
        Exit Function
    End If
    clamp = value
End Function
