package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"go/ast"
	"go/build/constraint"
	"go/format"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strconv"
	"strings"
)

// domainRejection carries a rejection code out of one function's analysis
// without ending the process, so batch mode can report a per-function verdict.
// It is deliberately the *only* thing batch mode recovers from: any other panic
// keeps propagating and takes the process down exactly as it does today,
// because the caller is not entitled to read an unexpected crash as a domain
// decision.
type domainRejection struct{ code string }

// batchMode is set once, before any analysis, and never cleared.  In
// single-function mode `fail` keeps its original behaviour to the byte -- the
// code on stderr and exit status 2 are what the Python side matches on.
var batchMode bool

const batchPrefix = "--functions="

func fail(code string) {
	if batchMode {
		panic(domainRejection{code})
	}
	fmt.Fprintln(os.Stderr, code)
	os.Exit(2)
}

type recordField struct {
	name string
	typ  string
}

type recordDef struct {
	name   string
	fields []recordField
}

func canonicalType(expr ast.Expr, records map[string]recordDef) string {
	ident, ok := expr.(*ast.Ident)
	if !ok {
		fail("GO_UNSUPPORTED_TYPE")
	}
	switch ident.Name {
	case "int64":
		return "integer"
	case "float64":
		return "number"
	case "bool":
		return "boolean"
	case "string":
		return "string"
	default:
		if _, ok := records[ident.Name]; ok {
			return ident.Name
		}
		fail("GO_UNSUPPORTED_TYPE:" + ident.Name)
	}
	return ""
}

var emittedBinaryHelpers = map[string]string{
	"elmosCheckedAdd": "+",
	"elmosCheckedSub": "-",
	"elmosCheckedMul": "*",
	"elmosCheckedDiv": "/",
	"elmosCheckedMod": "%",
}

func expression(expr ast.Expr, emittedTarget bool, records map[string]recordDef, functionNames map[string]bool) map[string]any {
	switch value := expr.(type) {
	case *ast.Ident:
		if value.Name == "true" || value.Name == "false" {
			return map[string]any{"kind": "literal", "value": value.Name == "true"}
		}
		return map[string]any{"kind": "name", "value": value.Name}
	case *ast.BasicLit:
		var literal any
		var err error
		switch value.Kind {
		case token.INT:
			literal, err = strconv.ParseInt(value.Value, 0, 64)
		case token.FLOAT:
			literal, err = strconv.ParseFloat(value.Value, 64)
		case token.STRING:
			literal, err = strconv.Unquote(value.Value)
		default:
			fail("GO_UNSUPPORTED_LITERAL")
		}
		if err != nil {
			fail("GO_INVALID_LITERAL")
		}
		return map[string]any{"kind": "literal", "value": literal}
	case *ast.ParenExpr:
		return expression(value.X, emittedTarget, records, functionNames)
	case *ast.BinaryExpr:
		op := value.Op.String()
		switch op {
		case "+", "-", "*", "/", "%", "<", "<=", ">", ">=", "==", "!=", "&&", "||":
		default:
			fail("GO_UNSUPPORTED_OPERATOR:" + op)
		}
		return map[string]any{
			"kind": "binary", "operator": op,
			"left": expression(value.X, emittedTarget, records, functionNames), "right": expression(value.Y, emittedTarget, records, functionNames),
		}
	case *ast.SelectorExpr:
		return map[string]any{
			"kind":   "member_access",
			"target": expression(value.X, emittedTarget, records, functionNames),
			"member": value.Sel.Name,
		}
	case *ast.CompositeLit:
		ident, ok := value.Type.(*ast.Ident)
		if !ok {
			fail(fmt.Sprintf("GO_UNSUPPORTED_EXPRESSION:%T", expr))
		}
		rec, ok := records[ident.Name]
		if !ok {
			fail("GO_UNSUPPORTED_RECORD_TYPE:" + ident.Name)
		}
		argsMap := map[string]any{}
		for i, elt := range value.Elts {
			switch kv := elt.(type) {
			case *ast.KeyValueExpr:
				kIdent, ok := kv.Key.(*ast.Ident)
				if !ok {
					fail("GO_INVALID_RECORD_CONSTRUCT_KEY")
				}
				argsMap[kIdent.Name] = expression(kv.Value, emittedTarget, records, functionNames)
			default:
				if i >= len(rec.fields) {
					fail("GO_RECORD_CONSTRUCT_TOO_MANY_ARGS:" + rec.name)
				}
				argsMap[rec.fields[i].name] = expression(elt, emittedTarget, records, functionNames)
			}
		}
		for _, f := range rec.fields {
			if _, ok := argsMap[f.name]; !ok {
				fail("GO_RECORD_CONSTRUCT_MISSING_FIELD:" + rec.name + "." + f.name)
			}
		}
		return map[string]any{
			"kind":        "record_construct",
			"record_name": rec.name,
			"arguments":   argsMap,
		}
	case *ast.CallExpr:
		if value.Ellipsis.IsValid() {
			fail(fmt.Sprintf("GO_UNSUPPORTED_EXPRESSION:%T", expr))
		}
		callee, ok := value.Fun.(*ast.Ident)
		if !ok {
			fail("GO_EMITTED_HELPER_CALLEE_INVALID")
		}
		if emittedTarget {
			if operator, ok := emittedBinaryHelpers[callee.Name]; ok {
				if len(value.Args) != 2 {
					fail("GO_EMITTED_HELPER_ARITY:" + callee.Name)
				}
				return map[string]any{
					"kind": "binary", "operator": operator,
					"left": expression(value.Args[0], true, records, functionNames), "right": expression(value.Args[1], true, records, functionNames),
				}
			}
			if callee.Name == "elmosNonZeroFloat64" {
				if len(value.Args) != 1 {
					fail("GO_EMITTED_HELPER_ARITY:" + callee.Name)
				}
				return expression(value.Args[0], true, records, functionNames)
			}
		}
		if functionNames != nil && functionNames[callee.Name] {
			args := make([]any, 0, len(value.Args))
			for _, arg := range value.Args {
				args = append(args, expression(arg, emittedTarget, records, functionNames))
			}
			return map[string]any{
				"kind":          "call",
				"function_name": callee.Name,
				"arguments":     args,
			}
		}
		if emittedTarget {
			fail("GO_EMITTED_HELPER_UNRECOGNIZED:" + callee.Name)
		}
		fail(fmt.Sprintf("GO_UNSUPPORTED_EXPRESSION:%T", expr))
	default:
		fail(fmt.Sprintf("GO_UNSUPPORTED_EXPRESSION:%T", expr))
	}
	return nil
}

