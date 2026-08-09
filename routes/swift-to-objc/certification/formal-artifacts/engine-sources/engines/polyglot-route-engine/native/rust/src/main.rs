use serde_json::{json, Value};
use std::{env, fs, path::Path, process};
use syn::{Attribute, BinOp, Block, Expr, FnArg, Item, Lit, Pat, ReturnType, Stmt, Type};

fn fail(code: impl AsRef<str>) -> ! {
    eprintln!("{}", code.as_ref());
    process::exit(2);
}

fn canonical_type(value: &Type) -> &'static str {
    let Type::Path(path) = value else {
        fail("RUST_UNSUPPORTED_TYPE");
    };
    let Some(segment) = path.path.segments.last() else {
        fail("RUST_UNSUPPORTED_TYPE");
    };
    match segment.ident.to_string().as_str() {
        "i64" => "integer",
        "f64" => "number",
        "bool" => "boolean",
        "String" => "string",
        name => fail(format!("RUST_UNSUPPORTED_TYPE:{name}")),
    }
}

fn path_name(value: &Expr) -> Option<String> {
    let Expr::Path(path) = value else {
        return None;
    };
    if path.qself.is_some() {
        return None;
    }
    path.path
        .segments
        .last()
        .map(|segment| segment.ident.to_string())
}

fn expression(value: &Expr, emitted_target: bool) -> Value {
    match value {
        Expr::Path(path) => {
            let Some(segment) = path.path.segments.last() else {
                fail("RUST_INVALID_PATH");
            };
            json!({"kind": "name", "value": segment.ident.to_string()})
        }
        Expr::Lit(literal) => match &literal.lit {
            Lit::Int(value) => {
                json!({"kind": "literal", "value": value.base10_parse::<i64>().unwrap_or_else(|_| fail("RUST_INVALID_INTEGER"))})
            }
            Lit::Float(value) => {
                json!({"kind": "literal", "value": value.base10_parse::<f64>().unwrap_or_else(|_| fail("RUST_INVALID_FLOAT"))})
            }
            Lit::Bool(value) => json!({"kind": "literal", "value": value.value}),
            Lit::Str(value) => json!({"kind": "literal", "value": value.value()}),
            _ => fail("RUST_UNSUPPORTED_LITERAL"),
        },
        Expr::Paren(paren) => expression(&paren.expr, emitted_target),
        Expr::Binary(binary) => {
            let operator = match &binary.op {
                BinOp::Add(_) => "+",
                BinOp::Sub(_) => "-",
                BinOp::Mul(_) => "*",
                BinOp::Div(_) => "/",
                BinOp::Rem(_) => "%",
                BinOp::Lt(_) => "<",
                BinOp::Le(_) => "<=",
                BinOp::Gt(_) => ">",
                BinOp::Ge(_) => ">=",
                BinOp::Eq(_) => "==",
                BinOp::Ne(_) => "!=",
                BinOp::And(_) => "&&",
                BinOp::Or(_) => "||",
                _ => fail("RUST_UNSUPPORTED_OPERATOR"),
            };
            json!({
                "kind": "binary",
                "operator": operator,
                "left": expression(&binary.left, emitted_target),
                "right": expression(&binary.right, emitted_target),
            })
        }
        Expr::Call(call) if emitted_target => {
            let Some(callee) = path_name(&call.func) else {
                fail("RUST_EMITTED_HELPER_CALLEE_INVALID");
            };
            if callee != "elmos_non_zero_f64" {
                fail(format!("RUST_EMITTED_HELPER_UNRECOGNIZED:{callee}"));
            }
            if call.args.len() != 1 {
                fail("RUST_EMITTED_HELPER_ARITY:elmos_non_zero_f64");
            }
            expression(&call.args[0], true)
        }
        Expr::Cast(cast) if emitted_target => {
            let Type::Path(target) = cast.ty.as_ref() else {
                fail("RUST_EMITTED_CAST_TARGET_INVALID");
            };
            let target_name = target
                .path
                .segments
                .last()
                .map(|segment| segment.ident.to_string());
            if target.qself.is_some() || target_name.as_deref() != Some("f64") {
                fail("RUST_EMITTED_CAST_TARGET_INVALID");
            }
            expression(&cast.expr, true)
        }
        Expr::MethodCall(call) if emitted_target => {
            let method = call.method.to_string();
            if method == "to_string" {
                if call.turbofish.is_some() || !call.args.is_empty() {
                    fail("RUST_EMITTED_STRING_CONVERSION_INVALID");
                }
                if !matches!(call.receiver.as_ref(), Expr::Lit(literal) if matches!(literal.lit, Lit::Str(_)))
                {
                    fail("RUST_EMITTED_STRING_CONVERSION_INVALID");
                }
                return expression(&call.receiver, true);
            }
            if method != "expect" || call.turbofish.is_some() || call.args.len() != 1 {
                fail(format!("RUST_EMITTED_METHOD_UNRECOGNIZED:{method}"));
            }
            let Expr::MethodCall(checked) = call.receiver.as_ref() else {
                fail("RUST_EMITTED_CHECKED_SHAPE_INVALID");
            };
            if checked.turbofish.is_some() || checked.args.len() != 1 {
                fail("RUST_EMITTED_CHECKED_SHAPE_INVALID");
            }
            let (operator, expected_message) = match checked.method.to_string().as_str() {
                "checked_add" => ("+", "ELMOS_INTEGER_OVERFLOW"),
                "checked_sub" => ("-", "ELMOS_INTEGER_OVERFLOW"),
                "checked_mul" => ("*", "ELMOS_INTEGER_OVERFLOW"),
                "checked_div" => ("/", "ELMOS_DIVIDE_BY_ZERO"),
                "checked_rem" => ("%", "ELMOS_DIVIDE_BY_ZERO"),
                name => fail(format!("RUST_EMITTED_CHECKED_METHOD_UNRECOGNIZED:{name}")),
            };
            let Expr::Lit(message) = &call.args[0] else {
                fail("RUST_EMITTED_CHECKED_MESSAGE_INVALID");
            };
            let Lit::Str(message) = &message.lit else {
                fail("RUST_EMITTED_CHECKED_MESSAGE_INVALID");
            };
            if message.value() != expected_message {
                fail("RUST_EMITTED_CHECKED_MESSAGE_INVALID");
            }
            json!({
                "kind": "binary",
                "operator": operator,
                "left": expression(&checked.receiver, true),
                "right": expression(&checked.args[0], true),
            })
        }
        _ => fail("RUST_UNSUPPORTED_EXPRESSION"),
    }
}

