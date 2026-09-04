use std::collections::{BTreeMap, BTreeSet, VecDeque};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EdgeInput {
    pub source: String,
    pub target: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BlastRadiusResult {
    pub status: String,
    pub affected_nodes: Vec<String>,
    pub node_count: usize,
    pub truncated: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

pub fn compute_blast_radius(
    changed: &[String],
    edges: &[EdgeInput],
    max_nodes: usize,
) -> BlastRadiusResult {
    let mut adjacency: BTreeMap<&str, BTreeSet<&str>> = BTreeMap::new();
    for edge in edges {
        adjacency
            .entry(&edge.source)
            .or_default()
            .insert(&edge.target);
    }

    let mut seen: BTreeSet<String> = BTreeSet::new();
    let mut queue: VecDeque<String> = VecDeque::new();

    for node in changed {
        if seen.insert(node.clone()) {
            queue.push_back(node.clone());
        }
    }

    let mut truncated = false;
    let limit = if max_nodes == 0 { 10_000 } else { max_nodes };

    while let Some(current) = queue.pop_front() {
        if seen.len() >= limit {
            truncated = true;
            break;
        }

        if let Some(neighbors) = adjacency.get(current.as_str()) {
            for &neighbor in neighbors {
                if seen.len() >= limit {
                    truncated = true;
                    break;
                }
                if seen.insert(neighbor.to_string()) {
                    queue.push_back(neighbor.to_string());
                }
            }
        }
    }

    let affected: Vec<String> = seen.into_iter().collect();
    let count = affected.len();

    BlastRadiusResult {
        status: "OK".to_string(),
        affected_nodes: affected,
        node_count: count,
        truncated,
        error: None,
    }
}

pub fn compute_blast_radius_json(
    changed_json: &str,
    edges_json: &str,
    max_nodes: usize,
) -> String {
    let changed: Vec<String> = match serde_json::from_str(changed_json) {
        Ok(v) => v,
        Err(e) => {
            let res = BlastRadiusResult {
                status: "ERROR".to_string(),
                affected_nodes: Vec::new(),
                node_count: 0,
                truncated: false,
                error: Some(format!("Invalid changed_json: {}", e)),
            };
            return serde_json::to_string(&res).unwrap_or_else(|_| "{}".to_string());
        }
    };

    let edges: Vec<EdgeInput> = match serde_json::from_str(edges_json) {
        Ok(v) => v,
        Err(e) => {
            let res = BlastRadiusResult {
                status: "ERROR".to_string(),
                affected_nodes: Vec::new(),
                node_count: 0,
                truncated: false,
                error: Some(format!("Invalid edges_json: {}", e)),
            };
            return serde_json::to_string(&res).unwrap_or_else(|_| "{}".to_string());
        }
    };

    let result = compute_blast_radius(&changed, &edges, max_nodes);
    serde_json::to_string(&result).unwrap_or_else(|_| "{}".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_empty_graph() {
        let res = compute_blast_radius(&[], &[], 100);
        assert_eq!(res.status, "OK");
        assert_eq!(res.affected_nodes.len(), 0);
        assert!(!res.truncated);
    }

    #[test]
    fn test_transitive_propagation_and_order() {
        let changed = vec!["A".to_string()];
        let edges = vec![
            EdgeInput { source: "A".to_string(), target: "C".to_string() },
            EdgeInput { source: "A".to_string(), target: "B".to_string() },
            EdgeInput { source: "B".to_string(), target: "D".to_string() },
            EdgeInput { source: "C".to_string(), target: "D".to_string() },
            EdgeInput { source: "D".to_string(), target: "E".to_string() },
        ];
        let res = compute_blast_radius(&changed, &edges, 100);
        assert_eq!(res.status, "OK");
        assert_eq!(res.affected_nodes, vec!["A", "B", "C", "D", "E"]);
        assert_eq!(res.node_count, 5);
        assert!(!res.truncated);
    }

    #[test]
    fn test_cyclic_graph_termination() {
        let changed = vec!["A".to_string()];
        let edges = vec![
            EdgeInput { source: "A".to_string(), target: "B".to_string() },
            EdgeInput { source: "B".to_string(), target: "C".to_string() },
            EdgeInput { source: "C".to_string(), target: "A".to_string() }, // Cycle
        ];
        let res = compute_blast_radius(&changed, &edges, 100);
        assert_eq!(res.status, "OK");
        assert_eq!(res.affected_nodes, vec!["A", "B", "C"]);
        assert_eq!(res.node_count, 3);
        assert!(!res.truncated);
    }

    #[test]
    fn test_max_nodes_limit() {
        let changed = vec!["A".to_string()];
        let edges = vec![
            EdgeInput { source: "A".to_string(), target: "B".to_string() },
            EdgeInput { source: "B".to_string(), target: "C".to_string() },
            EdgeInput { source: "C".to_string(), target: "D".to_string() },
        ];
        let res = compute_blast_radius(&changed, &edges, 2);
        assert_eq!(res.status, "OK");
        assert_eq!(res.node_count, 2);
        assert!(res.truncated);
    }
}