// ifStatement lifts one `if`, including an `else if` chain.
//
// The Go spec defines `else if` as an else branch whose statement is itself an
// if statement -- it is spelling, not a new construct -- so it lifts into the
// nested `else: [if]` shape the IR already carries. Every other frontend in
// this engine (CPython's ast, SwiftSyntax, the TS compiler, JDT, Roslyn, clang,
// ext/tokenizer) already produces exactly that shape; Go and Rust were the two
// that rejected it instead, which cost twelve directed routes each for no
// semantic reason.
//
// A nested `if` keeps its own Init check because the recursion re-enters here.
func ifStatement(statement *ast.IfStmt, emittedTarget bool, records map[string]recordDef, functionNames map[string]bool) map[string]any {
	if statement.Init != nil {
		fail("GO_IF_INIT_OUTSIDE_CERTIFIED_SUBSET")
	}
	elseBody := []map[string]any{}
	if statement.Else != nil {
		switch alternative := statement.Else.(type) {
		case *ast.BlockStmt:
			elseBody = statements(alternative, emittedTarget, records, functionNames)
		case *ast.IfStmt:
			elseBody = []map[string]any{ifStatement(alternative, emittedTarget, records, functionNames)}
		default:
			fail(fmt.Sprintf("GO_UNSUPPORTED_STATEMENT:%T", statement.Else))
		}
	}
	return map[string]any{
		"kind": "if", "condition": expression(statement.Cond, emittedTarget, records, functionNames),
		"then": statements(statement.Body, emittedTarget, records, functionNames), "else": elseBody,
	}
}

