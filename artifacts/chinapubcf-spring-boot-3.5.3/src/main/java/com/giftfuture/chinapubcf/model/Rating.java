package com.giftfuture.chinapubcf.model;

import java.time.LocalDateTime;

public record Rating(long userId, long bookId, double score, LocalDateTime ratedAt) {
    public Rating {
        if (score < 1.0 || score > 5.0) {
            throw new IllegalArgumentException("score must be between 1 and 5");
        }
    }
}
