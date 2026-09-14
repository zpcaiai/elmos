from elmos_spring_modernization.bean_dependency_graph import (
    BeanDependencyGraphExtractor,
    DependencyType,
    BeanNode,
    BeanEdge
)

def test_extract_graph():
    extractor = BeanDependencyGraphExtractor()
    graph = extractor.extract([{"name": "beanA", "dependencies": [{"target": "beanB", "type": "constructor"}]}])
    assert len(graph.nodes) == 1
    assert graph.nodes[0].name == "beanA"
    assert len(graph.edges) == 1
    assert graph.edges[0].target == "beanB"
    assert graph.edges[0].dependency_type == DependencyType.CONSTRUCTOR

def test_extract_too_many():
    extractor = BeanDependencyGraphExtractor()
    try:
        extractor.extract([{"name": f"bean{i}"} for i in range(1001)])
        assert False
    except ValueError:
        assert True

def test_cycle_detection():
    extractor = BeanDependencyGraphExtractor()
    # Cycle: A -> B -> C -> A
    definitions = [
        {"name": "beanA", "dependencies": [{"target": "beanB", "type": "field"}]},
        {"name": "beanB", "dependencies": [{"target": "beanC", "type": "setter"}]},
        {"name": "beanC", "dependencies": [{"target": "beanA", "type": "constructor"}]},
        {"name": "beanD", "dependencies": [{"target": "beanA"}]},
    ]
    graph = extractor.extract(definitions)
    assert len(graph.cycles) >= 1
    cycle_nodes = set(graph.cycles[0])
    assert "beanA" in cycle_nodes
    assert "beanB" in cycle_nodes
    assert "beanC" in cycle_nodes
    assert "beanD" not in cycle_nodes
    assert "cycleStyle" in graph.mermaid_diagram

def test_topological_sort():
    extractor = BeanDependencyGraphExtractor()
    # DAG: C -> B -> A (A has no deps, B depends on A, C depends on B)
    definitions = [
        {"name": "beanA", "dependencies": []},
        {"name": "beanB", "dependencies": [{"target": "beanA"}]},
        {"name": "beanC", "dependencies": [{"target": "beanB"}]},
    ]
    graph = extractor.extract(definitions)
    assert len(graph.cycles) == 0
    order, is_dag = extractor.topological_order(graph)
    assert is_dag is True
    assert order.index("beanA") < order.index("beanB")
    assert order.index("beanB") < order.index("beanC")
