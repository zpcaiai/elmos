use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use std::fs;
use std::path::Path;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClassMetadata {
    pub class_name: String,
    pub super_class: Option<String>,
    pub interfaces: Vec<String>,
    pub major_version: u16,
    pub minor_version: u16,
    pub spring_annotations: Vec<String>,
    pub referenced_classes: Vec<String>,
    pub is_controller: bool,
    pub is_service: bool,
    pub is_repository: bool,
    pub is_component: bool,
    pub is_configuration: bool,
    pub is_transactional: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DirectoryScanResult {
    pub scanned_classes_count: usize,
    pub controllers_count: usize,
    pub services_count: usize,
    pub repositories_count: usize,
    pub classes: Vec<ClassMetadata>,
    pub errors: Vec<String>,
}

#[derive(Debug, Clone)]
enum CpEntry {
    Utf8(String),
    Class(u16),
    Other,
}

pub fn parse_class_bytes(bytes: &[u8]) -> Result<ClassMetadata, String> {
    if bytes.len() < 10 {
        return Err("File too small for Java class".to_string());
    }

    // Check Magic: 0xCAFEBABE
    if bytes[0] != 0xCA || bytes[1] != 0xFE || bytes[2] != 0xBA || bytes[3] != 0xBE {
        return Err("Invalid magic bytes, expected 0xCAFEBABE".to_string());
    }

    let mut cursor = 4;
    let minor_version = read_u16(bytes, &mut cursor)?;
    let major_version = read_u16(bytes, &mut cursor)?;
    let cp_count = read_u16(bytes, &mut cursor)?;

    if cp_count == 0 {
        return Err("Invalid constant pool count".to_string());
    }

    let mut constant_pool: Vec<Option<CpEntry>> = vec![None; cp_count as usize];
    let mut i = 1;
    while i < cp_count as usize {
        if cursor >= bytes.len() {
            return Err("Unexpected EOF reading constant pool".to_string());
        }
        let tag = bytes[cursor];
        cursor += 1;

        match tag {
            1 => {
                // Utf8
                let len = read_u16(bytes, &mut cursor)? as usize;
                if cursor + len > bytes.len() {
                    return Err("Utf8 string overflows class bytes".to_string());
                }
                let s = String::from_utf8_lossy(&bytes[cursor..cursor + len]).to_string();
                cursor += len;
                constant_pool[i] = Some(CpEntry::Utf8(s));
            }
            3 | 4 => {
                // Integer, Float
                cursor += 4;
                constant_pool[i] = Some(CpEntry::Other);
            }
            5 | 6 => {
                // Long, Double (takes two slots)
                cursor += 8;
                constant_pool[i] = Some(CpEntry::Other);
                i += 1; // Double slot
            }
            7 => {
                // Class
                let name_idx = read_u16(bytes, &mut cursor)?;
                constant_pool[i] = Some(CpEntry::Class(name_idx));
            }
            8 => {
                // String
                cursor += 2;
                constant_pool[i] = Some(CpEntry::Other);
            }
            9 | 10 | 11 | 12 => {
                // Fieldref, Methodref, InterfaceMethodref, NameAndType
                cursor += 4;
                constant_pool[i] = Some(CpEntry::Other);
            }
            15 => {
                // MethodHandle
                cursor += 3;
                constant_pool[i] = Some(CpEntry::Other);
            }
            16 => {
                // MethodType
                cursor += 2;
                constant_pool[i] = Some(CpEntry::Other);
            }
            17 | 18 => {
                // Dynamic, InvokeDynamic
                cursor += 4;
                constant_pool[i] = Some(CpEntry::Other);
            }
            19 | 20 => {
                // Module, Package
                cursor += 2;
                constant_pool[i] = Some(CpEntry::Other);
            }
            other => {
                return Err(format!("Unknown constant pool tag: {}", other));
            }
        }
        i += 1;
    }

    if cursor + 6 > bytes.len() {
        return Err("Unexpected EOF reading class headers".to_string());
    }

    let _access_flags = read_u16(bytes, &mut cursor)?;
    let this_class_idx = read_u16(bytes, &mut cursor)?;
    let super_class_idx = read_u16(bytes, &mut cursor)?;

    let class_name = resolve_class_name(&constant_pool, this_class_idx)
        .unwrap_or_else(|| "Unknown".to_string());
    let super_class = resolve_class_name(&constant_pool, super_class_idx);

    let interfaces_count = read_u16(bytes, &mut cursor)? as usize;
    let mut interfaces = Vec::with_capacity(interfaces_count);
    for _ in 0..interfaces_count {
        let iface_idx = read_u16(bytes, &mut cursor)?;
        if let Some(iface_name) = resolve_class_name(&constant_pool, iface_idx) {
            interfaces.push(iface_name);
        }
    }

    // Collect Spring annotations and referenced classes from the Constant Pool Utf8 strings
    let mut spring_annotations = BTreeSet::new();
    let mut referenced_classes = BTreeSet::new();

    for entry in &constant_pool {
        if let Some(CpEntry::Utf8(ref s)) = entry {
            check_spring_annotation(s, &mut spring_annotations);
            check_class_reference(s, &mut referenced_classes);
        }
    }

    let is_controller = spring_annotations.contains("Controller")
        || spring_annotations.contains("RestController");
    let is_service = spring_annotations.contains("Service");
    let is_repository = spring_annotations.contains("Repository");
    let is_component = spring_annotations.contains("Component");
    let is_configuration = spring_annotations.contains("Configuration");
    let is_transactional = spring_annotations.contains("Transactional");

    Ok(ClassMetadata {
        class_name,
        super_class,
        interfaces,
        major_version,
        minor_version,
        spring_annotations: spring_annotations.into_iter().collect(),
        referenced_classes: referenced_classes.into_iter().collect(),
        is_controller,
        is_service,
        is_repository,
        is_component,
        is_configuration,
        is_transactional,
    })
}

fn read_u16(bytes: &[u8], cursor: &mut usize) -> Result<u16, String> {
    if *cursor + 2 > bytes.len() {
        return Err("Unexpected EOF reading u16".to_string());
    }
    let val = u16::from_be_bytes([bytes[*cursor], bytes[*cursor + 1]]);
    *cursor += 2;
    Ok(val)
}

fn resolve_class_name(cp: &[Option<CpEntry>], class_idx: u16) -> Option<String> {
    if class_idx == 0 || class_idx as usize >= cp.len() {
        return None;
    }
    if let Some(Some(CpEntry::Class(name_idx))) = cp.get(class_idx as usize) {
        if let Some(Some(CpEntry::Utf8(ref name))) = cp.get(*name_idx as usize) {
            return Some(name.clone());
        }
    }
    None
}

fn check_spring_annotation(s: &str, set: &mut BTreeSet<String>) {
    if s.contains("org/springframework/") || s.contains("org.springframework.") {
        let simple_name = s.split(|c| c == '/' || c == '.').last().unwrap_or(s);
        let clean = simple_name.trim_matches(';').trim_start_matches('L');
        match clean {
            "RestController" => { set.insert("RestController".to_string()); }
            "Controller" => { set.insert("Controller".to_string()); }
            "Service" => { set.insert("Service".to_string()); }
            "Repository" => { set.insert("Repository".to_string()); }
            "Component" => { set.insert("Component".to_string()); }
            "Configuration" => { set.insert("Configuration".to_string()); }
            "Bean" => { set.insert("Bean".to_string()); }
            "Transactional" => { set.insert("Transactional".to_string()); }
            "Autowired" => { set.insert("Autowired".to_string()); }
            "RequestMapping" => { set.insert("RequestMapping".to_string()); }
            "GetMapping" => { set.insert("GetMapping".to_string()); }
            "PostMapping" => { set.insert("PostMapping".to_string()); }
            "PutMapping" => { set.insert("PutMapping".to_string()); }
            "DeleteMapping" => { set.insert("DeleteMapping".to_string()); }
            _ => {}
        }
    }
}

fn check_class_reference(s: &str, set: &mut BTreeSet<String>) {
    if s.starts_with('L') && s.ends_with(';') && s.contains('/') {
        let cls = &s[1..s.len() - 1];
        if !cls.starts_with("java/lang/") {
            set.insert(cls.to_string());
        }
    }
}

pub fn scan_directory_classes(dir_path: &Path) -> DirectoryScanResult {
    let mut classes = Vec::new();
    let mut errors = Vec::new();
    let mut controllers = 0;
    let mut services = 0;
    let mut repositories = 0;

    let mut stack = vec![dir_path.to_path_buf()];
    while let Some(current) = stack.pop() {
        if let Ok(entries) = fs::read_dir(&current) {
            for entry in entries.flatten() {
                let p = entry.path();
                if p.is_dir() {
                    stack.push(p);
                } else if p.extension().map_or(false, |ext| ext == "class") {
                    match fs::read(&p) {
                        Ok(bytes) => match parse_class_bytes(&bytes) {
                            Ok(meta) => {
                                if meta.is_controller {
                                    controllers += 1;
                                }
                                if meta.is_service {
                                    services += 1;
                                }
                                if meta.is_repository {
                                    repositories += 1;
                                }
                                classes.push(meta);
                            }
                            Err(e) => {
                                errors.push(format!("{}: {}", p.display(), e));
                            }
                        },
                        Err(e) => {
                            errors.push(format!("{}: {}", p.display(), e));
                        }
                    }
                }
            }
        }
    }

    DirectoryScanResult {
        scanned_classes_count: classes.len(),
        controllers_count: controllers,
        services_count: services,
        repositories_count: repositories,
        classes,
        errors,
    }
}

pub fn scan_class_bytes_json(bytes: &[u8]) -> String {
    match parse_class_bytes(bytes) {
        Ok(meta) => serde_json::to_string(&meta).unwrap_or_else(|_| "{}".to_string()),
        Err(e) => {
            let err_obj = serde_json::json!({
                "error": e
            });
            err_obj.to_string()
        }
    }
}

pub fn scan_directory_json(path_str: &str) -> String {
    let res = scan_directory_classes(Path::new(path_str));
    serde_json::to_string(&res).unwrap_or_else(|_| "{}".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_invalid_class_magic() {
        let bad_bytes = vec![0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
        assert!(parse_class_bytes(&bad_bytes).is_err());
    }

    #[test]
    fn test_synthetic_minimal_class_parse() {
        // Minimal valid Java class file structure
        let mut bytes = Vec::new();
        // Magic
        bytes.extend_from_slice(&[0xCA, 0xFE, 0xBA, 0xBE]);
        // Minor version 0
        bytes.extend_from_slice(&[0x00, 0x00]);
        // Major version 61 (Java 17)
        bytes.extend_from_slice(&[0x00, 0x3D]);
        // Constant pool count = 6 (indices 1..5)
        bytes.extend_from_slice(&[0x00, 0x06]);

        // 1: Class (points to 2)
        bytes.push(7);
        bytes.extend_from_slice(&[0x00, 0x02]);
        // 2: Utf8 "com/example/TestController"
        bytes.push(1);
        let s2 = "com/example/TestController";
        bytes.extend_from_slice(&(s2.len() as u16).to_be_bytes());
        bytes.extend_from_slice(s2.as_bytes());
        // 3: Class (points to 4)
        bytes.push(7);
        bytes.extend_from_slice(&[0x00, 0x04]);
        // 4: Utf8 "java/lang/Object"
        bytes.push(1);
        let s4 = "java/lang/Object";
        bytes.extend_from_slice(&(s4.len() as u16).to_be_bytes());
        bytes.extend_from_slice(s4.as_bytes());
        // 5: Utf8 "Lorg/springframework/web/bind/annotation/RestController;"
        bytes.push(1);
        let s5 = "Lorg/springframework/web/bind/annotation/RestController;";
        bytes.extend_from_slice(&(s5.len() as u16).to_be_bytes());
        bytes.extend_from_slice(s5.as_bytes());

        // Access flags: 0x0021 (public super)
        bytes.extend_from_slice(&[0x00, 0x21]);
        // This class: 1
        bytes.extend_from_slice(&[0x00, 0x01]);
        // Super class: 3
        bytes.extend_from_slice(&[0x00, 0x03]);
        // Interfaces count: 0
        bytes.extend_from_slice(&[0x00, 0x00]);

        let meta = parse_class_bytes(&bytes).unwrap();
        assert_eq!(meta.class_name, "com/example/TestController");
        assert_eq!(meta.super_class, Some("java/lang/Object".to_string()));
        assert_eq!(meta.major_version, 61);
        assert!(meta.is_controller);
        assert!(!meta.is_service);
    }
}
