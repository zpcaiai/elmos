package main

import (
	"flag"
	"fmt"
	"os"

	"apps/project-generation/pkg/generator"
	"apps/project-generation/pkg/validator"
)

func printUsage() {
	fmt.Println(`project-gen - Multi-language microservice generator and DDD architectural validator

Usage:
  project-gen <command> [arguments]

Commands:
  generate    Generate a clean DDD microservice skeleton or K8s manifests
  validate    Validate DDD layer architectural compliance on a directory
  help        Show this help message

Run 'project-gen <command> -h' for more details on each command.`)
}

func main() {
	if len(os.Args) < 2 {
		printUsage()
		os.Exit(1)
	}

	switch os.Args[1] {
	case "generate":
		handleGenerate(os.Args[2:])
	case "validate":
		handleValidate(os.Args[2:])
	case "help", "-h", "--help":
		printUsage()
	default:
		fmt.Fprintf(os.Stderr, "Unknown command '%s'\n\n", os.Args[1])
		printUsage()
		os.Exit(1)
	}
}

func handleGenerate(args []string) {
	fs := flag.NewFlagSet("generate", flag.ExitOnError)
	lang := fs.String("lang", "go", "Target language: go, python, or k8s")
	name := fs.String("name", "my-service", "Project / Service name")
	module := fs.String("module", "", "Go module path (defaults to name)")
	output := fs.String("output", "", "Target output directory (defaults to ./<name>)")
	tmplDir := fs.String("template-dir", "", "Custom templates directory path")
	port := fs.String("port", "8080", "Service HTTP port")
	grpcPort := fs.String("grpc-port", "9090", "Service gRPC port")
	db := fs.String("database", "postgres", "Database technology (postgres, mysql, etc.)")
	desc := fs.String("desc", "", "Service description")
	author := fs.String("author", "Elmos Platform Team", "Author / Team name")

	if err := fs.Parse(args); err != nil {
		os.Exit(1)
	}

	if *output == "" {
		*output = fmt.Sprintf("./%s", *name)
	}
	if *module == "" {
		*module = *name
	}

	cfg := generator.ProjectConfig{
		Language:    generator.SupportedLanguage(*lang),
		ProjectName: *name,
		ModuleName:  *module,
		ServiceName: *name,
		Port:        *port,
		GRPCPort:    *grpcPort,
		Database:    *db,
		Description: *desc,
		Author:      *author,
		OutputDir:   *output,
		TemplateDir: *tmplDir,
	}

	engine := generator.NewEngine(*tmplDir)
	result, err := engine.Generate(cfg)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error generating project: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("Successfully generated %s project in '%s' (%d files created, took %v)\n",
		*lang, result.OutputDir, len(result.FilesGenerated), result.Duration)
}

func handleValidate(args []string) {
	fs := flag.NewFlagSet("validate", flag.ExitOnError)
	dir := fs.String("dir", ".", "Directory to validate")
	format := fs.String("format", "text", "Output format: text or json")

	if err := fs.Parse(args); err != nil {
		os.Exit(1)
	}

	v := validator.NewDDDValidator()
	report, err := v.Validate(*dir)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error running DDD validation: %v\n", err)
		os.Exit(1)
	}

	if *format == "json" {
		jsonStr, _ := report.ToJSON()
		fmt.Println(jsonStr)
	} else {
		fmt.Println(report.String())
	}

	if !report.Valid {
		os.Exit(1)
	}
}
