from __future__ import annotations
import argparse
from .psir_parser import PSIRParser
from .orchestrator import ProjectOrchestrator

def main():
    parser = argparse.ArgumentParser(description="ELMOS Project Generation Engine")
    parser.add_argument("command", choices=["generate", "generate-all", "validate", "list-combinations"])
    args = parser.parse_args()
    print("Executing", args.command)

if __name__ == "__main__":
    main()
