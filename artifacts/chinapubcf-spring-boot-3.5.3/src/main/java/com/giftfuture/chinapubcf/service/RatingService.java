package com.giftfuture.chinapubcf.service;

import com.giftfuture.chinapubcf.model.Rating;
import com.giftfuture.chinapubcf.repository.BookRepository;
import com.giftfuture.chinapubcf.repository.RatingRepository;
import com.giftfuture.chinapubcf.repository.UserRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

@Service
public class RatingService {
    private final RatingRepository ratings;
    private final BookRepository books;
    private final UserRepository users;
    private final Clock clock;

    public RatingService(RatingRepository ratings, BookRepository books, UserRepository users) {
        this.ratings = ratings;
        this.books = books;
        this.users = users;
        this.clock = Clock.systemUTC();
    }

    @Transactional
    public int record(long authenticatedUserId, long requestedUserId, String encodedRatings) {
        if (authenticatedUserId != requestedUserId) {
            throw new SecurityException("cannot rate books for another user");
        }
        if (users.findById(authenticatedUserId).isEmpty()) {
            throw new IllegalArgumentException("unknown user");
        }
        List<Rating> parsed = parse(authenticatedUserId, encodedRatings);
        List<Long> bookIds = parsed.stream().map(Rating::bookId).distinct().toList();
        if (books.findByIds(bookIds).size() != bookIds.size()) {
            throw new IllegalArgumentException("one or more books do not exist");
        }
        parsed.forEach(ratings::upsert);
        return parsed.size();
    }

    private List<Rating> parse(long userId, String encodedRatings) {
        if (encodedRatings == null || encodedRatings.isBlank()) {
            throw new IllegalArgumentException("bookIdScores is required");
        }
        if (encodedRatings.length() > 4096) {
            throw new IllegalArgumentException("bookIdScores is too large");
        }
        List<Rating> result = new ArrayList<>();
        for (String token : encodedRatings.split(",")) {
            String[] pair = token.trim().split("-", -1);
            if (pair.length != 2) {
                throw new IllegalArgumentException("each rating must use bookId-score format");
            }
            long bookId = Long.parseLong(pair[0]);
            double score = Double.parseDouble(pair[1]);
            result.add(new Rating(userId, bookId, score, LocalDateTime.now(clock)));
        }
        if (result.stream().map(Rating::bookId).distinct().count() != result.size()) {
            throw new IllegalArgumentException("duplicate book ratings are not allowed");
        }
        return result;
    }
}