fn statements(block: &Block, emitted_target: bool) -> Vec<Value> {
    block
        .stmts
        .iter()
        .map(|statement| match statement {
            Stmt::Expr(Expr::Return(returned), _) => {
                let Some(value) = returned.expr.as_ref() else {
                    fail("RUST_RETURN_EXPRESSION_REQUIRED");
                };
                json!({"kind": "return", "expression": expression(value, emitted_target)})
            }
            Stmt::Expr(Expr::If(branch), _) => {
                let otherwise = match branch.else_branch.as_ref() {
                    None => Vec::new(),
                    Some((_, value)) => match value.as_ref() {
                        Expr::Block(block) => statements(&block.block, emitted_target),
                        _ => fail("RUST_ELSE_IF_OUTSIDE_CERTIFIED_SUBSET"),
                    },
                };
                json!({
                    "kind": "if",
                    "condition": expression(&branch.cond, emitted_target),
                    "then": statements(&branch.then_branch, emitted_target),
                    "else": otherwise,
                })
            }
            _ => fail("RUST_UNSUPPORTED_STATEMENT"),
        })
        .collect()
}

fn attribute_name(attribute: &Attribute) -> String {
    attribute
        .path()
        .segments
        .iter()
        .map(|segment| segment.ident.to_string())
        .collect::<Vec<_>>()
        .join("::")
}

fn item_attributes(item: &Item) -> &[Attribute] {
    match item {
        Item::Const(value) => &value.attrs,
        Item::Enum(value) => &value.attrs,
        Item::ExternCrate(value) => &value.attrs,
        Item::Fn(value) => &value.attrs,
        Item::ForeignMod(value) => &value.attrs,
        Item::Impl(value) => &value.attrs,
        Item::Macro(value) => &value.attrs,
        Item::Mod(value) => &value.attrs,
        Item::Static(value) => &value.attrs,
        Item::Struct(value) => &value.attrs,
        Item::Trait(value) => &value.attrs,
        Item::TraitAlias(value) => &value.attrs,
        Item::Type(value) => &value.attrs,
        Item::Union(value) => &value.attrs,
        Item::Use(value) => &value.attrs,
        _ => &[],
    }
}

fn item_owner(item: &Item, index: usize) -> String {
    match item {
        Item::Const(value) => value.ident.to_string(),
        Item::Enum(value) => value.ident.to_string(),
        Item::ExternCrate(value) => value.ident.to_string(),
        Item::Fn(value) => value.sig.ident.to_string(),
        Item::Mod(value) => value.ident.to_string(),
        Item::Static(value) => value.ident.to_string(),
        Item::Struct(value) => value.ident.to_string(),
        Item::Trait(value) => value.ident.to_string(),
        Item::TraitAlias(value) => value.ident.to_string(),
        Item::Type(value) => value.ident.to_string(),
        Item::Union(value) => value.ident.to_string(),
        _ => format!("<item@{index}>"),
    }
}