func statements(block *ast.BlockStmt, emittedTarget bool, records map[string]recordDef, functionNames map[string]bool) []map[string]any {
	result := make([]map[string]any, 0, len(block.List))
	for _, raw := range block.List {
		switch statement := raw.(type) {
		case *ast.ReturnStmt:
			if len(statement.Results) != 1 {
				fail("GO_RETURN_EXPRESSION_REQUIRED")
			}
			result = append(result, map[string]any{"kind": "return", "expression": expression(statement.Results[0], emittedTarget, records, functionNames)})
		case *ast.IfStmt:
			result = append(result, ifStatement(statement, emittedTarget, records, functionNames))
		case *ast.DeclStmt:
			genDecl, ok := statement.Decl.(*ast.GenDecl)
			if !ok || genDecl.Tok != token.VAR {
				fail(fmt.Sprintf("GO_UNSUPPORTED_STATEMENT:%T", statement.Decl))
			}
			if len(genDecl.Specs) != 1 {
				fail("GO_MULTIPLE_DECLARATIONS_OUTSIDE_CERTIFIED_SUBSET")
			}
			valueSpec, ok := genDecl.Specs[0].(*ast.ValueSpec)
			if !ok {
				fail("GO_UNSUPPORTED_DECLARATION_SPEC")
			}
			if len(valueSpec.Names) != 1 {
				fail("GO_MULTIPLE_DECLARATIONS_OUTSIDE_CERTIFIED_SUBSET")
			}
			if len(valueSpec.Values) == 0 {
				fail("GO_ANNOTATED_DECLARATION_WITHOUT_VALUE")
			}
			if len(valueSpec.Values) != 1 {
				fail("GO_MULTIPLE_DECLARATIONS_OUTSIDE_CERTIFIED_SUBSET")
			}
			if valueSpec.Type == nil {
				fail("GO_UNANNOTATED_ASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET")
			}
			result = append(result, map[string]any{
				"kind":       "let",
				"name":       valueSpec.Names[0].Name,
				"type":       canonicalType(valueSpec.Type, records),
				"expression": expression(valueSpec.Values[0], emittedTarget, records, functionNames),
			})
		case *ast.AssignStmt:
			if statement.Tok == token.DEFINE {
				fail("GO_UNANNOTATED_ASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET")
			}
			fail("GO_MUTABLE_VARIABLE_OUTSIDE_CERTIFIED_SUBSET")
		case *ast.BranchStmt:
			if statement.Label != nil {
				fail("GO_LABELED_BRANCH_OUTSIDE_CERTIFIED_SUBSET")
			}
			switch statement.Tok {
			case token.BREAK:
				result = append(result, map[string]any{"kind": "break"})
			case token.CONTINUE:
				result = append(result, map[string]any{"kind": "continue"})
			case token.GOTO:
				fail("GO_GOTO_OUTSIDE_CERTIFIED_SUBSET")
			case token.FALLTHROUGH:
				fail("GO_FALLTHROUGH_OUTSIDE_CERTIFIED_SUBSET")
			default:
				fail(fmt.Sprintf("GO_UNSUPPORTED_BRANCH:%s", statement.Tok))
			}
		case *ast.ForStmt:
			if statement.Init == nil && statement.Post == nil {
				if statement.Cond == nil {
					fail("GO_INFINITE_LOOP_OUTSIDE_CERTIFIED_SUBSET")
				}
				result = append(result, map[string]any{
					"kind":      "while",
					"condition": expression(statement.Cond, emittedTarget, records, functionNames),
					"body":      statements(statement.Body, emittedTarget, records, functionNames),
				})
			} else if statement.Init != nil && statement.Cond != nil && statement.Post != nil {
				assign, ok := statement.Init.(*ast.AssignStmt)
				if !ok || (assign.Tok != token.DEFINE && assign.Tok != token.ASSIGN) || len(assign.Lhs) != 1 || len(assign.Rhs) != 1 {
					fail("GO_FOR_INIT_OUTSIDE_CERTIFIED_SUBSET")
				}
				ident, ok := assign.Lhs[0].(*ast.Ident)
				if !ok {
					fail("GO_FOR_INIT_OUTSIDE_CERTIFIED_SUBSET")
				}
				varName := ident.Name
				var startExpr map[string]any
				if call, ok := assign.Rhs[0].(*ast.CallExpr); ok {
					if callFun, ok := call.Fun.(*ast.Ident); ok && callFun.Name == "int64" && len(call.Args) == 1 {
						startExpr = expression(call.Args[0], emittedTarget, records, functionNames)
					} else {
						fail("GO_FOR_INIT_OUTSIDE_CERTIFIED_SUBSET")
					}
				} else {
					startExpr = expression(assign.Rhs[0], emittedTarget, records, functionNames)
				}

				binCond, ok := statement.Cond.(*ast.BinaryExpr)
				if !ok {
					fail("GO_FOR_CONDITION_NON_MONOTONIC")
				}
				leftIdent, ok := binCond.X.(*ast.Ident)
				if !ok || leftIdent.Name != varName {
					fail("GO_FOR_CONDITION_NON_MONOTONIC")
				}
				if binCond.Op != token.LSS {
					fail("GO_FOR_CONDITION_NON_MONOTONIC")
				}
				endExpr := expression(binCond.Y, emittedTarget, records, functionNames)

				var stepExpr map[string]any
				if inc, ok := statement.Post.(*ast.IncDecStmt); ok {
					postIdent, ok := inc.X.(*ast.Ident)
					if !ok || postIdent.Name != varName || inc.Tok != token.INC {
						fail("GO_FOR_POST_NON_MONOTONIC")
					}
				} else if postAssign, ok := statement.Post.(*ast.AssignStmt); ok {
					postIdent, ok := postAssign.Lhs[0].(*ast.Ident)
					if !ok || postIdent.Name != varName || postAssign.Tok != token.ADD_ASSIGN || len(postAssign.Rhs) != 1 {
						fail("GO_FOR_POST_NON_MONOTONIC")
					}
					stepExpr = expression(postAssign.Rhs[0], emittedTarget, records, functionNames)
				} else {
					fail("GO_FOR_POST_NON_MONOTONIC")
				}

				forLoop := map[string]any{
					"kind":  "for",
					"name":  varName,
					"type":  "integer",
					"start": startExpr,
					"end":   endExpr,
					"body":  statements(statement.Body, emittedTarget, records, functionNames),
				}
				if stepExpr != nil {
					forLoop["step"] = stepExpr
				}
				result = append(result, forLoop)
			} else {
				fail("GO_FOR_SHAPE_OUTSIDE_CERTIFIED_SUBSET")
			}
		case *ast.RangeStmt:
			fail("GO_RANGE_LOOP_OUTSIDE_CERTIFIED_SUBSET")
		default:
			fail(fmt.Sprintf("GO_UNSUPPORTED_STATEMENT:%T", raw))
		}
	}
	return result
}

