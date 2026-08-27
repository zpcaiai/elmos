package io.elmos.recipes;

import org.junit.jupiter.api.Test;
import org.openrewrite.InMemoryExecutionContext;
import org.openrewrite.SourceFile;
import org.openrewrite.java.JavaParser;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SpringSecurityLambdaChainTest {
    @Test
    void movesHttpSecurityCallsAfterAndOutsideAuthorizationLambda() {
        String before = """
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;

                class SecurityConfig {
                    void configure(HttpSecurity http) throws Exception {
                        http.authorizeHttpRequests(requests -> requests
                                .requestMatchers(\"/public\").permitAll()
                                .anyRequest().authenticated()
                                .and()
                                .addFilterBefore(new ExceptionFilter(), ExceptionFilter.class)
                                .addFilter(new AuthenticationFilter()))
                            .addFilterAfter(new JwtFilter(), AuthenticationFilter.class);
                    }
                }
                class ExceptionFilter {}
                class AuthenticationFilter {}
                class JwtFilter {}
                """;
        SourceFile source = JavaParser.fromJavaVersion().build().parse(before).findFirst().orElseThrow();
        SourceFile transformed = (SourceFile) new SpringSecurityLambdaChain().getVisitor()
                .visit(source, new InMemoryExecutionContext());
        String normalized = transformed.printAll().replaceAll("\\s+", "");

        assertEquals(1, normalized.split("authorizeHttpRequests", -1).length - 1);
        org.junit.jupiter.api.Assertions.assertTrue(
                normalized.contains("authenticated()).addFilterBefore"));
        org.junit.jupiter.api.Assertions.assertFalse(
                normalized.contains("authenticated().and().addFilterBefore"));
    }

    @Test
    void mapsToolsJacksonExceptionCatchToIoException() {
        String sourceText = """
                import tools.jackson.core.JacksonException;
                import tools.jackson.databind.json.JsonMapper;

                class Parser {
                    void parse() {
                        try {
                            new JsonMapper().readValue(System.in, Object.class);
                        } catch (JacksonException error) {
                            throw new RuntimeException(error);
                        }
                    }
                }
                """;

        SourceFile source = JavaParser.fromJavaVersion().build().parse(sourceText).findFirst().orElseThrow();
        SourceFile transformed = (SourceFile) new SpringSecurityLambdaChain().getVisitor()
                .visit(source, new InMemoryExecutionContext());
        String normalized = transformed.printAll().replaceAll("\\s+", "");

        assertEquals(1, normalized.split("catch\\(IOException", -1).length - 1);
        org.junit.jupiter.api.Assertions.assertFalse(normalized.contains("JacksonException"));
    }
}
