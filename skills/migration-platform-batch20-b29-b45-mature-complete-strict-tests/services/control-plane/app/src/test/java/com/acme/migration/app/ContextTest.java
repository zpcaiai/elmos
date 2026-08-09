package com.acme.migration.app;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ContextTest {
    @Test
    void applicationClassExists() {
        assertThat(ControlPlaneApplication.class).isNotNull();
    }
}
