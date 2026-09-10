package daemon

import (
	"bytes"
	"errors"
	"go/ast"
	"go/format"
	"go/parser"
	"go/token"
	"strings"
	"sync"
)

// Industrial Go AST Safe Code & Test Self-Healing Engine.

type CodeRepairMutationRule struct {
	RuleID          string `json:"rule_id"`
	TargetFunction  string `json:"target_function"`
	OldIdentifier   string `json:"old_identifier"`
	NewIdentifier   string `json:"new_identifier"`
	PreserveAsserts bool   `json:"preserve_asserts"`
	StrictSafety    bool   `json:"strict_safety"`
}

func (r *CodeRepairMutationRule) Validate() error {
	if r.RuleID == "" {
		return errors.New("rule_id cannot be empty")
	}
	if r.OldIdentifier == "" || r.NewIdentifier == "" {
		return errors.New("identifiers cannot be empty")
	}
	return nil
}

func (r *CodeRepairMutationRule) IsApplicable(fnName string) bool {
	return r.TargetFunction == fnName || r.TargetFunction == "*"
}

// ASTSafeCodeRewriter applies validated transformations while enforcing anti-cheating invariants.
type ASTSafeCodeRewriter struct {
	fileSet *token.FileSet
	mu      sync.Mutex
}

func NewASTSafeCodeRewriter() *ASTSafeCodeRewriter {
	return &ASTSafeCodeRewriter{fileSet: token.NewFileSet()}
}

func (rw *ASTSafeCodeRewriter) ValidateSourceSafety(src string) error {
	if strings.Contains(src, "assert True") || strings.Contains(src, "assert 1 == 1") {
		return errors.New("anti-cheating: tautological assertion detected")
	}
	if strings.Contains(src, "t.Skip(") || strings.Contains(src, "@unittest.skip") {
		return errors.New("anti-cheating: test skip detected")
	}
	if strings.Contains(src, "time.Sleep(") {
		return errors.New("anti-cheating: sleep injection detected")
	}
	return nil
}

func (rw *ASTSafeCodeRewriter) RenameIdentifierInSource(src []byte, oldName, newName string) ([]byte, int, error) {
	rw.mu.Lock()
	defer rw.mu.Unlock()
	f, err := parser.ParseFile(rw.fileSet, "repair.go", src, parser.ParseComments)
	if err != nil {
		return nil, 0, err
	}
	renameCount := 0
	ast.Inspect(f, func(n ast.Node) bool {
		if ident, ok := n.(*ast.Ident); ok {
			if ident.Name == oldName {
				ident.Name = newName
				renameCount++
			}
		}
		return true
	})
	var buf bytes.Buffer
	if err := format.Node(&buf, rw.fileSet, f); err != nil {
		return nil, 0, err
	}
	return buf.Bytes(), renameCount, nil
}

// GoASTSafeTransformer validates and rewrites Go AST safely.
type GoASTSafeTransformer struct {
	rewriter *ASTSafeCodeRewriter
}

func NewGoASTSafeTransformer() *GoASTSafeTransformer {
	return &GoASTSafeTransformer{
		rewriter: NewASTSafeCodeRewriter(),
	}
}

func (t *GoASTSafeTransformer) ValidateGoSyntax(filename string, src []byte) error {
	fset := token.NewFileSet()
	_, err := parser.ParseFile(fset, filename, src, parser.AllErrors)
	return err
}

func (t *GoASTSafeTransformer) CountAssertions(filename string, src []byte) (int, error) {
	fset := token.NewFileSet()
	f, err := parser.ParseFile(fset, filename, src, parser.ParseComments)
	if err != nil {
		return 0, err
	}
	count := 0
	ast.Inspect(f, func(n ast.Node) bool {
		call, ok := n.(*ast.CallExpr)
		if !ok {
			return true
		}
		if sel, ok := call.Fun.(*ast.SelectorExpr); ok {
			switch sel.Sel.Name {
			case "Errorf", "Fatalf", "Fail", "FailNow", "Error", "Fatal", "True", "False", "Equal":
				count++
			}
		}
		return true
	})
	return count, nil
}

func (t *GoASTSafeTransformer) ReplaceIdentifierInFunction(filename string, src []byte, fnName, oldName, newName string) ([]byte, error) {
	fset := token.NewFileSet()
	f, err := parser.ParseFile(fset, filename, src, parser.ParseComments)
	if err != nil {
		return nil, err
	}
	ast.Inspect(f, func(n ast.Node) bool {
		fn, ok := n.(*ast.FuncDecl)
		if !ok || fn.Name.Name != fnName {
			return true
		}
		ast.Inspect(fn.Body, func(inner ast.Node) bool {
			if ident, ok := inner.(*ast.Ident); ok {
				if ident.Name == oldName {
					ident.Name = newName
				}
			}
			return true
		})
		return false
	})
	var buf bytes.Buffer
	if err := format.Node(&buf, fset, f); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}
