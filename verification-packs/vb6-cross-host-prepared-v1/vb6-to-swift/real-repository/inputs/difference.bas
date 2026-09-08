Option Explicit

Public Function difference(ByVal left As Long, ByVal right As Long) As Long
    If left < right Then
        difference = 0&
        Exit Function
    End If
    difference = left - right
End Function