func nodeText(fileSet *token.FileSet, node any) string {
	var buffer bytes.Buffer
	if err := format.Node(&buffer, fileSet, node); err != nil {
		return ""
	}
	return buffer.String()
}

func sourceSpan(fileSet *token.FileSet, sourcePath string, node ast.Node) map[string]any {
	return map[string]any{
		"file":       filepath.Base(sourcePath),
		"start_byte": fileSet.Position(node.Pos()).Offset,
		"end_byte":   fileSet.Position(node.End()).Offset,
	}
}

func moduleInventory(
	fileSet *token.FileSet,
	sourcePath string,
	parsed *ast.File,
	diagnostics []string,
) map[string]any {
	subjects := []map[string]any{}
	packageName := parsed.Name.Name
	for _, group := range parsed.Comments {
		for _, comment := range group.List {
			text := strings.TrimSpace(comment.Text)
			declarationKind := ""
			name := ""
			switch {
			case constraint.IsGoBuild(text):
				declarationKind = "go-build-constraint"
				name = "<go:build>"
				if _, err := constraint.Parse(text); err != nil {
					diagnostics = append(diagnostics, "GO_BUILD_CONSTRAINT_INVALID:"+err.Error())
				}
			case constraint.IsPlusBuild(text):
				declarationKind = "plus-build-constraint"
				name = "<+build>"
				if _, err := constraint.Parse(text); err != nil {
					diagnostics = append(diagnostics, "GO_BUILD_CONSTRAINT_INVALID:"+err.Error())
				}
			case strings.HasPrefix(text, "//go:"):
				fields := strings.Fields(text)
				if len(fields) > 0 {
					directive := strings.TrimPrefix(fields[0], "//go:")
					declarationKind = "go-directive"
					name = "<go:" + directive + ">"
				}
			}
			if declarationKind == "" {
				continue
			}
			subjects = append(subjects, map[string]any{
				"name":             name,
				"qualified_name":   packageName + "." + name,
				"declaration_kind": declarationKind,
				"analyzable":       false,
				"source_span":      sourceSpan(fileSet, sourcePath, comment),
				"signature":        map[string]any{"directive": text},
			})
		}
	}
	for _, declaration := range parsed.Decls {
		switch value := declaration.(type) {
		case *ast.FuncDecl:
			parameters := []map[string]any{}
			for _, field := range value.Type.Params.List {
				names := []string{}
				for _, name := range field.Names {
					names = append(names, name.Name)
				}
				parameters = append(parameters, map[string]any{
					"names": names, "source_type": nodeText(fileSet, field.Type),
				})
			}
			receiver := ""
			declarationKind := "function"
			qualifiedName := packageName + "." + value.Name.Name
			if value.Recv != nil {
				declarationKind = "method"
				receiver = nodeText(fileSet, value.Recv)
				qualifiedName = packageName + "." + receiver + "." + value.Name.Name
			}
			returnType := ""
			if value.Type.Results != nil {
				returnType = nodeText(fileSet, value.Type.Results)
			}
			analyzable := value.Recv == nil && value.Body != nil && value.Type.TypeParams == nil
			subjects = append(subjects, map[string]any{
				"name":             value.Name.Name,
				"qualified_name":   qualifiedName,
				"declaration_kind": declarationKind,
				"analyzable":       analyzable,
				"source_span":      sourceSpan(fileSet, sourcePath, value),
				"signature": map[string]any{
					"parameters": parameters, "source_return_type": returnType, "receiver": receiver,
				},
			})
		case *ast.GenDecl:
			for _, specification := range value.Specs {
				switch spec := specification.(type) {
				case *ast.ImportSpec:
					name := spec.Path.Value
					subjects = append(subjects, map[string]any{
						"name": name, "qualified_name": name, "declaration_kind": "import",
						"analyzable": false, "source_span": sourceSpan(fileSet, sourcePath, spec),
						"signature": map[string]any{},
					})
				case *ast.TypeSpec:
					name := spec.Name.Name
					subjects = append(subjects, map[string]any{
						"name": name, "qualified_name": packageName + "." + name, "declaration_kind": "type",
						"analyzable": false, "source_span": sourceSpan(fileSet, sourcePath, spec),
						"signature": map[string]any{"source_type": nodeText(fileSet, spec.Type)},
					})
				case *ast.ValueSpec:
					kind := "variable"
					if value.Tok == token.CONST {
						kind = "constant"
					}
					for _, identifier := range spec.Names {
						name := identifier.Name
						subjects = append(subjects, map[string]any{
							"name": name, "qualified_name": packageName + "." + name, "declaration_kind": kind,
							"analyzable": false, "source_span": sourceSpan(fileSet, sourcePath, spec),
							"signature": map[string]any{"source_type": nodeText(fileSet, spec.Type)},
						})
					}
				}
			}
		}
	}
	status := "PASSED"
	if len(diagnostics) > 0 {
		status = "FAILED"
	}
	return map[string]any{
		"schema_version": "1.0.0", "kind": "elmos.typed-pure-module-inventory",
		"profile": "typed-pure-module-v1", "source_language": "go",
		"source_file": filepath.Base(sourcePath), "analyzer": "go/parser AST",
		"analyzer_version": runtime.Version(), "enumeration_status": status,
		"subjects": subjects, "diagnostics": diagnostics,
	}
}

