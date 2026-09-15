from __future__ import annotations

import json
from pathlib import Path

from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.models import SynthesisRequest
from elmos_project_synthesis.project_graphs import validate_workspace_graphs
from elmos_project_synthesis.workspace import generate_workspace, render_workspace


def test_scientific_draft_and_approval() -> None:
    draft = create_draft(
        name="neuro-transformer",
        description="Scientific research paper investigating self-attention and residual ablation on deep benchmarks.",
        project_kind="scientific",
        languages=["python"],
    )

    req_ids = {r["id"] for r in draft["requirements"]}
    assert "REQ-SCI-001" in req_ids
    assert "REQ-SCI-002" in req_ids
    assert "REQ-SCI-003" in req_ids
    assert "REQ-SCI-004" in req_ids

    ac_ids = {a["id"] for a in draft["acceptance_criteria"]}
    assert "AC-SCI-001" in ac_ids
    assert "AC-SCI-002" in ac_ids
    assert "AC-SCI-003" in ac_ids
    assert "AC-SCI-004" in ac_ids

    approved = approve_request(
        draft,
        actor="researcher:lead-scientist",
        approved_at="2026-09-15T12:00:00+00:00",
    )
    request = SynthesisRequest.from_mapping(approved)
    assert request.is_scientific is True
    assert request.project_kind == "scientific"
    assert request.research_spec is not None
    assert request.research_spec.framework == "pytorch"
    assert request.research_spec.reproducibility_seed == 42


def test_scientific_workspace_generation() -> None:
    draft = create_draft(
        name="quantum-net",
        description="Deep learning research on quantum graph representations with ablation and LaTeX exports.",
        project_kind="scientific",
        languages=["python"],
    )
    approved = approve_request(
        draft,
        actor="researcher:lab-pi",
        approved_at="2026-09-15T12:00:00+00:00",
    )
    request = SynthesisRequest.from_mapping(approved)
    files = render_workspace(request)

    # Core Scientific Stack Files
    expected_files = [
        "pyproject.toml",
        "environment.yml",
        "reproducibility.py",
        "train.py",
        "distributed_train.py",
        "eval.py",
        "reproduce.sh",
        "datasets/data_loader.py",
        "datasets/streaming_dataset.py",
        "models/neural_net.py",
        "losses/loss.py",
        "trackers/tracker.py",
        "experiments/ablation.py",
        "metrics/significance.py",
        "hpc/slurm.sh",
        "hpc/run_distributed.sh",
        "hpc/cuda_extension.py",
        "hpc/Containerfile.cuda",
        "hpc/Apptainer.def",
        "notebooks/01_exploratory_data_analysis.ipynb",
        "notebooks/02_model_training_and_evaluation.ipynb",
        "scripts/plot_results.py",
        "scripts/export_latex.py",
        "docs/REPRODUCIBILITY.md",
        ".elmos/reproducibility-receipt.json",
        ".elmos/generation-manifest.json",
    ]

    for rel_path in expected_files:
        assert rel_path in files, f"Missing expected scientific file: {rel_path}"

    # Verify Jupyter Notebooks syntax and schema
    for nb_path in (
        "notebooks/01_exploratory_data_analysis.ipynb",
        "notebooks/02_model_training_and_evaluation.ipynb",
    ):
        nb = json.loads(files[nb_path])
        assert nb["nbformat"] == 4
        assert nb["nbformat_minor"] == 5
        assert isinstance(nb["cells"], list)
        assert len(nb["cells"]) >= 4
        cell_types = {c["cell_type"] for c in nb["cells"]}
        assert "markdown" in cell_types
        assert "code" in cell_types

    # Verify Multi-View PSIR
    psir = json.loads(files["requirements/psir.json"])
    assert "business_view" in psir
    assert "research_view" in psir
    assert psir["research_view"]["framework"] == "pytorch"
    assert psir["research_view"]["reproducibility_seed"] == 42
    assert "ablation_matrix" in psir["research_view"]
    assert len(psir["research_view"]["ablation_matrix"]) == 4
    assert "distributed_training" in psir["research_view"]
    assert "data_pipeline" in psir["research_view"]

    # Verify Project Blueprint
    blueprint = json.loads(files["requirements/project-blueprint.json"])
    gen_unit_ids = {u["id"] for u in blueprint["generation_units"]}
    assert "GEN-SCIENTIFIC" in gen_unit_ids

    # Verify Asset Graph
    asset_graph = json.loads(files["requirements/asset-graph.json"])
    asset_node_ids = {n["id"] for n in asset_graph["nodes"]}
    assert "scientific-source" in asset_node_ids
    assert "scientific-notebooks" in asset_node_ids
    assert "scientific-reproducibility" in asset_node_ids
    assert "scientific-hpc" in asset_node_ids

    # Verify Build Graph
    build_graph = json.loads(files["requirements/build-graph.json"])
    build_node_ids = {n["id"] for n in build_graph["nodes"]}
    assert "scientific-generate" in build_node_ids
    assert "scientific-smoke" in build_node_ids
    assert "scientific-train" in build_node_ids
    assert "scientific-distributed-train" in build_node_ids
    assert "scientific-eval" in build_node_ids
    assert "scientific-ablation" in build_node_ids
    assert "scientific-container-build" in build_node_ids

    # Verify Makefile
    makefile = files["Makefile"]
    assert "scientific-train:" in makefile
    assert "scientific-train-ddp:" in makefile
    assert "scientific-eval:" in makefile
    assert "scientific-ablation:" in makefile
    assert "scientific-figures:" in makefile
    assert "scientific-paper:" in makefile
    assert "reproduce:" in makefile
    assert "container-build:" in makefile

    # Verify Root README contains scientific section
    readme = files["README.md"]
    assert "Scientific Deep Learning & Reproducibility Pipeline" in readme
    assert "docs/REPRODUCIBILITY.md" in readme

    # Verify Reproducibility Receipt
    receipt = json.loads(files[".elmos/reproducibility-receipt.json"])
    assert receipt["kind"] == "elmos.scientific-reproducibility-receipt"
    assert receipt["seed_lock"]["global_seed"] == 42
    assert receipt["authority_and_certification"]["evidence_grade"] == "LOCAL_EXECUTED_SELF_ATTESTED"
    assert receipt["authority_and_certification"]["external_hpc_cluster_execution"] == "NOT_RUN"


