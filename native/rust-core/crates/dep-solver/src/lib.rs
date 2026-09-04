use serde::{Deserialize, Serialize};
use std::cmp::Ordering;
use std::collections::{BTreeMap, HashMap};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SemVer {
    pub major: u64,
    pub minor: u64,
    pub patch: u64,
    pub pre: Option<String>,
}

impl SemVer {
    pub fn parse(s: &str) -> Result<Self, String> {
        let clean = s.trim().trim_start_matches('v').trim_start_matches('=');
        let (ver_part, pre) = if let Some(idx) = clean.find('-') {
            (&clean[..idx], Some(clean[idx + 1..].to_string()))
        } else {
            (clean, None)
        };

        let parts: Vec<&str> = ver_part.split('.').collect();
        if parts.is_empty() || parts.len() > 3 {
            return Err(format!("Invalid semver: {}", s));
        }

        let major = parts[0].parse::<u64>().map_err(|e| e.to_string())?;
        let minor = if parts.len() > 1 {
            parts[1].parse::<u64>().map_err(|e| e.to_string())?
        } else {
            0
        };
        let patch = if parts.len() > 2 {
            parts[2].parse::<u64>().map_err(|e| e.to_string())?
        } else {
            0
        };

        Ok(SemVer {
            major,
            minor,
            patch,
            pre,
        })
    }

    pub fn to_string_repr(&self) -> String {
        if let Some(ref p) = self.pre {
            format!("{}.{}.{}-{}", self.major, self.minor, self.patch, p)
        } else {
            format!("{}.{}.{}", self.major, self.minor, self.patch)
        }
    }
}

impl Ord for SemVer {
    fn cmp(&self, other: &Self) -> Ordering {
        match self.major.cmp(&other.major) {
            Ordering::Equal => match self.minor.cmp(&other.minor) {
                Ordering::Equal => match self.patch.cmp(&other.patch) {
                    Ordering::Equal => match (&self.pre, &other.pre) {
                        (None, None) => Ordering::Equal,
                        (None, Some(_)) => Ordering::Greater, // Non-prerelease is higher than prerelease
                        (Some(_), None) => Ordering::Less,
                        (Some(a), Some(b)) => a.cmp(b),
                    },
                    other => other,
                },
                other => other,
            },
            other => other,
        }
    }
}

