from elmos_spring_modernization.security_filter_chain import SecurityFilterChainExtractor

def test_extract_security():
    extractor = SecurityFilterChainExtractor()
    config = extractor.extract([{"pattern": "/api/**", "rule": "authenticated"}])
    assert "/api/**" in config.filter_chain_rules
    assert config.filter_chain_rules["/api/**"] == "authenticated"
    assert "Standard" in config.posture_summary or "Hardened" in config.posture_summary

def test_extract_too_many():
    extractor = SecurityFilterChainExtractor()
    try:
        extractor.extract([{"pattern": f"/api/{i}", "rule": "auth"} for i in range(501)])
        assert False
    except ValueError:
        assert True

def test_extract_full_security_config():
    extractor = SecurityFilterChainExtractor()
    sources = [
        {"pattern": "/public/**", "rule": "permitAll"},
        {"pattern": "/admin/**", "rule": "hasRole('ADMIN')"},
        {"pattern": "/**", "rule": "authenticated"},
        {"auth_providers": ["jwtAuthenticationProvider", "ldapAuthenticationProvider"]},
        {"cors": {"allowedOrigins": "https://example.com", "allowCredentials": "true"}},
        {"csrf": {"enabled": "true", "tokenRepository": "CookieCsrfTokenRepository"}},
        {"custom_filters": ["JwtTokenValidationFilter", "RateLimitingFilter"]}
    ]
    config = extractor.extract(sources)
    assert len(config.filter_chain_rules) == 3
    assert "jwtAuthenticationProvider" in config.auth_providers
    assert "ldapAuthenticationProvider" in config.auth_providers
    assert config.cors_config["allowedOrigins"] == "https://example.com"
    assert config.csrf_config["enabled"] == "true"
    assert len(config.custom_filters) == 2
    assert "Hardened" in config.posture_summary or "Standard" in config.posture_summary

def test_critical_security_posture_findings():
    extractor = SecurityFilterChainExtractor()
    sources = [
        {"pattern": "/**", "rule": "permitAll"},
        {"cors": {"allowedOrigins": "*", "allowCredentials": "true"}},
        {"csrf": {"enabled": "false"}}
    ]
    config = extractor.extract(sources)
    assert "Elevated Risk" in config.posture_summary
    assert "CRITICAL: Root or wildcard path is configured with permitAll" in config.posture_summary
    assert "CRITICAL: CORS allows wildcard origin '*' combined with credentials" in config.posture_summary
    assert "WARNING: CSRF protection is disabled" in config.posture_summary