func main() {
	arguments := os.Args[1:]
	if len(arguments) > 0 && arguments[0] == "--" {
		arguments = arguments[1:]
	}
	if len(arguments) < 2 || len(arguments) > 3 || (len(arguments) == 3 && arguments[2] != "--emitted-target") {
		fail("USAGE:analyzer SOURCE FUNCTION [--emitted-target]")
	}
	sourcePath, functionName := arguments[0], arguments[1]
	emittedTarget := len(arguments) == 3
	// Batch mode: parsing the target file is the shared cost, and it is
	// identical no matter which function is asked about.  Paying it once per
	// file instead of once per candidate function is the entire point; every
	// per-function answer still comes from `analyzeFunction`, unchanged.
	var batchNames []string
	if strings.HasPrefix(functionName, batchPrefix) {
		seen := map[string]bool{}
		for _, part := range strings.Split(strings.TrimPrefix(functionName, batchPrefix), ",") {
			trimmed := strings.TrimSpace(part)
			// Duplicates are dropped: an answer must not depend on how many
			// times its name was requested.
			if trimmed != "" && !seen[trimmed] {
				seen[trimmed] = true
				batchNames = append(batchNames, trimmed)
			}
		}
		if len(batchNames) == 0 {
			fail("USAGE:analyzer SOURCE --functions=NAME[,NAME...] [--emitted-target]")
		}
		batchMode = true
	}
	fileSet := token.NewFileSet()
	parsed, err := parser.ParseFile(
		fileSet,
		sourcePath,
		nil,
		parser.SkipObjectResolution|parser.ParseComments,
	)
	if err != nil {
		if functionName == "--inventory" {
			payload := map[string]any{
				"schema_version": "1.0.0", "kind": "elmos.typed-pure-module-inventory",
				"profile": "typed-pure-module-v1", "source_language": "go",
				"source_file": filepath.Base(sourcePath), "analyzer": "go/parser AST",
				"analyzer_version": runtime.Version(), "enumeration_status": "FAILED",
				"subjects": []map[string]any{}, "diagnostics": []string{"GO_PARSE_FAILED:" + err.Error()},
			}
			_ = json.NewEncoder(os.Stdout).Encode(payload)
			return
		}
		fail("GO_PARSE_FAILED:" + err.Error())
	}
	if functionName == "--inventory" {
		if err := json.NewEncoder(os.Stdout).Encode(moduleInventory(fileSet, sourcePath, parsed, []string{})); err != nil {
			fail("GO_JSON_ENCODE_FAILED")
		}
		return
	}
	if batchMode {
		emitBatch(sourcePath, parsed, batchNames, emittedTarget)
		return
	}
	payload := analyzeFunction(sourcePath, parsed, functionName, emittedTarget)
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(payload); err != nil {
		fail("GO_JSON_ENCODE_FAILED")
	}
}

