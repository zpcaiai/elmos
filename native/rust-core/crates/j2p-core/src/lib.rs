use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct JavaParam {
    pub name: String,
    pub type_name: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct JavaMethod {
    pub name: String,
    pub return_type: String,
    pub modifiers: Vec<String>,
    pub parameters: Vec<JavaParam>,
    pub annotations: Vec<String>,
    pub line_start: usize,
    pub line_end: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct JavaField {
    pub name: String,
    pub type_name: String,
    pub modifiers: Vec<String>,
    pub annotations: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct JavaClass {
    pub name: String,
    pub kind: String, // class, interface, enum, record
    pub modifiers: Vec<String>,
    pub super_class: Option<String>,
    pub interfaces: Vec<String>,
    pub annotations: Vec<String>,
    pub fields: Vec<JavaField>,
    pub methods: Vec<JavaMethod>,
    pub line_start: usize,
    pub line_end: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct JavaFileSummary {
    pub package_name: Option<String>,
    pub imports: Vec<String>,
    pub classes: Vec<JavaClass>,
    pub line_count: usize,
}

pub struct JavaAstExtractor;

impl JavaAstExtractor {
    pub fn parse_summary(source: &str) -> JavaFileSummary {
        let lines: Vec<&str> = source.lines().collect();
        let line_count = lines.len();
        let mut package_name = None;
        let mut imports = Vec::new();
        let mut classes = Vec::new();

        let mut current_annotations: Vec<String> = Vec::new();
        let mut in_comment = false;

        let mut current_class: Option<JavaClass> = None;

        for (idx, &line) in lines.iter().enumerate() {
            let line_number = idx + 1;
            let trimmed = line.trim();

            if in_comment {
                if let Some(pos) = trimmed.find("*/") {
                    in_comment = false;
                    let remaining = trimmed[pos + 2..].trim();
                    if remaining.is_empty() {
                        continue;
                    }
                } else {
                    continue;
                }
            }

            if trimmed.starts_with("/*") {
                if !trimmed.contains("*/") {
                    in_comment = true;
                    continue;
                }
            }
            if trimmed.starts_with("//") || trimmed.is_empty() {
                continue;
            }

            // Annotations
            if trimmed.starts_with('@') {
                let annotation = trimmed.split_whitespace().next().unwrap_or(trimmed);
                current_annotations.push(annotation.to_string());
                continue;
            }

            // Package declaration
            if trimmed.starts_with("package ") {
                if let Some(semi) = trimmed.find(';') {
                    let pkg = trimmed["package ".len()..semi].trim();
                    package_name = Some(pkg.to_string());
                }
                continue;
            }

            // Import declaration
            if trimmed.starts_with("import ") {
                if let Some(semi) = trimmed.find(';') {
                    let imp = trimmed["import ".len()..semi].trim();
                    imports.push(imp.to_string());
                }
                continue;
            }

            // Class, Interface, Enum, Record declaration
            if is_type_declaration(trimmed) {
                if let Some(c) = current_class.take() {
                    classes.push(c);
                }

                let (kind, name, mods, super_c, ifaces) = parse_type_decl(trimmed);
                let class_def = JavaClass {
                    name,
                    kind,
                    modifiers: mods,
                    super_class: super_c,
                    interfaces: ifaces,
                    annotations: std::mem::take(&mut current_annotations),
                    fields: Vec::new(),
                    methods: Vec::new(),
                    line_start: line_number,
                    line_end: line_number,
                };
                current_class = Some(class_def);
                continue;
            }

            // Method or Field inside class
            if let Some(ref mut c) = current_class {
                if !trimmed.starts_with("return ")
                    && trimmed.contains('(')
                    && (trimmed.ends_with('{') || trimmed.ends_with(';'))
                {
                    // Method signature
                    let method = parse_method_sig(trimmed, line_number, std::mem::take(&mut current_annotations));
                    if let Some(m) = method {
                        c.methods.push(m);
                    }
                } else if trimmed.ends_with(';') && !trimmed.starts_with("return ") {
                    // Field
                    let field = parse_field_decl(trimmed, std::mem::take(&mut current_annotations));
                    if let Some(f) = field {
                        c.fields.push(f);
                    }
                }
            }

            current_annotations.clear();
        }

        if let Some(c) = current_class {
            classes.push(c);
        }

        JavaFileSummary {
            package_name,
            imports,
            classes,
            line_count,
        }
    }
}

fn is_type_declaration(line: &str) -> bool {
    let tokens: Vec<&str> = line.split_whitespace().collect();
    for token in tokens {
        if matches!(token, "class" | "interface" | "enum" | "record") {
            return true;
        }
    }
    false
}

fn parse_type_decl(line: &str) -> (String, String, Vec<String>, Option<String>, Vec<String>) {
    let tokens: Vec<&str> = line.split_whitespace().collect();
    let mut modifiers = Vec::new();
    let mut kind = "class".to_string();
    let mut name = String::new();
    let mut super_class = None;
    let mut interfaces = Vec::new();

    let mut state = "mods"; // mods -> name -> after
    let mut after_state = "";

    for &tok in &tokens {
        let clean = tok.trim_matches(|c| c == '{' || c == '(');
        if clean.is_empty() {
            continue;
        }

        if state == "mods" {
            if matches!(clean, "class" | "interface" | "enum" | "record") {
                kind = clean.to_string();
                state = "name";
            } else {
                modifiers.push(clean.to_string());
            }
        } else if state == "name" {
            // Strip generic parameters if any e.g. Foo<T>
            let base_name = clean.split('<').next().unwrap_or(clean);
            name = base_name.to_string();
            state = "after";
        } else if state == "after" {
            if clean == "extends" {
                after_state = "extends";
            } else if clean == "implements" {
                after_state = "implements";
            } else if after_state == "extends" {
                super_class = Some(clean.trim_matches(',').to_string());
                after_state = "";
            } else if after_state == "implements" {
                interfaces.push(clean.trim_matches(',').to_string());
            }
        }
    }

    (kind, name, modifiers, super_class, interfaces)
}

fn parse_method_sig(line: &str, line_number: usize, annotations: Vec<String>) -> Option<JavaMethod> {
    let open_paren = line.find('(')?;
    let before_paren = line[..open_paren].trim();
    let tokens: Vec<&str> = before_paren.split_whitespace().collect();
    if tokens.is_empty() {
        return None;
    }

    let name = tokens.last()?.to_string();
    let mut modifiers = Vec::new();
    let mut return_type = "void".to_string();

    if tokens.len() > 1 {
        return_type = tokens[tokens.len() - 2].to_string();
        for &tok in &tokens[..tokens.len() - 2] {
            modifiers.push(tok.to_string());
        }
    }

    let close_paren = line.find(')')?;
    let param_str = &line[open_paren + 1..close_paren].trim();
    let mut parameters = Vec::new();

    if !param_str.is_empty() {
        for p in param_str.split(',') {
            let p_tokens: Vec<&str> = p.split_whitespace().collect();
            if p_tokens.len() >= 2 {
                parameters.push(JavaParam {
                    type_name: p_tokens[p_tokens.len() - 2].to_string(),
                    name: p_tokens[p_tokens.len() - 1].to_string(),
                });
            }
        }
    }

    Some(JavaMethod {
        name,
        return_type,
        modifiers,
        parameters,
        annotations,
        line_start: line_number,
        line_end: line_number,
    })
}

fn parse_field_decl(line: &str, annotations: Vec<String>) -> Option<JavaField> {
    let stripped = line.trim_end_matches(';').trim();
    let tokens: Vec<&str> = stripped.split_whitespace().collect();
    if tokens.len() < 2 {
        return None;
    }

    let name_candidate = tokens.last()?;
    let name = name_candidate.split('=').next()?.trim().to_string();
    let type_name = tokens[tokens.len() - 2].to_string();
    let mut modifiers = Vec::new();
    for &tok in &tokens[..tokens.len() - 2] {
        modifiers.push(tok.to_string());
    }

    Some(JavaField {
        name,
        type_name,
        modifiers,
        annotations,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_java_summary() {
        let code = r#"
package io.elmos.test;

import java.util.List;
import java.util.Map;

@Service
public class OrderService extends BaseService implements IOrder {
    private String orderId;
    public int status;

    @Override
    public List<String> processOrder(String orderId, int count) {
        return List.of();
    }
}
"#;
        let summary = JavaAstExtractor::parse_summary(code);
        assert_eq!(summary.package_name, Some("io.elmos.test".to_string()));
        assert_eq!(summary.imports.len(), 2);
        assert_eq!(summary.classes.len(), 1);

        let cls = &summary.classes[0];
        assert_eq!(cls.name, "OrderService");
        assert_eq!(cls.kind, "class");
        assert_eq!(cls.super_class, Some("BaseService".to_string()));
        assert_eq!(cls.interfaces, vec!["IOrder".to_string()]);
        assert_eq!(cls.fields.len(), 2);
        assert_eq!(cls.methods.len(), 1);

        let m = &cls.methods[0];
        assert_eq!(m.name, "processOrder");
        assert_eq!(m.return_type, "List<String>");
        assert_eq!(m.parameters.len(), 2);
        assert_eq!(m.parameters[0].name, "orderId");
        assert_eq!(m.parameters[0].type_name, "String");
    }
}
