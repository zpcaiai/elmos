package com.giftfuture.chinapubcf.service;

import com.giftfuture.chinapubcf.model.UserAccount;
import com.giftfuture.chinapubcf.repository.UserRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Locale;
import java.util.Optional;
import java.util.regex.Pattern;

@Service
public class AccountService {
    private static final Pattern NAME = Pattern.compile("[\\p{L}\\p{N}_]{4,20}");
    private static final Pattern EMAIL = Pattern.compile("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$");

    private final UserRepository users;
    private final PasswordService passwords;

    public AccountService(UserRepository users, PasswordService passwords) {
        this.users = users;
        this.passwords = passwords;
    }

    @Transactional
    public UserAccount register(Registration registration) {
        String name = normalized(registration.name());
        String email = normalized(registration.email()).toLowerCase(Locale.ROOT);
        if (!NAME.matcher(name).matches()) {
            throw new IllegalArgumentException("name must contain 4-20 letters, numbers, or underscores");
        }
        if (!EMAIL.matcher(email).matches()) {
            throw new IllegalArgumentException("email is invalid");
        }
        return users.insert(name, email, passwords.encode(registration.password()),
                normalized(registration.status()), normalized(registration.admireField()),
                normalized(registration.expertAt()), normalized(registration.tag()),
                normalized(registration.knowFrom()));
    }

    @Transactional
    public Optional<UserAccount> authenticate(String login, String rawPassword) {
        if (login == null || rawPassword == null) {
            return Optional.empty();
        }
        Optional<UserAccount> account = users.findByLogin(login);
        if (account.isEmpty() || !passwords.matches(rawPassword, account.get().passwordHash())) {
            return Optional.empty();
        }
        UserAccount authenticated = account.get();
        if (passwords.needsUpgrade(authenticated.passwordHash())) {
            users.updatePasswordHash(authenticated.userId(), passwords.encodeVerifiedLegacy(rawPassword));
            authenticated = users.findById(authenticated.userId()).orElseThrow();
        }
        return Optional.of(authenticated);
    }

    public Optional<UserAccount> findById(long userId) {
        return users.findById(userId);
    }

    private static String normalized(String value) {
        return value == null ? "" : value.trim();
    }

    public record Registration(String name, String email, String password, String status,
                               String admireField, String expertAt, String tag, String knowFrom) {
    }
}
