from elmos_spring_modernization.bean_dependency_graph import BeanDependencyGraphExtractor

def test_extract_graph():
    extractor = BeanDependencyGraphExtractor()
    graph = extractor.extract([{"name": "beanA", "dependencies": [{"target": "beanB"}]}])
    assert len(graph.nodes) == 1
    assert graph.nodes[0].name == "beanA"
    assert len(graph.edges) == 1
    assert graph.edges[0].target == "beanB"

def test_extract_too_many():
    extractor = BeanDependencyGraphExtractor()
    try:
        extractor.extract([{"name": f"bean{i}"} for i in range(1001)])
        assert False
    except ValueError:
        assert True
