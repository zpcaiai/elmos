fun clamp(elmos_p000_2afc4ead0168ca70: Long, upper: Long): Long {
    if ((elmos_p000_2afc4ead0168ca70 > upper)) {
        return upper
    }
    if ((elmos_p000_2afc4ead0168ca70 < 0L)) {
        return 0L
    }
    return elmos_p000_2afc4ead0168ca70
}
