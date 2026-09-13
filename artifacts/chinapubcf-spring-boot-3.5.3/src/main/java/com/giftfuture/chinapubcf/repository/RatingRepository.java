package com.giftfuture.chinapubcf.repository;

import com.giftfuture.chinapubcf.model.Rating;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.sql.Timestamp;
import java.util.List;

@Repository
public class RatingRepository {
    private final JdbcTemplate jdbc;

    public RatingRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<Rating> findAll() {
        return jdbc.query("""
                SELECT user_id, book_id, rating, rated_at
                FROM rating
                ORDER BY user_id, book_id
                """, (rs, rowNum) -> new Rating(
                rs.getLong("user_id"),
                rs.getLong("book_id"),
                rs.getDouble("rating"),
                rs.getTimestamp("rated_at").toLocalDateTime()));
    }

    public List<Rating> findByUser(long userId) {
        return jdbc.query("""
                SELECT user_id, book_id, rating, rated_at
                FROM rating WHERE user_id = ? ORDER BY book_id
                """, (rs, rowNum) -> new Rating(
                rs.getLong("user_id"),
                rs.getLong("book_id"),
                rs.getDouble("rating"),
                rs.getTimestamp("rated_at").toLocalDateTime()), userId);
    }

    public void upsert(Rating rating) {
        jdbc.update("DELETE FROM rating WHERE user_id = ? AND book_id = ?", rating.userId(), rating.bookId());
        jdbc.update("""
                INSERT INTO rating (user_id, book_id, rating, rated_at) VALUES (?, ?, ?, ?)
                """, rating.userId(), rating.bookId(), rating.score(), Timestamp.valueOf(rating.ratedAt()));
    }
}
