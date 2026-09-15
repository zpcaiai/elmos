from __future__ import annotations

import argparse
from .models import PSIR, Language, Framework, ProjectType, EntitySpec, FieldSpec, FieldType
from .orchestrator import ProjectOrchestrator
from .hybrid_orchestrator import LayeredHybridProjectSynthesizer


def main() -> None:
    parser = argparse.ArgumentParser(description="ELMOS Multi-Language Project Generation Engine")
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to run")

    # generate command
    gen_parser = subparsers.add_parser("generate", help="Generate project from PSIR definition")
    gen_parser.add_argument("--psir", help="Path to PSIR JSON/YAML file")
    gen_parser.add_argument("--lang", default="python", help="Target language (python, go, java, typescript, csharp)")
    gen_parser.add_argument("--output", default="./output", help="Output directory")

    # hybrid-generate command
    hybrid_parser = subparsers.add_parser("hybrid-generate", help="Run 5-layer industrial hybrid generation")
    hybrid_parser.add_argument("--name", default="PricingService", help="Project name")
    hybrid_parser.add_argument("--lang", default="python", choices=["python", "go", "java", "typescript", "csharp"], help="Target language")
    hybrid_parser.add_argument("--output", default="./output_hybrid", help="Target output directory")
    hybrid_parser.add_argument("--native-toolchain", action="store_true", help="Execute real host compiler/test runner on disk (L4)")
    hybrid_parser.add_argument("--self-heal", action="store_true", help="Enable autonomous closed-loop self-healing on failure (L5)")
    hybrid_parser.add_argument("--audit-maturity", action="store_true", default=True, help="Perform L1-L5 commercial maturity assessment")

    # list-combinations
    subparsers.add_parser("list-combinations", help="List supported language and framework combinations")

    args = parser.parse_args()

    if args.command == "hybrid-generate":
        lang_map = {
            "python": (Language.PYTHON, Framework.FASTAPI),
            "go": (Language.GO, Framework.GIN),
            "java": (Language.JAVA, Framework.SPRING_BOOT),
            "typescript": (Language.TYPESCRIPT, Framework.NESTJS),
            "csharp": (Language.CSHARP, Framework.ASPNET),
        }
        target_lang, target_fw = lang_map.get(args.lang.lower(), (Language.PYTHON, Framework.FASTAPI))

        psir = PSIR(
            project_name=args.name,
            description=f"Enterprise {args.name} microservice with DDD and hybrid AI domain synthesis",
            language=target_lang,
            framework=target_fw,
            project_type=ProjectType.REST_API,
            entities=[
                EntitySpec(
                    name="Order",
                    fields=[
                        FieldSpec(name="base_price", type=FieldType.FLOAT, required=True),
                        FieldSpec(name="quantity", type=FieldType.INT, required=True),
                    ]
                )
            ]
        )

        synthesizer = LayeredHybridProjectSynthesizer()
        outcome = synthesizer.synthesize(
            psir=psir,
            run_native_toolchain=args.native_toolchain,
            enable_self_healing=args.self_heal,
            enable_merkle_provenance=True,
            audit_maturity=args.audit_maturity
        )
        outcome.write_to_disk(args.output)
        print(outcome.markdown_report)
        if outcome.maturity_assessment:
            print(f"\n[MATURITY] Evaluated Delivery Maturity: {outcome.maturity_assessment.current_level.value}")
            print(f"[MERKLE] Root Hash: {outcome.evidence_bundle.merkle_root if outcome.evidence_bundle else 'N/A'}")
        print(f"\n[SUCCESS] Generated hybrid project written to: {args.output}")


    elif args.command == "list-combinations":
        orch = ProjectOrchestrator()
        for lang, fw, ptype in orch.get_supported_combinations():
            print(f"- {lang.value} / {fw.value} / {ptype.value}")
    else:
        print(f"Executing {args.command or 'default'}")


if __name__ == "__main__":
    main()