func parseRecords(parsed *ast.File) ([]recordDef, map[string]recordDef) {
	recordDefs := []recordDef{}
	recordMap := map[string]recordDef{}

	// First pass: collect struct type definitions
	rawStructs := map[string]*ast.StructType{}
	for _, declaration := range parsed.Decls {
		genDecl, ok := declaration.(*ast.GenDecl)
		if !ok || genDecl.Tok != token.TYPE {
			continue
		}
		for _, spec := range genDecl.Specs {
			typeSpec, ok := spec.(*ast.TypeSpec)
			if !ok {
				continue
			}
			structType, ok := typeSpec.Type.(*ast.StructType)
			if !ok {
				continue
			}
			name := typeSpec.Name.Name
			if _, exists := rawStructs[name]; exists {
				fail("GO_DUPLICATE_RECORD:" + name)
			}
			rawStructs[name] = structType
			recordDefs = append(recordDefs, recordDef{name: name})
			recordMap[name] = recordDef{name: name}
		}
	}

	// Second pass: resolve fields
	for i, r := range recordDefs {
		structType := rawStructs[r.name]
		fields := []recordField{}
		seenFields := map[string]bool{}
		for _, field := range structType.Fields.List {
			if len(field.Names) == 0 {
				fail("GO_EMBEDDED_FIELD_OUTSIDE_CERTIFIED_SUBSET")
			}
			fieldType := canonicalType(field.Type, recordMap)
			for _, ident := range field.Names {
				fName := ident.Name
				if seenFields[fName] {
					fail("GO_DUPLICATE_FIELD:" + r.name + "." + fName)
				}
				seenFields[fName] = true
				fields = append(fields, recordField{name: fName, typ: fieldType})
			}
		}
		recordDefs[i].fields = fields
		recordMap[r.name] = recordDefs[i]
	}

	return recordDefs, recordMap
}

func extractCalleesFromExpr(expr map[string]any, callees *[]string) {
	if expr == nil {
		return
	}
	kind, _ := expr["kind"].(string)
	switch kind {
	case "call":
		if fnName, ok := expr["function_name"].(string); ok {
			*callees = append(*callees, fnName)
		}
		if args, ok := expr["arguments"].([]any); ok {
			for _, arg := range args {
				if argMap, ok := arg.(map[string]any); ok {
					extractCalleesFromExpr(argMap, callees)
				}
			}
		}
	case "binary":
		if left, ok := expr["left"].(map[string]any); ok {
			extractCalleesFromExpr(left, callees)
		}
		if right, ok := expr["right"].(map[string]any); ok {
			extractCalleesFromExpr(right, callees)
		}
	case "member_access":
		if target, ok := expr["target"].(map[string]any); ok {
			extractCalleesFromExpr(target, callees)
		}
	case "record_construct":
		if args, ok := expr["arguments"].(map[string]any); ok {
			for _, v := range args {
				if argMap, ok := v.(map[string]any); ok {
					extractCalleesFromExpr(argMap, callees)
				}
			}
		}
	}
}

func extractCalleesFromStmts(stmts []map[string]any) []string {
	var callees []string
	var walkStmts func(list []map[string]any)
	walkStmts = func(list []map[string]any) {
		for _, stmt := range list {
			kind, _ := stmt["kind"].(string)
			switch kind {
			case "return", "let":
				if expr, ok := stmt["expression"].(map[string]any); ok {
					extractCalleesFromExpr(expr, &callees)
				}
			case "if":
				if cond, ok := stmt["condition"].(map[string]any); ok {
					extractCalleesFromExpr(cond, &callees)
				}
				if thenB, ok := stmt["then"].([]map[string]any); ok {
					walkStmts(thenB)
				}
				if elseB, ok := stmt["else"].([]map[string]any); ok {
					walkStmts(elseB)
				}
			case "while":
				if cond, ok := stmt["condition"].(map[string]any); ok {
					extractCalleesFromExpr(cond, &callees)
				}
				if body, ok := stmt["body"].([]map[string]any); ok {
					walkStmts(body)
				}
			case "for":
				if start, ok := stmt["start"].(map[string]any); ok {
					extractCalleesFromExpr(start, &callees)
				}
				if end, ok := stmt["end"].(map[string]any); ok {
					extractCalleesFromExpr(end, &callees)
				}
				if step, ok := stmt["step"].(map[string]any); ok {
					extractCalleesFromExpr(step, &callees)
				}
				if body, ok := stmt["body"].([]map[string]any); ok {
					walkStmts(body)
				}
			}
		}
	}
	walkStmts(stmts)
	return callees
}

