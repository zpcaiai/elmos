package com.example.secjpa;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

public class SecurityJpaApplicationTest {
    @Test
    void userEntityConstructorWorks() {
        UserEntity user = new UserEntity(1L, "alice", "ADMIN");
        assertEquals("alice", user.getUsername());
        assertEquals("ADMIN", user.getRole());
    }
}