fn push_attribute_subjects(
    subjects: &mut Vec<Value>,
    attributes: &[Attribute],
    owner: &str,
    declaration_kind: &str,
) {
    for attribute in attributes {
        let path = attribute_name(attribute);
        let name = format!("<attribute:{path}>");
        subjects.push(json!({
            "name": name,
            "qualified_name": format!("{owner}::@{path}"),
            "declaration_kind": declaration_kind,
            "analyzable": false,
            "source_span": null,
            "signature": {"attribute_path": path},
        }));
    }
}

fn module_inventory(source_path: &str, file: &syn::File) -> Value {
    let mut subjects: Vec<Value> = Vec::new();
    push_attribute_subjects(&mut subjects, &file.attrs, "<module>", "module-attribute");
    for (index, item) in file.items.iter().enumerate() {
        let owner = item_owner(item, index);
        push_attribute_subjects(
            &mut subjects,
            item_attributes(item),
            &owner,
            "item-attribute",
        );
        match item {
            Item::Fn(function) => subjects.push(json!({
                "name": function.sig.ident.to_string(),
                "qualified_name": function.sig.ident.to_string(),
                "declaration_kind": "function",
                "analyzable": function.sig.asyncness.is_none()
                    && function.sig.unsafety.is_none()
                    && function.sig.abi.is_none()
                    && function.sig.constness.is_none()
                    && function.attrs.is_empty()
                    && function.sig.generics.params.is_empty()
                    && function.sig.generics.where_clause.is_none()
                    && function.sig.variadic.is_none(),
                "source_span": null,
                "signature": {
                    "parameter_count": function.sig.inputs.len(),
                    "has_return_type": !matches!(&function.sig.output, ReturnType::Default),
                    "async": function.sig.asyncness.is_some(),
                    "unsafe": function.sig.unsafety.is_some(),
                    "extern": function.sig.abi.is_some(),
                },
            })),
            Item::Impl(implementation) => {
                let container = format!("<impl@{index}>");
                subjects.push(json!({
                    "name": container,
                    "qualified_name": container,
                    "declaration_kind": "impl",
                    "analyzable": false,
                    "source_span": null,
                    "signature": {},
                }));
                for member in &implementation.items {
                    if let syn::ImplItem::Fn(method) = member {
                        let name = method.sig.ident.to_string();
                        subjects.push(json!({
                            "name": name,
                            "qualified_name": format!("{container}::{name}"),
                            "declaration_kind": "method",
                            "analyzable": false,
                            "source_span": null,
                            "signature": {"parameter_count": method.sig.inputs.len()},
                        }));
                    }
                }
            }
            Item::Const(value) => subjects.push(json!({
                "name": value.ident.to_string(), "qualified_name": value.ident.to_string(),
                "declaration_kind": "constant", "analyzable": false, "source_span": null,
                "signature": {},
            })),
            Item::Static(value) => subjects.push(json!({
                "name": value.ident.to_string(), "qualified_name": value.ident.to_string(),
                "declaration_kind": "static", "analyzable": false, "source_span": null,
                "signature": {},
            })),
            Item::Struct(value) => subjects.push(json!({
                "name": value.ident.to_string(), "qualified_name": value.ident.to_string(),
                "declaration_kind": "struct", "analyzable": false, "source_span": null,
                "signature": {},
            })),
            Item::Enum(value) => subjects.push(json!({
                "name": value.ident.to_string(), "qualified_name": value.ident.to_string(),
                "declaration_kind": "enum", "analyzable": false, "source_span": null,
                "signature": {},
            })),
            Item::Type(value) => subjects.push(json!({
                "name": value.ident.to_string(), "qualified_name": value.ident.to_string(),
                "declaration_kind": "type", "analyzable": false, "source_span": null,
                "signature": {},
            })),
            Item::Mod(value) => subjects.push(json!({
                "name": value.ident.to_string(), "qualified_name": value.ident.to_string(),
                "declaration_kind": "module", "analyzable": false, "source_span": null,
                "signature": {},
            })),
            Item::Use(_) => {
                let name = format!("<use@{index}>");
                subjects.push(json!({
                    "name": name, "qualified_name": name, "declaration_kind": "use",
                    "analyzable": false, "source_span": null, "signature": {},
                }));
            }
            _ => {
                let name = format!("<item@{index}>");
                subjects.push(json!({
                    "name": name, "qualified_name": name, "declaration_kind": "unsupported-item",
                    "analyzable": false, "source_span": null, "signature": {},
                }));
            }
        }
    }
    json!({
        "schema_version": "1.0.0",
        "kind": "elmos.typed-pure-module-inventory",
        "profile": "typed-pure-module-v1",
        "source_language": "rust",
        "source_file": Path::new(source_path).file_name().and_then(|value| value.to_str()).unwrap_or(source_path),
        "analyzer": "syn AST",
        "analyzer_version": "2.0.119 / rustc 1.89.0",
        "enumeration_status": "PASSED",
        "subjects": subjects,
        "diagnostics": [],
    })
}

