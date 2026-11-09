package main

import (
	"go/ast"
	"go/parser"
	"go/token"
	"regexp"
	"strconv"
	"testing"
)

// Every command registered in main's switch must appear in the help text.
// A dozen had drifted out of it (review, prepare, verify-seal and others).
func TestHelpListsEveryCommand(t *testing.T) {
	fset := token.NewFileSet()
	file, err := parser.ParseFile(fset, "main.go", nil, 0)
	if err != nil {
		t.Fatalf("parse main.go: %v", err)
	}

	var commands []string
	for _, decl := range file.Decls {
		fn, ok := decl.(*ast.FuncDecl)
		if !ok || fn.Name.Name != "main" || fn.Recv != nil {
			continue
		}
		ast.Inspect(fn.Body, func(n ast.Node) bool {
			clause, ok := n.(*ast.CaseClause)
			if !ok {
				return true
			}
			for _, expr := range clause.List {
				lit, ok := expr.(*ast.BasicLit)
				if !ok || lit.Kind != token.STRING {
					continue
				}
				name, err := strconv.Unquote(lit.Value)
				if err != nil {
					t.Fatalf("unquote %s: %v", lit.Value, err)
				}
				commands = append(commands, name)
			}
			return true
		})
	}
	if len(commands) < 50 {
		t.Fatalf("found only %d commands in main; the switch moved and this test needs updating", len(commands))
	}

	for _, name := range commands {
		switch name {
		case "help", "--help", "-h":
			continue
		}
		listed := regexp.MustCompile(`(^|[^a-z0-9-])` + regexp.QuoteMeta(name) + `([^a-z0-9-]|$)`)
		if !listed.MatchString(helpText) {
			t.Errorf("command %q is registered in main but missing from the help text", name)
		}
	}
}
