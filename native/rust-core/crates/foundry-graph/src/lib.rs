use std::collections::{BTreeMap, BTreeSet, VecDeque};
use std::sync::RwLock;

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillNode {
    pub name: String,
    pub pack: String,
    pub dependencies: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CatalogInput {
    pub schema_version: Option<String>,
    pub atomic_skills: Option<Vec<SkillNodeInput>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillNodeInput {
    pub name: String,
    pub pack: String,
    #[serde(default)]
    pub dependencies: Vec<String>,
}

pub struct SkillGraph {
    nodes: BTreeMap<String, SkillNode>,
    adjacency: BTreeMap<String, Vec<String>>,
    reverse_adjacency: BTreeMap<String, Vec<String>>,
}

impl SkillGraph {
    pub fn new() -> Self {
        Self {
            nodes: BTreeMap::new(),
            adjacency: BTreeMap::new(),
            reverse_adjacency: BTreeMap::new(),
        }
    }

    pub fn load_json(json_str: &str) -> Result<Self, String> {
        let input: CatalogInput = serde_json::from_str(json_str).map_err(|e| e.to_string())?;
        let atomic_skills = input.atomic_skills.unwrap_or_default();

        let mut graph = Self::new();
        for skill in atomic_skills {
            let node = SkillNode {
                name: skill.name.clone(),
                pack: skill.pack.clone(),
                dependencies: skill.dependencies.clone(),
            };
            graph.nodes.insert(skill.name.clone(), node);
            graph.adjacency.insert(skill.name.clone(), skill.dependencies.clone());

            for dep in &skill.dependencies {
                graph
                    .reverse_adjacency
                    .entry(dep.clone())
                    .or_default()
                    .push(skill.name.clone());
            }
        }
        Ok(graph)
    }

    pub fn resolve_dependencies(&self, root: &str) -> Vec<String> {
        let mut visited = BTreeSet::new();
        let mut queue = VecDeque::new();
        queue.push_back(root.to_string());
        visited.insert(root.to_string());

        let mut all_deps = Vec::new();

        while let Some(current) = queue.pop_front() {
            if let Some(deps) = self.adjacency.get(&current) {
                for d in deps {
                    if visited.insert(d.clone()) {
                        queue.push_back(d.clone());
                        all_deps.push(d.clone());
                    }
                }
            }
        }

        // Return sorted topologically
        self.topological_sort(&all_deps).unwrap_or(all_deps)
    }

    pub fn topological_sort(&self, subset: &[String]) -> Result<Vec<String>, String> {
        let set: BTreeSet<String> = subset.iter().cloned().collect();
        let mut in_degrees: BTreeMap<String, usize> = BTreeMap::new();

        for name in &set {
            in_degrees.insert(name.clone(), 0);
        }

        for name in &set {
            if let Some(deps) = self.adjacency.get(name) {
                for dep in deps {
                    if set.contains(dep) {
                        *in_degrees.entry(name.clone()).or_insert(0) += 1;
                    }
                }
            }
        }

        let mut ready: VecDeque<String> = in_degrees
            .iter()
            .filter(|(_, &deg)| deg == 0)
            .map(|(k, _)| k.clone())
            .collect();

        let mut result = Vec::with_capacity(set.len());

        while let Some(curr) = ready.pop_front() {
            result.push(curr.clone());
            if let Some(dependents) = self.reverse_adjacency.get(&curr) {
                for dep in dependents {
                    if set.contains(dep) {
                        if let Some(deg) = in_degrees.get_mut(dep) {
                            *deg -= 1;
                            if *deg == 0 {
                                ready.push_back(dep.clone());
                            }
                        }
                    }
                }
            }
        }

        if result.len() != set.len() {
            return Err("cycle detected in dependency subgraph".to_string());
        }

        Ok(result)
    }

    pub fn get_skill(&self, name: &str) -> Option<&SkillNode> {
        self.nodes.get(name)
    }

    pub fn skill_count(&self) -> usize {
        self.nodes.len()
    }
}

// Thread-safe global singleton
static GLOBAL_GRAPH: RwLock<Option<SkillGraph>> = RwLock::new(None);

pub fn init_global_catalog(catalog_json: &str) -> Result<usize, String> {
    let graph = SkillGraph::load_json(catalog_json)?;
    let count = graph.skill_count();
    let mut lock = GLOBAL_GRAPH.write().map_err(|e| e.to_string())?;
    *lock = Some(graph);
    Ok(count)
}

pub fn resolve_global_dependencies(skill_name: &str) -> Result<Vec<String>, String> {
    let lock = GLOBAL_GRAPH.read().map_err(|e| e.to_string())?;
    let graph = lock.as_ref().ok_or_else(|| "catalog graph not initialized".to_string())?;
    Ok(graph.resolve_dependencies(skill_name))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_graph_resolution() {
        let sample = r#"{
            "atomic_skills": [
                {"name": "skill-c", "pack": "pack-c", "dependencies": []},
                {"name": "skill-b", "pack": "pack-b", "dependencies": ["skill-c"]},
                {"name": "skill-a", "pack": "pack-a", "dependencies": ["skill-b"]}
            ]
        }"#;

        let graph = SkillGraph::load_json(sample).unwrap();
        assert_eq!(graph.skill_count(), 3);
        let deps = graph.resolve_dependencies("skill-a");
        assert_eq!(deps, vec!["skill-c", "skill-b"]);
    }
}