fn main() {
    let arguments: Vec<String> = env::args().collect();
    if arguments.len() < 3
        || arguments.len() > 4
        || (arguments.len() == 4 && arguments[3] != "--emitted-target")
    {
        fail("USAGE:elmos-rust-analyzer SOURCE FUNCTION [--emitted-target]");
    }
    let source_path = &arguments[1];
    let function_name = &arguments[2];
    let inventory_mode = function_name == "--inventory";
    if inventory_mode && arguments.len() != 3 {
        fail("RUST_INVENTORY_ARGUMENTS_INVALID");
    }
    let emitted_target = arguments.len() == 4;
    let source = fs::read_to_string(source_path)
        .unwrap_or_else(|error| fail(format!("RUST_SOURCE_READ_FAILED:{error}")));
    let file = match syn::parse_file(&source) {
        Ok(value) => value,
        Err(error) if inventory_mode => {
            println!(
                "{}",
                json!({
                    "schema_version": "1.0.0", "kind": "elmos.typed-pure-module-inventory",
                    "profile": "typed-pure-module-v1", "source_language": "rust",
                    "source_file": Path::new(source_path).file_name().and_then(|value| value.to_str()).unwrap_or(source_path),
                    "analyzer": "syn AST", "analyzer_version": "2.0.119 / rustc 1.89.0",
                    "enumeration_status": "FAILED", "subjects": [],
                    "diagnostics": [format!("RUST_PARSE_FAILED:{error}")],
                })
            );
            return;
        }
        Err(error) => fail(format!("RUST_PARSE_FAILED:{error}")),
    };
    if inventory_mode {
        println!("{}", module_inventory(source_path, &file));
        return;
    }
    let function = file
        .items
        .iter()
        .find_map(|item| match item {
            Item::Fn(function) if function.sig.ident == function_name => Some(function),
            _ => None,
        })
        .unwrap_or_else(|| fail(format!("FUNCTION_NOT_FOUND:{function_name}")));
    if !file.attrs.is_empty() || !function.attrs.is_empty() {
        fail("RUST_ATTRIBUTE_OUTSIDE_CERTIFIED_SUBSET");
    }
    if function.sig.asyncness.is_some()
        || function.sig.unsafety.is_some()
        || function.sig.abi.is_some()
        || function.sig.constness.is_some()
    {
        fail("RUST_FUNCTION_QUALIFIER_OUTSIDE_CERTIFIED_SUBSET");
    }
    if !function.sig.generics.params.is_empty()
        || function.sig.generics.where_clause.is_some()
        || function.sig.variadic.is_some()
    {
        fail("RUST_GENERIC_OR_VARIADIC_FUNCTION_OUTSIDE_CERTIFIED_SUBSET");
    }
    let parameters: Vec<Value> = function
        .sig
        .inputs
        .iter()
        .map(|input| match input {
            FnArg::Typed(argument) => {
                let Pat::Ident(name) = argument.pat.as_ref() else {
                    fail("RUST_PARAMETER_IDENTIFIER_REQUIRED");
                };
                json!({"name": name.ident.to_string(), "type": canonical_type(&argument.ty)})
            }
            FnArg::Receiver(_) => fail("RUST_METHOD_OUTSIDE_CERTIFIED_SUBSET"),
        })
        .collect();
    let return_type = match &function.sig.output {
        ReturnType::Type(_, value) => canonical_type(value),
        ReturnType::Default => fail("RUST_RETURN_TYPE_REQUIRED"),
    };
    let output = json!({
        "schema_version": "1.0.0",
        "source_language": "rust",
        "source_file": Path::new(source_path).file_name().and_then(|value| value.to_str()).unwrap_or(source_path),
        "analyzer": "syn AST",
        "analyzer_version": "2.0.119 / rustc 1.89.0",
        "functions": [{
            "name": function.sig.ident.to_string(),
            "parameters": parameters,
            "return_type": return_type,
            "body": statements(&function.block, emitted_target),
        }],
        "diagnostics": [],
    });
    println!(
        "{}",
        serde_json::to_string(&output)
            .unwrap_or_else(|error| fail(format!("RUST_JSON_FAILED:{error}")))
    );
}
