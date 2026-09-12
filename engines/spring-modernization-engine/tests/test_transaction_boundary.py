from elmos_spring_modernization.transaction_boundary import TransactionBoundaryExtractor

def test_extract_tx():
    extractor = TransactionBoundaryExtractor()
    config = extractor.extract([{"name": "saveUser", "propagation": "REQUIRES_NEW"}])
    assert "saveUser" in config.method_policies
    assert config.method_policies["saveUser"].propagation == "REQUIRES_NEW"

def test_extract_too_many():
    extractor = TransactionBoundaryExtractor()
    try:
        extractor.extract([{"name": f"method{i}"} for i in range(501)])
        assert False
    except ValueError:
        assert True
