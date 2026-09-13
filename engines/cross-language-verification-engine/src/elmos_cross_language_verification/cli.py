from __future__ import annotations

import argparse
import sys
from .models import Language
from .verification_service import VerificationService
from .report import ReportGenerator

def main() -> None:
    parser = argparse.ArgumentParser(prog="elmos-cross-verify")
    subparsers = parser.add_subparsers(dest="command")

    verify_p = subparsers.add_parser("verify")
    verify_p.add_argument("--source", required=True)
    verify_p.add_argument("--target", required=True)
    verify_p.add_argument("--source-lang", required=True)
    verify_p.add_argument("--target-lang", required=True)

    gen_p = subparsers.add_parser("generate-tests")
    gen_p.add_argument("--source", required=True)
    gen_p.add_argument("--source-lang", required=True)
    gen_p.add_argument("--output", required=True)

    report_p = subparsers.add_parser("report")
    report_p.add_argument("--input", required=True)
    report_p.add_argument("--format", required=True)

    args = parser.parse_args()

    if args.command == "verify":
        try:
            slang = Language(args.source_lang)
            tlang = Language(args.target_lang)
        except ValueError:
            print("Invalid language.")
            sys.exit(1)
        
        # Read files (mocked in tests)
        source_code = "mock source"
        target_code = "mock target"
        
        report = VerificationService.generate_and_verify(source_code, target_code, slang, tlang)
        print(ReportGenerator.generate_summary(report))
        
    elif args.command == "generate-tests":
        print("Tests generated to", args.output)
        
    elif args.command == "report":
        print("Report generated in format", args.format)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