def test_scientific_workspace_atomic_generation_and_validation(tmp_path: Path) -> None:
    draft = create_draft(
        name="bio-informatics-rep",
        description="Bioinformatics machine learning model with statistical hypothesis verification and reproducible pipeline.",
        project_kind="scientific",
        languages=["python"],
    )
    approved = approve_request(
        draft,
        actor="researcher:bio-director",
        approved_at="2026-09-15T12:00:00+00:00",
    )
    workspace = tmp_path / "bio-workspace"
    manifest = generate_workspace(approved, workspace)

    assert manifest["status"] == "GENERATED"
    assert (workspace / "reproducibility.py").is_file()
    assert (workspace / "distributed_train.py").is_file()
    assert (workspace / "reproduce.sh").is_file()
    assert (workspace / "datasets" / "data_loader.py").is_file()
    assert (workspace / "datasets" / "streaming_dataset.py").is_file()
    assert (workspace / "models" / "neural_net.py").is_file()
    assert (workspace / "losses" / "loss.py").is_file()
    assert (workspace / "experiments" / "ablation.py").is_file()
    assert (workspace / "metrics" / "significance.py").is_file()
    assert (workspace / "hpc" / "run_distributed.sh").is_file()
    assert (workspace / "hpc" / "Containerfile.cuda").is_file()
    assert (workspace / "hpc" / "Apptainer.def").is_file()
    assert (workspace / ".elmos" / "reproducibility-receipt.json").is_file()

    # Validate workspace graphs without errors
    validate_workspace_graphs(workspace)
    assert (workspace / "requirements" / "project-structure.json").is_file()
    assert (workspace / "requirements" / "declared-dependency-graph.json").is_file()
