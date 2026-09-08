use serde_json::{json, Value};
use std::collections::{HashMap, HashSet};
use std::sync::atomic::{AtomicBool, Ordering};
use std::{env, fs, panic, path::Path, process};
use syn::{Attribute, BinOp, Block, Expr, ExprIf, FnArg, Item, Lit, Pat, ReturnType, Stmt, Type};

/// Carries a rejection code out of one function's analysis without ending the
/// process, so batch mode can report a per-function verdict.
///
/// This is deliberately the *only* payload batch mode recovers from.  Any other
/// panic keeps unwinding and takes the process down exactly as it does today,
/// because the caller is not entitled to read an unexpected crash as a domain
/// decision -- it has to fall back to the per-function path, where the existing
/// fail-closed handling applies unchanged.
struct DomainRejection(String);

/// Set once, before any analysis, and never cleared.  In single-function mode
/// `fail` keeps its original behaviour to the byte -- the code on stderr and
/// exit status 2 are what the Python side matches on.
static BATCH_MODE: AtomicBool = AtomicBool::new(false);

fn fail(code: impl AsRef<str>) -> ! {
    let code = code.as_ref();
    if BATCH_MODE.load(Ordering::Relaxed) {
        panic::panic_any(DomainRejection(code.to_string()));
    }
    eprintln!("{code}");
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
    match value {
        Expr::Path(path) => {
            if path.qself.is_some() {
                return None;
            }
            path.path
                .segments
                .last()
                .map(|segment| segment.ident.to_string())
        }
        Expr::Paren(paren) => path_name(&paren.expr),
        _ => None,
    }
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
        Expr::Unary(unary) => match &unary.op {
            syn::UnOp::Neg(_) => match unary.expr.as_ref() {
                Expr::Lit(literal) => match &literal.lit {
                    Lit::Int(value) => {
                        let parsed = value
                            .base10_parse::<i64>()
                            .unwrap_or_else(|_| fail("RUST_INVALID_INTEGER"));
                        json!({"kind": "literal", "value": -parsed})
                    }
                    Lit::Float(value) => {
                        let parsed = value
                            .base10_parse::<f64>()
                            .unwrap_or_else(|_| fail("RUST_INVALID_FLOAT"));
                        json!({"kind": "literal", "value": -parsed})
                    }
                    _ => fail("RUST_UNSUPPORTED_EXPRESSION"),
                },
                _ => fail("RUST_UNSUPPORTED_EXPRESSION"),
            },
            _ => fail("RUST_UNSUPPORTED_EXPRESSION"),
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

/// Lifts one `if`, including an `else if` chain.
///
/// In Rust an `else if` is an else branch whose expression is itself an `if`
/// -- spelling, not a new construct -- so it lifts into the nested
/// `else: [if]` shape the IR already carries. Eight of this engine's ten
/// frontends already produced that shape; Go and Rust rejected it instead,
/// which cost twelve directed routes each for no semantic reason.
///
/// Anything else in the else position (a `match`, a bare expression) is still
/// outside the profile and still fails closed.
fn lift_if(
    branch: &ExprIf,
    emitted_target: bool,
    scope_vars: &HashMap<String, &'static str>,
    param_names: &HashSet<String>,
) -> Value {
    let mut then_scope = scope_vars.clone();
    let then_statements = statements(&branch.then_branch, emitted_target, &mut then_scope, param_names);
    let otherwise = match branch.else_branch.as_ref() {
        None => Vec::new(),
        Some((_, value)) => match value.as_ref() {
            Expr::Block(block) => {
                let mut else_scope = scope_vars.clone();
                statements(&block.block, emitted_target, &mut else_scope, param_names)
            }
            Expr::If(chained) => vec![lift_if(chained, emitted_target, scope_vars, param_names)],
            _ => fail("RUST_ELSE_IF_OUTSIDE_CERTIFIED_SUBSET"),
        },
    };
    json!({
        "kind": "if",
        "condition": expression(&branch.cond, emitted_target),
        "then": then_statements,
        "else": otherwise,
    })
}

fn statements(
    block: &Block,
    emitted_target: bool,
    scope_vars: &mut HashMap<String, &'static str>,
    param_names: &HashSet<String>,
) -> Vec<Value> {
    let mut result = Vec::new();
    let stmts_len = block.stmts.len();
    for (idx, statement) in block.stmts.iter().enumerate() {
        let is_last = idx == stmts_len - 1;
        match statement {
            Stmt::Local(local) => {
                let Some(init) = &local.init else {
                    fail("RUST_ANNOTATED_DECLARATION_WITHOUT_VALUE");
                };
                if init.diverge.is_some() {
                    fail("RUST_LET_ELSE_OUTSIDE_CERTIFIED_SUBSET");
                }
                let (pat_ident, ty_str) = match &local.pat {
                    Pat::Ident(_) => {
                        fail("RUST_UNANNOTATED_ASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET");
                    }
                    Pat::Type(pat_type) => {
                        let Pat::Ident(pat_ident) = pat_type.pat.as_ref() else {
                            fail("RUST_PATTERN_BINDING_OUTSIDE_CERTIFIED_SUBSET");
                        };
                        (pat_ident, canonical_type(&pat_type.ty))
                    }
                    _ => fail("RUST_PATTERN_BINDING_OUTSIDE_CERTIFIED_SUBSET"),
                };
                if pat_ident.by_ref.is_some() || pat_ident.subpat.is_some() {
                    fail("RUST_PATTERN_BINDING_OUTSIDE_CERTIFIED_SUBSET");
                }
                let name = pat_ident.ident.to_string();
                scope_vars.insert(name.clone(), ty_str);
                result.push(json!({
                    "kind": "let",
                    "name": name,
                    "type": ty_str,
                    "expression": expression(&init.expr, emitted_target),
                }));
            }
            Stmt::Expr(expr, semi) => {
                match expr {
                    Expr::Return(returned) => {
                        let Some(value) = returned.expr.as_ref() else {
                            fail("RUST_RETURN_EXPRESSION_REQUIRED");
                        };
                        result.push(json!({
                            "kind": "return",
                            "expression": expression(value, emitted_target)
                        }));
                    }
                    Expr::If(branch) => {
                        result.push(lift_if(branch, emitted_target, scope_vars, param_names));
                    }
                    Expr::While(while_expr) => {
                        if while_expr.label.is_some() {
                            fail("RUST_LABELED_LOOP_OUTSIDE_CERTIFIED_SUBSET");
                        }
                        let mut loop_scope = scope_vars.clone();
                        let body_stmts = statements(&while_expr.body, emitted_target, &mut loop_scope, param_names);
                        result.push(json!({
                            "kind": "while",
                            "condition": expression(&while_expr.cond, emitted_target),
                            "body": body_stmts,
                        }));
                    }
                    Expr::ForLoop(for_loop) => {
                        if for_loop.label.is_some() {
                            fail("RUST_LABELED_LOOP_OUTSIDE_CERTIFIED_SUBSET");
                        }
                        let pat_ident = match for_loop.pat.as_ref() {
                            Pat::Ident(ident) => ident,
                            _ => fail("RUST_FOR_PATTERN_OUTSIDE_CERTIFIED_SUBSET"),
                        };
                        if pat_ident.by_ref.is_some() || pat_ident.subpat.is_some() {
                            fail("RUST_FOR_PATTERN_OUTSIDE_CERTIFIED_SUBSET");
                        }
                        let var_name = pat_ident.ident.to_string();
                        let (start_expr, end_expr, step_val) = match for_loop.expr.as_ref() {
                            Expr::Range(range) => {
                                if !matches!(range.limits, syn::RangeLimits::HalfOpen(_)) {
                                    fail("RUST_FOR_RANGE_OUTSIDE_CERTIFIED_SUBSET");
                                }
                                let Some(start) = range.start.as_deref() else {
                                    fail("RUST_FOR_RANGE_OUTSIDE_CERTIFIED_SUBSET");
                                };
                                let Some(end) = range.end.as_deref() else {
                                    fail("RUST_FOR_RANGE_OUTSIDE_CERTIFIED_SUBSET");
                                };
                                (start, end, None)
                            }
                            Expr::MethodCall(method_call) => {
                                if method_call.method != "step_by" || method_call.args.len() != 1 {
                                    fail("RUST_FOR_RANGE_OUTSIDE_CERTIFIED_SUBSET");
                                }
                                let range_expr = match method_call.receiver.as_ref() {
                                    Expr::Paren(paren) => paren.expr.as_ref(),
                                    other => other,
                                };
                                let Expr::Range(range) = range_expr else {
                                    fail("RUST_FOR_RANGE_OUTSIDE_CERTIFIED_SUBSET");
                                };
                                if !matches!(range.limits, syn::RangeLimits::HalfOpen(_)) {
                                    fail("RUST_FOR_RANGE_OUTSIDE_CERTIFIED_SUBSET");
                                }
                                let Some(start) = range.start.as_deref() else {
                                    fail("RUST_FOR_RANGE_OUTSIDE_CERTIFIED_SUBSET");
                                };
                                let Some(end) = range.end.as_deref() else {
                                    fail("RUST_FOR_RANGE_OUTSIDE_CERTIFIED_SUBSET");
                                };
                                let step_arg = &method_call.args[0];
                                let step_inner = match step_arg {
                                    Expr::Cast(cast) => &cast.expr,
                                    other => other,
                                };
                                let step_value = expression(step_inner, emitted_target);
                                (start, end, Some(step_value))
                            }
                            _ => fail("RUST_FOR_RANGE_OUTSIDE_CERTIFIED_SUBSET"),
                        };
                        let mut loop_scope = scope_vars.clone();
                        loop_scope.insert(var_name.clone(), "integer");
                        let body_stmts = statements(&for_loop.body, emitted_target, &mut loop_scope, param_names);
                        let mut for_json = json!({
                            "kind": "for",
                            "name": var_name,
                            "type": "integer",
                            "start": expression(start_expr, emitted_target),
                            "end": expression(end_expr, emitted_target),
                            "body": body_stmts,
                        });
                        if let Some(step) = step_val {
                            for_json["step"] = step;
                        }
                        result.push(for_json);
                    }
                    Expr::Break(expr_break) => {
                        if expr_break.label.is_some() {
                            fail("RUST_LABELED_BREAK_OUTSIDE_CERTIFIED_SUBSET");
                        }
                        if expr_break.expr.is_some() {
                            fail("RUST_BREAK_VALUE_OUTSIDE_CERTIFIED_SUBSET");
                        }
                        result.push(json!({"kind": "break"}));
                    }
                    Expr::Continue(expr_continue) => {
                        if expr_continue.label.is_some() {
                            fail("RUST_LABELED_CONTINUE_OUTSIDE_CERTIFIED_SUBSET");
                        }
                        result.push(json!({"kind": "continue"}));
                    }
                    Expr::Assign(assign) => {
                        let target_name = match path_name(&assign.left) {
                            Some(name) => name,
                            None => fail("RUST_ASSIGNMENT_TARGET_OUTSIDE_CERTIFIED_SUBSET"),
                        };
                        if param_names.contains(&target_name) {
                            fail(format!("RUST_PARAMETER_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:{target_name}"));
                        }
                        if !scope_vars.contains_key(&target_name) {
                            fail(format!("RUST_ASSIGNMENT_TARGET_NOT_DECLARED:{target_name}"));
                        }
                        result.push(json!({
                            "kind": "assign",
                            "name": target_name,
                            "expression": expression(&assign.right, emitted_target),
                        }));
                    }
                    Expr::Binary(binary) => {
                        let op_str = match &binary.op {
                            BinOp::AddAssign(_) => "+",
                            BinOp::SubAssign(_) => "-",
                            BinOp::MulAssign(_) => "*",
                            BinOp::DivAssign(_) => "/",
                            BinOp::RemAssign(_) => "%",
                            _ => {
                                if semi.is_none() && is_last {
                                    result.push(json!({
                                        "kind": "return",
                                        "expression": expression(expr, emitted_target)
                                    }));
                                    continue;
                                }
                                fail("RUST_UNSUPPORTED_STATEMENT");
                            }
                        };
                        let target_name = match path_name(&binary.left) {
                            Some(name) => name,
                            None => fail("RUST_ASSIGNMENT_TARGET_OUTSIDE_CERTIFIED_SUBSET"),
                        };
                        if param_names.contains(&target_name) {
                            fail(format!("RUST_PARAMETER_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:{target_name}"));
                        }
                        if !scope_vars.contains_key(&target_name) {
                            fail(format!("RUST_ASSIGNMENT_TARGET_NOT_DECLARED:{target_name}"));
                        }
                        result.push(json!({
                            "kind": "assign",
                            "name": target_name,
                            "expression": {
                                "kind": "binary",
                                "operator": op_str,
                                "left": {"kind": "name", "value": target_name},
                                "right": expression(&binary.right, emitted_target),
                            },
                        }));
                    }
                    _ => {
                        if semi.is_none() && is_last {
                            result.push(json!({
                                "kind": "return",
                                "expression": expression(expr, emitted_target)
                            }));
                        } else {
                            fail("RUST_UNSUPPORTED_STATEMENT");
                        }
                    }
                }
            }
            _ => fail("RUST_UNSUPPORTED_STATEMENT"),
        }
    }
    result
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
    // Batch mode: parsing the target file is the shared cost and is identical
    // no matter which function is asked about.  Paying it once per file instead
    // of once per candidate function is the whole point; every per-function
    // answer still comes from `analyze_function`, unchanged.
    let mut batch_names: Vec<String> = Vec::new();
    if let Some(encoded) = function_name.strip_prefix("--functions=") {
        for part in encoded.split(',') {
            let trimmed = part.trim();
            // Duplicates are dropped: an answer must not depend on how many
            // times its name was requested.
            if !trimmed.is_empty() && !batch_names.iter().any(|name| name == trimmed) {
                batch_names.push(trimmed.to_string());
            }
        }
        if batch_names.is_empty() {
            fail("USAGE:elmos-rust-analyzer SOURCE --functions=NAME[,NAME...] [--emitted-target]");
        }
        // The default hook prints a panic banner to stderr.  A domain rejection
        // is an ordinary per-function verdict here, not a crash, so it must not
        // produce one; every other payload still gets the normal report, which
        // is what makes an unexpected crash visibly different from a rejection.
        let previous = panic::take_hook();
        panic::set_hook(Box::new(move |info| {
            if info.payload().downcast_ref::<DomainRejection>().is_none() {
                previous(info);
            }
        }));
        BATCH_MODE.store(true, Ordering::Relaxed);
    }
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
    if BATCH_MODE.load(Ordering::Relaxed) {
        emit_batch(source_path, &file, &batch_names, emitted_target);
        return;
    }
    println!(
        "{}",
        serde_json::to_string(&analyze_function(
            source_path,
            &file,
            function_name,
            emitted_target
        ))
        .unwrap_or_else(|error| fail(format!("RUST_JSON_FAILED:{error}")))
    );
}

/// The single source of truth for one function's result.  Batch mode calls
/// exactly this, so a batch entry cannot drift from what the per-function
/// invocation it replaces would have produced.
fn analyze_function(
    source_path: &str,
    file: &syn::File,
    function_name: &str,
    emitted_target: bool,
) -> Value {
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
    let param_names: HashSet<String> = function
        .sig
        .inputs
        .iter()
        .filter_map(|input| match input {
            FnArg::Typed(argument) => match argument.pat.as_ref() {
                Pat::Ident(name) => Some(name.ident.to_string()),
                _ => None,
            },
            FnArg::Receiver(_) => None,
        })
        .collect();
    let mut scope_vars: HashMap<String, &'static str> = HashMap::new();
    let body = statements(&function.block, emitted_target, &mut scope_vars, &param_names);
    json!({
        "schema_version": "1.0.0",
        "source_language": "rust",
        "source_file": Path::new(source_path).file_name().and_then(|value| value.to_str()).unwrap_or(source_path),
        "analyzer": "syn AST",
        "analyzer_version": "2.0.119 / rustc 1.89.0",
        "functions": [{
            "name": function.sig.ident.to_string(),
            "parameters": parameters,
            "return_type": return_type,
            "body": body,
        }],
        "diagnostics": [],
    })
}

/// Run one function's analysis, turning a domain rejection into a value.
/// Anything that is not a domain rejection resumes unwinding, so the process
/// still dies on it -- batch mode must never convert an unexpected crash into a
/// per-function verdict.
fn analyze_function_guarded(
    source_path: &str,
    file: &syn::File,
    function_name: &str,
    emitted_target: bool,
) -> Result<Value, String> {
    match panic::catch_unwind(panic::AssertUnwindSafe(|| {
        analyze_function(source_path, file, function_name, emitted_target)
    })) {
        Ok(value) => Ok(value),
        Err(payload) => match payload.downcast::<DomainRejection>() {
            Ok(rejection) => Err(rejection.0),
            Err(other) => panic::resume_unwind(other),
        },
    }
}

fn emit_batch(source_path: &str, file: &syn::File, names: &[String], emitted_target: bool) {
    let results: Vec<Value> = names
        .iter()
        .map(
            |name| match analyze_function_guarded(source_path, file, name, emitted_target) {
                Ok(value) => json!({"function": name, "status": "ok", "error": Value::Null, "value": value}),
                Err(code) => {
                    json!({"function": name, "status": "domain_error", "error": code, "value": Value::Null})
                }
            },
        )
        .collect();
    let document = json!({
        "schema_version": "1.0.0",
        "kind": "elmos.typed-pure-function-batch",
        "source_language": "rust",
        "source_file": Path::new(source_path).file_name().and_then(|value| value.to_str()).unwrap_or(source_path),
        "analyzer": "syn AST",
        "analyzer_version": "2.0.119 / rustc 1.89.0",
        "results": results,
    });
    match serde_json::to_string(&document) {
        Ok(text) => println!("{text}"),
        Err(error) => {
            // Every function has already been decided by this point, so leaving
            // batch mode here cannot swallow a verdict; it just restores the
            // ordinary hard-failure exit for an encoding fault.
            BATCH_MODE.store(false, Ordering::Relaxed);
            fail(format!("RUST_JSON_FAILED:{error}"));
        }
    }
}
