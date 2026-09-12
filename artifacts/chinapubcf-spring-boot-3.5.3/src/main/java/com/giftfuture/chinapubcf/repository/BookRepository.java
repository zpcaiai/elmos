package com.giftfuture.chinapubcf.repository;

import com.giftfuture.chinapubcf.model.Book;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public class BookRepository {
    private static final RowMapper<Book> BOOK_MAPPER = (rs, rowNum) -> new Book(
            rs.getLong("book_id"),
            rs.getString("original_name"),
            rs.getString("author"),
            rs.getString("name"),
            rs.getString("translator"),
            rs.getString("press"),
            rs.getString("series_name"),
            rs.getString("isbn"),
            rs.getString("press_time"),
            rs.getString("version"),
            rs.getString("shelf_time"),
            rs.getString("category"),
            rs.getBigDecimal("price"),
            rs.getBigDecimal("vip_price"),
            rs.getBigDecimal("school_price"),
            rs.getString("activity"),
            rs.getInt("sales"));

    private static final String SELECT_COLUMNS = """
            SELECT b.book_id, b.original_name, b.author, b.name, b.translator, b.press, b.series_name,
                   b.isbn, b.press_time, b.version, b.shelf_time, b.category, b.price, b.vip_price,
                   b.school_price, b.activity, b.sales
            FROM book b
            """;

    private final JdbcTemplate jdbc;

    public BookRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public long count() {
        Long count = jdbc.queryForObject("SELECT COUNT(*) FROM book", Long.class);
        return count == null ? 0 : count;
    }

    public List<Book> findPage(int page, int size) {
        int offset = Math.multiplyExact(page - 1, size);
        return jdbc.query(SELECT_COLUMNS + " ORDER BY b.book_id LIMIT ? OFFSET ?", BOOK_MAPPER, size, offset);
    }

    public List<Book> findByUser(long userId) {
        return jdbc.query(SELECT_COLUMNS + """
                JOIN rating r ON r.book_id = b.book_id
                WHERE r.user_id = ?
                ORDER BY r.rated_at DESC, b.book_id
                """, BOOK_MAPPER, userId);
    }

    public List<Book> findByIds(List<Long> ids) {
        if (ids.isEmpty()) {
            return List.of();
        }
        String placeholders = String.join(",", java.util.Collections.nCopies(ids.size(), "?"));
        return jdbc.query(SELECT_COLUMNS + " WHERE b.book_id IN (" + placeholders + ") ORDER BY b.book_id",
                BOOK_MAPPER, ids.toArray());
    }
}
