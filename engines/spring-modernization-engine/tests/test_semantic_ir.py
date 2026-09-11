from elmos_spring_modernization.semantic_ir import SpringSemanticExtractor

def test_extract_ir():
    extractor = SpringSemanticExtractor()
    ir = extractor.extract_full_ir("/tmp")
    assert ir is not None
