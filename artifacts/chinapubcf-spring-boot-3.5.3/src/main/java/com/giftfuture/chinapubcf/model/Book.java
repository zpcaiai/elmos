package com.giftfuture.chinapubcf.model;

import java.math.BigDecimal;

public record Book(
        long bookId,
        String originalName,
        String author,
        String name,
        String translator,
        String press,
        String seriesName,
        String isbn,
        String pressTime,
        String version,
        String shelfTime,
        String category,
        BigDecimal price,
        BigDecimal vipPrice,
        BigDecimal schoolPrice,
        String activity,
        int sales) {
}
