from __future__ import annotations

import argparse
import sys
from typing import List, Optional

def main(args: Optional[List[str]] = None) -> int:
    if args is None:
        args = sys.argv[1:]

    parser = argparse.ArgumentParser(description="ELMOS Teaching Subsystem CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # diagram command
    diagram_parser = subparsers.add_parser("diagram", help="Generate diagrams")
    diagram_parser.add_argument("--type", type=str, help="Type of diagram")
    
    # analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Run project analysis")
    analyze_parser.add_argument("--dir", type=str, help="Directory to analyze")
    
    # tour command
    tour_parser = subparsers.add_parser("tour", help="Generate guided tours")
    tour_parser.add_argument("--type", type=str, help="Type of tour")
    
    # export command
    export_parser = subparsers.add_parser("export", help="Export diagrams/reports")
    export_parser.add_argument("--format", type=str, help="Export format")

    parsed_args = parser.parse_args(args)

    if not parsed_args.command:
        parser.print_help()
        return 1

    print(f"Executing command: {parsed_args.command}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
