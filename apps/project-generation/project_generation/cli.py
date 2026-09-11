"""Command line interface for project-generation."""

import argparse
import sys
from pathlib import Path

from project_generation.engine import ProjectConfig, ProjectGenerator
from project_generation.validator import DDDValidator


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="project-gen",
        description="Multi-language microservice generator and DDD architectural validator",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Generate subcommand
    gen_parser = subparsers.add_parser("generate", help="Generate a microservice project or K8s manifests")
    gen_parser.add_argument("-lang", "--language", default="go", choices=["go", "python", "k8s"], help="Target language")
    gen_parser.add_argument("-name", "--name", default="my-service", help="Project / Service name")
    gen_parser.add_argument("-module", "--module", default="", help="Go module name (defaults to project name)")
    gen_parser.add_argument("-output", "--output", default="", help="Target output directory")
    gen_parser.add_argument("-template-dir", "--template-dir", default="", help="Custom templates directory path")
    gen_parser.add_argument("-port", "--port", default="8080", help="HTTP port")
    gen_parser.add_argument("-grpc-port", "--grpc-port", default="9090", help="gRPC port")
    gen_parser.add_argument("-database", "--database", default="postgres", help="Database engine")
    gen_parser.add_argument("-desc", "--description", default="", help="Service description")
    gen_parser.add_argument("-author", "--author", default="Elmos Platform Team", help="Author name")

    # Validate subcommand
    val_parser = subparsers.add_parser("validate", help="Validate DDD architecture constraints on a project")
    val_parser.add_argument("path", nargs="?", default=None, help="Project directory to validate (optional positional)")
    val_parser.add_argument("-dir", "--dir", "--directory", dest="directory", default=None, help="Project directory to validate")
    val_parser.add_argument("-format", "--format", choices=["text", "json"], default="text", help="Output format")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "generate":
        config = ProjectConfig(
            language=args.language,
            project_name=args.name,
            module_name=args.module or args.name,
            service_name=args.name,
            port=args.port,
            grpc_port=args.grpc_port,
            database=args.database,
            description=args.description,
            author=args.author,
            output_dir=args.output or f"./{args.name}",
            template_dir=args.template_dir,
        )
        generator = ProjectGenerator(base_template_dir=args.template_dir)
        result = generator.generate(config)

        if not result.success:
            print(f"Error generating project: {result.error}", file=sys.stderr)
            sys.exit(1)
        print(
            f"Successfully generated {config.language} project in '{result.output_dir}' "
            f"({len(result.files_generated)} files created, took {result.duration_seconds:.3f}s)"
        )

    elif args.command == "validate":
        target_dir = args.directory or args.path or "."
        validator = DDDValidator()
        report = validator.validate(target_dir)

        if args.format == "json":
            print(report.to_json())
        else:
            print(str(report))

        if not report.valid:
            sys.exit(1)


if __name__ == "__main__":
    main()
