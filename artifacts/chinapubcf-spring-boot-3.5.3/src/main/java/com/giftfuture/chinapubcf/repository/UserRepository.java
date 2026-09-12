package com.giftfuture.chinapubcf.repository;

import com.giftfuture.chinapubcf.model.UserAccount;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.util.Locale;
import java.util.Optional;

@Repository
public class UserRepository {
    private static final RowMapper<UserAccount> USER_MAPPER = (rs, rowNum) -> new UserAccount(
            rs.getLong("user_id"),
            rs.getString("name"),
            rs.getString("email"),
            rs.getString("password_hash"),
            rs.getString("status"),
            rs.getString("admire_field"),
            rs.getString("expert_at"),
            rs.getString("tag"),
            rs.getString("know_from"));

    private static final String SELECT = """
            SELECT user_id, name, email, password_hash, status, admire_field, expert_at, tag, know_from
            FROM app_user
            """;

    private final JdbcTemplate jdbc;

    public UserRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<UserAccount> findByLogin(String login) {
        String normalized = login.trim().toLowerCase(Locale.ROOT);
        return jdbc.query(SELECT + " WHERE LOWER(email) = ? OR LOWER(name) = ?", USER_MAPPER,
                normalized, normalized).stream().findFirst();
    }

    public Optional<UserAccount> findById(long id) {
        return jdbc.query(SELECT + " WHERE user_id = ?", USER_MAPPER, id).stream().findFirst();
    }

    public UserAccount insert(String name, String email, String passwordHash, String status,
                              String admireField, String expertAt, String tag, String knowFrom) {
        KeyHolder keys = new GeneratedKeyHolder();
        try {
            jdbc.update(connection -> {
                PreparedStatement statement = connection.prepareStatement("""
                        INSERT INTO app_user
                          (name, email, password_hash, status, admire_field, expert_at, tag, know_from)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, Statement.RETURN_GENERATED_KEYS);
                statement.setString(1, name);
                statement.setString(2, email.toLowerCase(Locale.ROOT));
                statement.setString(3, passwordHash);
                statement.setString(4, status);
                statement.setString(5, admireField);
                statement.setString(6, expertAt);
                statement.setString(7, tag);
                statement.setString(8, knowFrom);
                return statement;
            }, keys);
        } catch (DuplicateKeyException duplicate) {
            throw new IllegalArgumentException("name or email is already registered", duplicate);
        }
        Number id = keys.getKey();
        if (id == null) {
            throw new IllegalStateException("database did not return a user id");
        }
        return findById(id.longValue()).orElseThrow();
    }

    public void updatePasswordHash(long userId, String passwordHash) {
        jdbc.update("UPDATE app_user SET password_hash = ? WHERE user_id = ?", passwordHash, userId);
    }
}
