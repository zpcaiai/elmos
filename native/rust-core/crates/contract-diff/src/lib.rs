use std::collections::BTreeMap;
use std::time::Instant;

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FieldSchema {
    pub r#type: String,
    pub required: bool,
    #[serde(default)]
    pub nullable: bool,
    pub format: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EndpointSchema {
    #[serde(default)]
    pub request_fields: BTreeMap<String, FieldSchema>,
    #[serde(default)]
    pub response_fields: BTreeMap<String, FieldSchema>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContractSpec {
    pub schema_version: String,
    pub endpoints: BTreeMap<String, EndpointSchema>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContractDiffItem {
    pub endpoint: String,
    pub category: String,
    pub severity: String, // "BREAKING" | "WARNING" | "NON_BREAKING"
    pub description: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub field_name: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContractDiffReport {
    pub total_changes: usize,
    pub breaking_changes_count: usize,
    pub warnings_count: usize,
    pub non_breaking_count: usize,
    pub is_backward_compatible: bool,
    pub duration_ms: f64,
    pub changes: Vec<ContractDiffItem>,
}

pub fn diff_contract_specs(source: &ContractSpec, target: &ContractSpec) -> ContractDiffReport {
    let start = Instant::now();
    let mut changes = Vec::new();

    // 1. Check endpoints in source
    for (endpoint_key, source_endpoint) in &source.endpoints {
        if let Some(target_endpoint) = target.endpoints.get(endpoint_key) {
            compare_fields(
                endpoint_key,
                &source_endpoint.request_fields,
                &target_endpoint.request_fields,
                "request",
                &mut changes,
            );
            compare_fields(
                endpoint_key,
                &source_endpoint.response_fields,
                &target_endpoint.response_fields,
                "response",
                &mut changes,
            );
        } else {
            changes.push(ContractDiffItem {
                endpoint: endpoint_key.clone(),
                category: "ENDPOINT_REMOVED".to_string(),
                severity: "BREAKING".to_string(),
                description: format!("Endpoint '{}' was removed", endpoint_key),
                field_name: None,
            });
        }
    }

    // 2. Check endpoints added in target
    for endpoint_key in target.endpoints.keys() {
        if !source.endpoints.contains_key(endpoint_key) {
            changes.push(ContractDiffItem {
                endpoint: endpoint_key.clone(),
                category: "ENDPOINT_ADDED".to_string(),
                severity: "NON_BREAKING".to_string(),
                description: format!("Endpoint '{}' was added", endpoint_key),
                field_name: None,
            });
        }
    }

    let breaking_count = changes.iter().filter(|c| c.severity == "BREAKING").count();
    let warnings_count = changes.iter().filter(|c| c.severity == "WARNING").count();
    let non_breaking_count = changes.iter().filter(|c| c.severity == "NON_BREAKING").count();

    ContractDiffReport {
        total_changes: changes.len(),
        breaking_changes_count: breaking_count,
        warnings_count,
        non_breaking_count,
        is_backward_compatible: breaking_count == 0,
        duration_ms: (start.elapsed().as_secs_f64() * 1000.0 * 1000.0).round() / 1000.0,
        changes,
    }
}

fn compare_fields(
    endpoint: &str,
    source_fields: &BTreeMap<String, FieldSchema>,
    target_fields: &BTreeMap<String, FieldSchema>,
    channel: &str,
    changes: &mut Vec<ContractDiffItem>,
) {
    let title_channel = if channel == "request" { "Request" } else { "Response" };

    // Check fields in source
    for (field_name, source_field) in source_fields {
        if let Some(target_field) = target_fields.get(field_name) {
            // Type changed
            if source_field.r#type != target_field.r#type {
                changes.push(ContractDiffItem {
                    endpoint: endpoint.to_string(),
                    category: "TYPE_CHANGED".to_string(),
                    severity: "BREAKING".to_string(),
                    field_name: Some(field_name.clone()),
                    description: format!(
                        "{} field '{}' changed type from {} to {}",
                        title_channel, field_name, source_field.r#type, target_field.r#type
                    ),
                });
            }

            // Format changed
            if source_field.format != target_field.format {
                changes.push(ContractDiffItem {
                    endpoint: endpoint.to_string(),
                    category: "FORMAT_CHANGED".to_string(),
                    severity: "BREAKING".to_string(),
                    field_name: Some(field_name.clone()),
                    description: format!(
                        "{} field '{}' changed format from {:?} to {:?}",
                        title_channel, field_name, source_field.format, target_field.format
                    ),
                });
            }

            // Optionality changed
            if source_field.required != target_field.required {
                let is_breaking = if channel == "request" {
                    !source_field.required && target_field.required
                } else {
                    source_field.required && !target_field.required
                };
                changes.push(ContractDiffItem {
                    endpoint: endpoint.to_string(),
                    category: "OPTIONALITY_CHANGED".to_string(),
                    severity: if is_breaking { "BREAKING".to_string() } else { "NON_BREAKING".to_string() },
                    field_name: Some(field_name.clone()),
                    description: format!(
                        "{} field '{}' required changed from {} to {}",
                        title_channel, field_name, source_field.required, target_field.required
                    ),
                });
            }

            // Nullability changed
            if source_field.nullable != target_field.nullable {
                let is_breaking = if channel == "request" {
                    source_field.nullable && !target_field.nullable
                } else {
                    !source_field.nullable && target_field.nullable
                };
                changes.push(ContractDiffItem {
                    endpoint: endpoint.to_string(),
                    category: "NULLABILITY_CHANGED".to_string(),
                    severity: if is_breaking { "BREAKING".to_string() } else { "NON_BREAKING".to_string() },
                    field_name: Some(field_name.clone()),
                    description: format!(
                        "{} field '{}' nullable changed from {} to {}",
                        title_channel, field_name, source_field.nullable, target_field.nullable
                    ),
                });
            }
        } else {
            // Field removed
            changes.push(ContractDiffItem {
                endpoint: endpoint.to_string(),
                category: "FIELD_REMOVED".to_string(),
                severity: "BREAKING".to_string(),
                field_name: Some(field_name.clone()),
                description: format!("{} field '{}' was removed", title_channel, field_name),
            });
        }
    }

    // Check fields added in target
    for (field_name, target_field) in target_fields {
        if !source_fields.contains_key(field_name) {
            let is_breaking = channel == "request" && target_field.required;
            changes.push(ContractDiffItem {
                endpoint: endpoint.to_string(),
                category: "FIELD_ADDED".to_string(),
                severity: if is_breaking { "BREAKING".to_string() } else { "NON_BREAKING".to_string() },
                field_name: Some(field_name.clone()),
                description: format!("{} field '{}' was added", title_channel, field_name),
            });
        }
    }
}

pub fn diff_specs_json(source_json: &str, target_json: &str) -> Result<ContractDiffReport, String> {
    let source_spec: ContractSpec = serde_json::from_str(source_json).map_err(|e| e.to_string())?;
    let target_spec: ContractSpec = serde_json::from_str(target_json).map_err(|e| e.to_string())?;
    Ok(diff_contract_specs(&source_spec, &target_spec))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_diff_compatible_and_breaking() {
        let src_json = r#"{
            "schema_version": "1.0",
            "endpoints": {
                "POST /api/v1/orders": {
                    "request_fields": {
                        "order_id": {"type": "string", "required": true}
                    },
                    "response_fields": {
                        "status": {"type": "string", "required": true}
                    }
                }
            }
        }"#;

        let tgt_compatible = r#"{
            "schema_version": "1.0",
            "endpoints": {
                "POST /api/v1/orders": {
                    "request_fields": {
                        "order_id": {"type": "string", "required": true},
                        "note": {"type": "string", "required": false}
                    },
                    "response_fields": {
                        "status": {"type": "string", "required": true}
                    }
                }
            }
        }"#;

        let report = diff_specs_json(src_json, tgt_compatible).unwrap();
        assert!(report.is_backward_compatible);
        assert_eq!(report.breaking_changes_count, 0);
        assert_eq!(report.total_changes, 1);

        let tgt_breaking = r#"{
            "schema_version": "1.0",
            "endpoints": {
                "POST /api/v1/orders": {
                    "request_fields": {
                        "order_id": {"type": "integer", "required": true}
                    },
                    "response_fields": {
                        "status": {"type": "string", "required": true}
                    }
                }
            }
        }"#;

        let report_breaking = diff_specs_json(src_json, tgt_breaking).unwrap();
        assert!(!report_breaking.is_backward_compatible);
        assert_eq!(report_breaking.breaking_changes_count, 1);
    }
}
