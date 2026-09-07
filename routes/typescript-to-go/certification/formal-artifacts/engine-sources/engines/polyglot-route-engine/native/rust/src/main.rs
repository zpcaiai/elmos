use serde_json::{json, Value};
use std::{env, fs, path::Path, process};
use syn::{BinOp, Block, Expr, FnArg, Item, Lit, Pat, ReturnType, Stmt, Type};

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
    path.path.segments.last().map(|segment| segment.ident.to_string())
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
            let target_name = target.path.segments.last().map(|segment| segment.ident.to_string());
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
                if !matches!(call.receiver.as_ref(), Expr::Lit(literal) if matches!(literal.lit, Lit::Str(_))) {
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
    let emitted_target = arguments.len() == 4;
    let source = fs::read_to_string(source_path)
        .unwrap_or_else(|error| fail(format!("RUST_SOURCE_READ_FAILED:{error}")));
    let file =
        syn::parse_file(&source).unwrap_or_else(|error| fail(format!("RUST_PARSE_FAILED:{error}")));
    let function = file
        .items
        .iter()
        .find_map(|item| match item {
            Item::Fn(function) if function.sig.ident == function_name => Some(function),
            _ => None,
        })
        .unwrap_or_else(|| fail(format!("FUNCTION_NOT_FOUND:{function_name}")));
    if function.sig.asyncness.is_some()
        || function.sig.unsafety.is_some()
        || function.sig.abi.is_some()
    {
        fail("RUST_FUNCTION_QUALIFIER_OUTSIDE_CERTIFIED_SUBSET");
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