impl PartialOrd for SemVer {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ConstraintOp {
    Exact,
    Gte,
    Lte,
    Gt,
    Lt,
    Caret,
    Tilde,
    Wildcard,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SingleConstraint {
    pub op: ConstraintOp,
    pub version: SemVer,
}

impl SingleConstraint {
    pub fn matches(&self, ver: &SemVer) -> bool {
        match self.op {
            ConstraintOp::Exact => ver == &self.version,
            ConstraintOp::Gte => ver >= &self.version,
            ConstraintOp::Lte => ver <= &self.version,
            ConstraintOp::Gt => ver > &self.version,
            ConstraintOp::Lt => ver < &self.version,
            ConstraintOp::Caret => {
                if ver < &self.version {
                    return false;
                }
                if self.version.major > 0 {
                    ver.major == self.version.major
                } else if self.version.minor > 0 {
                    ver.major == 0 && ver.minor == self.version.minor
                } else {
                    ver.major == 0 && ver.minor == 0 && ver.patch == self.version.patch
                }
            }
            ConstraintOp::Tilde => {
                if ver < &self.version {
                    return false;
                }
                ver.major == self.version.major && ver.minor == self.version.minor
            }
            ConstraintOp::Wildcard => true,
        }
    }
}

pub fn parse_constraints(spec: &str) -> Vec<SingleConstraint> {
    let mut results = Vec::new();
    let parts = spec.split(',');
    for part in parts {
        let p = part.trim();
        if p.is_empty() || p == "*" {
            results.push(SingleConstraint {
                op: ConstraintOp::Wildcard,
                version: SemVer {
                    major: 0,
                    minor: 0,
                    patch: 0,
                    pre: None,
                },
            });
            continue;
        }

        let (op, ver_str) = if let Some(v) = p.strip_prefix(">=") {
            (ConstraintOp::Gte, v)
        } else if let Some(v) = p.strip_prefix("<=") {
            (ConstraintOp::Lte, v)
        } else if let Some(v) = p.strip_prefix('>') {
            (ConstraintOp::Gt, v)
        } else if let Some(v) = p.strip_prefix('<') {
            (ConstraintOp::Lt, v)
        } else if let Some(v) = p.strip_prefix('^') {
            (ConstraintOp::Caret, v)
        } else if let Some(v) = p.strip_prefix('~') {
            (ConstraintOp::Tilde, v)
        } else if let Some(v) = p.strip_prefix("==") {
            (ConstraintOp::Exact, v)
        } else if let Some(v) = p.strip_prefix('=') {
            (ConstraintOp::Exact, v)
        } else {
            (ConstraintOp::Exact, p)
        };

        if let Ok(sem) = SemVer::parse(ver_str) {
            results.push(SingleConstraint { op, version: sem });
        }
    }
    results
}

pub fn satisfies_all(constraints: &[SingleConstraint], ver: &SemVer) -> bool {
    constraints.iter().all(|c| c.matches(ver))
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DependencyRequirement {
    pub package: String,
    pub constraints: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PackageRelease {
    pub version: String,
    #[serde(default)]
    pub dependencies: Vec<DependencyRequirement>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SolverInput {
    pub root_dependencies: Vec<DependencyRequirement>,
    pub available_packages: HashMap<String, Vec<PackageRelease>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SolverOutput {
    pub status: String,
    pub solution: Option<BTreeMap<String, String>>,
    pub error: Option<String>,
}

pub fn solve_dependencies(input: &SolverInput) -> SolverOutput {
    let mut sorted_available: HashMap<String, Vec<(SemVer, PackageRelease)>> = HashMap::new();
    for (pkg, releases) in &input.available_packages {
        let mut list: Vec<(SemVer, PackageRelease)> = releases
            .iter()
            .filter_map(|r| SemVer::parse(&r.version).ok().map(|v| (v, r.clone())))
            .collect();
        // Sort descending to prefer latest versions
        list.sort_by(|a, b| b.0.cmp(&a.0));
        sorted_available.insert(pkg.clone(), list);
    }

    let mut assignment: BTreeMap<String, (SemVer, PackageRelease)> = BTreeMap::new();
    let mut requirements: Vec<DependencyRequirement> = input.root_dependencies.clone();

    // Backtracking depth-first search
    if solve_recursive(&mut assignment, &mut requirements, &sorted_available) {
        let mut solution = BTreeMap::new();
        for (k, (v, _)) in assignment {
            solution.insert(k, v.to_string_repr());
        }
        SolverOutput {
            status: "SOLVED".to_string(),
            solution: Some(solution),
            error: None,
        }
    } else {
        SolverOutput {
            status: "CONFLICT".to_string(),
            solution: None,
            error: Some("Dependency conflict detected: no compatible version assignment found".to_string()),
        }
    }
}

fn solve_recursive(
    assignment: &mut BTreeMap<String, (SemVer, PackageRelease)>,
    unresolved: &mut Vec<DependencyRequirement>,
    available: &HashMap<String, Vec<(SemVer, PackageRelease)>>,
) -> bool {
    if unresolved.is_empty() {
        return true;
    }

    let req = unresolved.pop().unwrap();
    let constraints = parse_constraints(&req.constraints);

    if let Some((assigned_ver, _)) = assignment.get(&req.package) {
        if satisfies_all(&constraints, assigned_ver) {
            return solve_recursive(assignment, unresolved, available);
        } else {
            unresolved.push(req);
            return false;
        }
    }

    let candidates = match available.get(&req.package) {
        Some(list) => list,
        None => {
            unresolved.push(req);
            return false;
        }
    };

    for (ver, release) in candidates {
        if satisfies_all(&constraints, ver) {
            assignment.insert(req.package.clone(), (ver.clone(), release.clone()));
            let mut new_unresolved = unresolved.clone();
            for dep in &release.dependencies {
                new_unresolved.push(dep.clone());
            }

            if solve_recursive(assignment, &mut new_unresolved, available) {
                return true;
            }

            assignment.remove(&req.package);
        }
    }

    unresolved.push(req);
    false
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LockfileSummary {
    pub format: String,
    pub total_packages: usize,
    pub packages: BTreeMap<String, String>,
}

pub fn parse_lockfile_str(content: &str, format: &str) -> Result<LockfileSummary, String> {
    let mut packages = BTreeMap::new();

    if format == "npm" || format == "package-lock" {
        let json_val: serde_json::Value =
            serde_json::from_str(content).map_err(|e| format!("JSON parse error: {}", e))?;
        if let Some(deps) = json_val.get("packages").and_then(|p| p.as_object()) {
            for (k, v) in deps {
                let clean_name = k.trim_start_matches("node_modules/");
                if !clean_name.is_empty() {
                    if let Some(ver) = v.get("version").and_then(|ver| ver.as_str()) {
                        packages.insert(clean_name.to_string(), ver.to_string());
                    }
                }
            }
        } else if let Some(deps) = json_val.get("dependencies").and_then(|p| p.as_object()) {
            for (k, v) in deps {
                if let Some(ver) = v.get("version").and_then(|ver| ver.as_str()) {
                    packages.insert(k.clone(), ver.to_string());
                }
            }
        }
    } else {
        // Simple generic key-value line scanner
        for line in content.lines() {
            let l = line.trim();
            if let Some((k, v)) = l.split_once("==") {
                packages.insert(k.trim().to_string(), v.trim().to_string());
            } else if let Some((k, v)) = l.split_once(':') {
                if !k.contains('{') && !v.contains('{') {
                    packages.insert(k.trim().to_string(), v.trim().trim_matches('"').to_string());
                }
            }
        }
    }

    Ok(LockfileSummary {
        format: format.to_string(),
        total_packages: packages.len(),
        packages,
    })
}

pub fn solve_dependencies_json(json_input: &str) -> String {
    let input: SolverInput = match serde_json::from_str(json_input) {
        Ok(inp) => inp,
        Err(e) => {
            let err_output = SolverOutput {
                status: "ERROR".to_string(),
                solution: None,
                error: Some(format!("Invalid solver input JSON: {}", e)),
            };
            return serde_json::to_string(&err_output).unwrap_or_else(|_| "{}".to_string());
        }
    };

    let result = solve_dependencies(&input);
    serde_json::to_string(&result).unwrap_or_else(|_| "{}".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_semver_parsing_and_ordering() {
        let v1 = SemVer::parse("1.2.3").unwrap();
        let v2 = SemVer::parse("1.2.4").unwrap();
        let v3 = SemVer::parse("2.0.0-beta.1").unwrap();
        let v4 = SemVer::parse("2.0.0").unwrap();

        assert!(v1 < v2);
        assert!(v2 < v3);
        assert!(v3 < v4);
    }

    #[test]
    fn test_constraint_matching() {
        let v = SemVer::parse("1.5.2").unwrap();
        let c_caret = parse_constraints("^1.2.0");
        assert!(satisfies_all(&c_caret, &v));

        let c_tilde = parse_constraints("~1.5.0");
        assert!(satisfies_all(&c_tilde, &v));

        let c_range = parse_constraints(">=1.0.0, <2.0.0");
        assert!(satisfies_all(&c_range, &v));

        let c_mismatch = parse_constraints("^2.0.0");
        assert!(!satisfies_all(&c_mismatch, &v));
    }

    #[test]
    fn test_dependency_solving_success() {
        let mut available = HashMap::new();
        available.insert(
            "fastapi".to_string(),
            vec![
                PackageRelease {
                    version: "0.100.0".to_string(),
                    dependencies: vec![DependencyRequirement {
                        package: "pydantic".to_string(),
                        constraints: "^2.0.0".to_string(),
                    }],
                },
                PackageRelease {
                    version: "0.95.0".to_string(),
                    dependencies: vec![DependencyRequirement {
                        package: "pydantic".to_string(),
                        constraints: "^1.10.0".to_string(),
                    }],
                },
            ],
        );
        available.insert(
            "pydantic".to_string(),
            vec![
                PackageRelease {
                    version: "2.4.2".to_string(),
                    dependencies: vec![],
                },
                PackageRelease {
                    version: "1.10.8".to_string(),
                    dependencies: vec![],
                },
            ],
        );

        let input = SolverInput {
            root_dependencies: vec![
                DependencyRequirement {
                    package: "fastapi".to_string(),
                    constraints: ">=0.95.0".to_string(),
                },
                DependencyRequirement {
                    package: "pydantic".to_string(),
                    constraints: "^2.0.0".to_string(),
                },
            ],
            available_packages: available,
        };

        let output = solve_dependencies(&input);
        assert_eq!(output.status, "SOLVED");
        let sol = output.solution.unwrap();
        assert_eq!(sol.get("fastapi").unwrap(), "0.100.0");
        assert_eq!(sol.get("pydantic").unwrap(), "2.4.2");
    }

    #[test]
    fn test_dependency_conflict() {
        let mut available = HashMap::new();
        available.insert(
            "lib-a".to_string(),
            vec![PackageRelease {
                version: "1.0.0".to_string(),
                dependencies: vec![DependencyRequirement {
                    package: "shared".to_string(),
                    constraints: "^1.0.0".to_string(),
                }],
            }],
        );
        available.insert(
            "lib-b".to_string(),
            vec![PackageRelease {
                version: "1.0.0".to_string(),
                dependencies: vec![DependencyRequirement {
                    package: "shared".to_string(),
                    constraints: "^2.0.0".to_string(),
                }],
            }],
        );
        available.insert(
            "shared".to_string(),
            vec![
                PackageRelease {
                    version: "1.5.0".to_string(),
                    dependencies: vec![],
                },
                PackageRelease {
                    version: "2.1.0".to_string(),
                    dependencies: vec![],
                },
            ],
        );

        let input = SolverInput {
            root_dependencies: vec![
                DependencyRequirement {
                    package: "lib-a".to_string(),
                    constraints: "*".to_string(),
                },
                DependencyRequirement {
                    package: "lib-b".to_string(),
                    constraints: "*".to_string(),
                },
            ],
            available_packages: available,
        };

        let output = solve_dependencies(&input);
        assert_eq!(output.status, "CONFLICT");
        assert!(output.solution.is_none());
    }
}