func topologicalSortFunctions(functions []map[string]any) []map[string]any {
	fnMap := make(map[string]map[string]any, len(functions))
	calleesMap := make(map[string]map[string]bool, len(functions))

	for _, fn := range functions {
		name := fn["name"].(string)
		fnMap[name] = fn
		body, _ := fn["body"].([]map[string]any)
		called := extractCalleesFromStmts(body)
		cSet := make(map[string]bool)
		for _, c := range called {
			if c == name {
				fail(fmt.Sprintf("RECURSIVE_CALL_OUTSIDE_CERTIFIED_SUBSET:%s->%s", name, name))
			}
			cSet[c] = true
		}
		calleesMap[name] = cSet
	}

	state := make(map[string]int, len(functions))
	var callPath []string

	var dfs func(name string)
	dfs = func(name string) {
		state[name] = 1
		callPath = append(callPath, name)

		var sortedCallees []string
		for c := range calleesMap[name] {
			if _, ok := fnMap[c]; ok {
				sortedCallees = append(sortedCallees, c)
			}
		}
		sort.Strings(sortedCallees)

		for _, callee := range sortedCallees {
			if state[callee] == 1 {
				idx := -1
				for i, p := range callPath {
					if p == callee {
						idx = i
						break
					}
				}
				cycleSlice := append(callPath[idx:], callee)
				fail("RECURSIVE_CALL_OUTSIDE_CERTIFIED_SUBSET:" + strings.Join(cycleSlice, "->"))
			}
			if state[callee] == 0 {
				dfs(callee)
			}
		}

		callPath = callPath[:len(callPath)-1]
		state[name] = 2
	}

	for _, fn := range functions {
		name := fn["name"].(string)
		if state[name] == 0 {
			dfs(name)
		}
	}

	inDegree := make(map[string]int, len(functions))
	dependents := make(map[string][]string, len(functions))

	for _, fn := range functions {
		name := fn["name"].(string)
		cnt := 0
		for c := range calleesMap[name] {
			if _, ok := fnMap[c]; ok {
				cnt++
				dependents[c] = append(dependents[c], name)
			}
		}
		inDegree[name] = cnt
	}

	originalOrder := make(map[string]int, len(functions))
	for i, fn := range functions {
		originalOrder[fn["name"].(string)] = i
	}

	var ready []string
	for _, fn := range functions {
		name := fn["name"].(string)
		if inDegree[name] == 0 {
			ready = append(ready, name)
		}
	}
	sort.Slice(ready, func(i, j int) bool {
		return originalOrder[ready[i]] < originalOrder[ready[j]]
	})

	var sortedNames []string
	for len(ready) > 0 {
		curr := ready[0]
		ready = ready[1:]
		sortedNames = append(sortedNames, curr)

		deps := dependents[curr]
		sort.Slice(deps, func(i, j int) bool {
			return originalOrder[deps[i]] < originalOrder[deps[j]]
		})

		for _, dep := range deps {
			inDegree[dep]--
			if inDegree[dep] == 0 {
				ready = append(ready, dep)
				sort.Slice(ready, func(i, j int) bool {
					return originalOrder[ready[i]] < originalOrder[ready[j]]
				})
			}
		}
	}

	result := make([]map[string]any, len(sortedNames))
	for i, name := range sortedNames {
		result[i] = fnMap[name]
	}
	return result
}

func parseSingleFunc(
	function *ast.FuncDecl,
	emittedTarget bool,
	recordMap map[string]recordDef,
	functionNames map[string]bool,
) map[string]any {
	if function == nil || function.Recv != nil || function.Body == nil {
		fail("FUNCTION_NOT_FOUND:" + function.Name.Name)
	}
	if function.Type.TypeParams != nil {
		fail("GO_GENERIC_FUNCTION_OUTSIDE_CERTIFIED_SUBSET")
	}
	parameters := []map[string]string{}
	for _, field := range function.Type.Params.List {
		if len(field.Names) != 1 {
			fail("GO_ONE_NAME_PER_PARAMETER_REQUIRED")
		}
		parameters = append(parameters, map[string]string{
			"name": field.Names[0].Name,
			"type": canonicalType(field.Type, recordMap),
		})
	}
	if function.Type.Results == nil || len(function.Type.Results.List) != 1 {
		fail("GO_SINGLE_RETURN_TYPE_REQUIRED")
	}
	return map[string]any{
		"name":        function.Name.Name,
		"parameters":  parameters,
		"return_type": canonicalType(function.Type.Results.List[0].Type, recordMap),
		"body":        statements(function.Body, emittedTarget, recordMap, functionNames),
	}
}

