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
	"strconv"
	"strings"
)

func fail(code string) {
	fmt.Fprintln(os.Stderr, code)
	os.Exit(2)
}

func canonicalType(expr ast.Expr) string {
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

func expression(expr ast.Expr, emittedTarget bool) map[string]any {
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
		return expression(value.X, emittedTarget)
	case *ast.BinaryExpr:
		op := value.Op.String()
		switch op {
		case "+", "-", "*", "/", "%", "<", "<=", ">", ">=", "==", "!=", "&&", "||":
		default:
			fail("GO_UNSUPPORTED_OPERATOR:" + op)
		}
		return map[string]any{
			"kind": "binary", "operator": op,
			"left": expression(value.X, emittedTarget), "right": expression(value.Y, emittedTarget),
		}
	case *ast.CallExpr:
		if !emittedTarget || value.Ellipsis.IsValid() {
			fail(fmt.Sprintf("GO_UNSUPPORTED_EXPRESSION:%T", expr))
		}
		callee, ok := value.Fun.(*ast.Ident)
		if !ok {
			fail("GO_EMITTED_HELPER_CALLEE_INVALID")
		}
		if operator, ok := emittedBinaryHelpers[callee.Name]; ok {
			if len(value.Args) != 2 {
				fail("GO_EMITTED_HELPER_ARITY:" + callee.Name)
			}
			return map[string]any{
				"kind": "binary", "operator": operator,
				"left": expression(value.Args[0], true), "right": expression(value.Args[1], true),
			}
		}
		if callee.Name == "elmosNonZeroFloat64" {
			if len(value.Args) != 1 {
				fail("GO_EMITTED_HELPER_ARITY:" + callee.Name)
			}
			return expression(value.Args[0], true)
		}
		fail("GO_EMITTED_HELPER_UNRECOGNIZED:" + callee.Name)
	default:
		fail(fmt.Sprintf("GO_UNSUPPORTED_EXPRESSION:%T", expr))
	}
	return nil
}

func statements(block *ast.BlockStmt, emittedTarget bool) []map[string]any {
	result := make([]map[string]any, 0, len(block.List))
	for _, raw := range block.List {
		switch statement := raw.(type) {
		case *ast.ReturnStmt:
			if len(statement.Results) != 1 {
				fail("GO_RETURN_EXPRESSION_REQUIRED")
			}
			result = append(result, map[string]any{"kind": "return", "expression": expression(statement.Results[0], emittedTarget)})
		case *ast.IfStmt:
			if statement.Init != nil {
				fail("GO_IF_INIT_OUTSIDE_CERTIFIED_SUBSET")
			}
			elseBody := []map[string]any{}
			if statement.Else != nil {
				elseBlock, ok := statement.Else.(*ast.BlockStmt)
				if !ok {
					fail("GO_ELSE_IF_OUTSIDE_CERTIFIED_SUBSET")
				}
				elseBody = statements(elseBlock, emittedTarget)
			}
			result = append(result, map[string]any{
				"kind": "if", "condition": expression(statement.Cond, emittedTarget),
				"then": statements(statement.Body, emittedTarget), "else": elseBody,
			})
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
	var candidate *ast.FuncDecl
	for _, declaration := range parsed.Decls {
		if function, ok := declaration.(*ast.FuncDecl); ok && function.Name.Name == functionName {
			candidate = function
			break
		}
	}
	if candidate == nil || candidate.Recv != nil || candidate.Body == nil {
		fail("FUNCTION_NOT_FOUND:" + functionName)
	}
	if candidate.Type.TypeParams != nil {
		fail("GO_GENERIC_FUNCTION_OUTSIDE_CERTIFIED_SUBSET")
	}
	parameters := []map[string]string{}
	for _, field := range candidate.Type.Params.List {
		if len(field.Names) != 1 {
			fail("GO_ONE_NAME_PER_PARAMETER_REQUIRED")
		}
		parameters = append(parameters, map[string]string{"name": field.Names[0].Name, "type": canonicalType(field.Type)})
	}
	if candidate.Type.Results == nil || len(candidate.Type.Results.List) != 1 {
		fail("GO_SINGLE_RETURN_TYPE_REQUIRED")
	}
	payload := map[string]any{
		"schema_version":   "1.0.0",
		"source_language":  "go",
		"source_file":      filepath.Base(sourcePath),
		"analyzer":         "go/parser AST",
		"analyzer_version": runtime.Version(),
		"functions": []map[string]any{{
			"name":        candidate.Name.Name,
			"parameters":  parameters,
			"return_type": canonicalType(candidate.Type.Results.List[0].Type),
			"body":        statements(candidate.Body, emittedTarget),
		}},
		"diagnostics": []string{},
	}
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(payload); err != nil {
		fail("GO_JSON_ENCODE_FAILED")
	}
}
