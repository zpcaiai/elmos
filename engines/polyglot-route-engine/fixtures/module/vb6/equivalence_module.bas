Option Explicit

Public Function calculate(ByVal subtotal As Long, ByVal tax As Long) As Long
    If subtotal < 0& Then
        calculate = 0&
        Exit Function
    End If
    calculate = subtotal + tax
End Function

Public Function clamp(ByVal value As Long, ByVal minimum As Long, ByVal maximum As Long) As Long
    If value < minimum Then
        clamp = minimum
        Exit Function
    End If
    If value > maximum Then
        clamp = maximum
        Exit Function
    End If
    clamp = value
End Function

Public Function difference(ByVal left As Long, ByVal right As Long) As Long
    difference = left - right
End Function

Public Function clampNumber(ByVal value As Double, ByVal minimum As Double, ByVal maximum As Double) As Double
    If value < minimum Then
        clampNumber = minimum
        Exit Function
    End If
    If value > maximum Then
        clampNumber = maximum
        Exit Function
    End If
    clampNumber = value
End Function

Public Function both(ByVal left As Boolean, ByVal right As Boolean) As Boolean
    both = left And right
End Function