// analyzeFunction is the single source of truth for one function's result.
// Batch mode calls exactly this, so a batch entry cannot drift from what the
// per-function invocation it replaces would have produced.
func analyzeFunction(
	sourcePath string,
	parsed *ast.File,
	functionName string,
	emittedTarget bool,
) map[string]any {
	recordDefs, recordMap := parseRecords(parsed)
	moduleFuncs := make(map[string]*ast.FuncDecl)
	functionNames := make(map[string]bool)

	for _, declaration := range parsed.Decls {
		if function, ok := declaration.(*ast.FuncDecl); ok {
			name := function.Name.Name
			if emittedTarget && (emittedBinaryHelpers[name] != "" || name == "elmosNonZeroFloat64") {
				continue
			}
			if functionNames[name] {
				fail("GO_DUPLICATE_FUNCTION_NAME:" + name)
			}
			moduleFuncs[name] = function
			functionNames[name] = true
		}
	}

	rootDecl, ok := moduleFuncs[functionName]
	if !ok || rootDecl.Recv != nil || rootDecl.Body == nil {
		fail("FUNCTION_NOT_FOUND:" + functionName)
	}

	parsedFunctions := make(map[string]map[string]any)
	queue := []string{functionName}
	visited := map[string]bool{functionName: true}

	for len(queue) > 0 {
		curr := queue[0]
		queue = queue[1:]

		fnDecl := moduleFuncs[curr]
		parsedFn := parseSingleFunc(fnDecl, emittedTarget, recordMap, functionNames)
		parsedFunctions[curr] = parsedFn

		body, _ := parsedFn["body"].([]map[string]any)
		callees := extractCalleesFromStmts(body)
		for _, callee := range callees {
			if _, exists := moduleFuncs[callee]; exists {
				if !visited[callee] {
					visited[callee] = true
					queue = append(queue, callee)
				}
			} else {
				fail("UNKNOWN_FUNCTION:" + callee)
			}
		}
	}

	reachableList := make([]map[string]any, 0, len(parsedFunctions))
	for _, declaration := range parsed.Decls {
		if function, ok := declaration.(*ast.FuncDecl); ok {
			if fn, ok := parsedFunctions[function.Name.Name]; ok {
				reachableList = append(reachableList, fn)
			}
		}
	}

	sortedFunctions := topologicalSortFunctions(reachableList)

	payload := map[string]any{
		"schema_version":   "1.0.0",
		"source_language":  "go",
		"source_file":      filepath.Base(sourcePath),
		"analyzer":         "go/parser AST",
		"analyzer_version": runtime.Version(),
		"functions":        sortedFunctions,
		"diagnostics":      []string{},
	}
	if len(recordDefs) > 0 {
		recordsList := make([]map[string]any, len(recordDefs))
		for i, r := range recordDefs {
			fieldsList := make([]map[string]string, len(r.fields))
			for j, f := range r.fields {
				fieldsList[j] = map[string]string{
					"name": f.name,
					"type": f.typ,
				}
			}
			recordsList[i] = map[string]any{
				"name":   r.name,
				"fields": fieldsList,
			}
		}
		payload["records"] = recordsList
	}
	return payload
}

// analyzeFunctionGuarded runs one function's analysis and converts a domain
// rejection into a value.  Anything that is not a domain rejection is
// re-panicked so the process still dies on it -- batch mode must never turn an
// unexpected crash into a per-function verdict.
func analyzeFunctionGuarded(
	sourcePath string,
	parsed *ast.File,
	functionName string,
	emittedTarget bool,
) (payload map[string]any, code string) {
	defer func() {
		if recovered := recover(); recovered != nil {
			rejection, ok := recovered.(domainRejection)
			if !ok {
				panic(recovered)
			}
			payload, code = nil, rejection.code
		}
	}()
	return analyzeFunction(sourcePath, parsed, functionName, emittedTarget), ""
}

func emitBatch(sourcePath string, parsed *ast.File, names []string, emittedTarget bool) {
	results := []map[string]any{}
	for _, name := range names {
		payload, code := analyzeFunctionGuarded(sourcePath, parsed, name, emittedTarget)
		entry := map[string]any{"function": name}
		if code != "" {
			entry["status"] = "domain_error"
			entry["error"] = code
			entry["value"] = nil
		} else {
			entry["status"] = "ok"
			entry["error"] = nil
			entry["value"] = payload
		}
		results = append(results, entry)
	}
	document := map[string]any{
		"schema_version":   "1.0.0",
		"kind":             "elmos.typed-pure-function-batch",
		"source_language":  "go",
		"source_file":      filepath.Base(sourcePath),
		"analyzer":         "go/parser AST",
		"analyzer_version": runtime.Version(),
		"results":          results,
	}
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(document); err != nil {
		// Not reachable through batchMode's panic path, because encoding
		// happens after every function has already been decided.
		batchMode = false
		fail("GO_JSON_ENCODE_FAILED")
	}
}
