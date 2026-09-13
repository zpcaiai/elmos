from elmos_spring_modernization.security_filter_chain import SecurityFilterChainExtractor

def test_extract_security():
    extractor = SecurityFilterChainExtractor()
    config = extractor.extract([{"pattern": "/api/**", "rule": "authenticated"}])
    assert "/api/**" in config.filter_chain_rules
    assert config.filter_chain_rules["/api/**"] == "authenticated"

def test_extract_too_many():
    extractor = SecurityFilterChainExtractor()
    try:
        extractor.extract([{"pattern": f"/api/{i}", "rule": "auth"} for i in range(501)])
        assert False
    except ValueError:
        assert True
