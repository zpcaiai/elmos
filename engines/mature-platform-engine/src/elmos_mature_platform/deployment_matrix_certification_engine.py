from typing import Dict, List, Optional
from datetime import datetime

from elmos_mature_platform.types import (
    DeploymentEnvironment,
    CertificationStatus,
    DeploymentCell,
    DeploymentMatrix,
    MatrixTestResult
)

class DeploymentMatrixCertificationEngine:
    """
    Engine for certifying deployment matrices across environments and platforms.
    """

    def __init__(self):
        self._matrices: Dict[str, DeploymentMatrix] = {}
        self._cells: Dict[str, DeploymentCell] = {}
        self._test_results: Dict[str, List[MatrixTestResult]] = {}

    def create_matrix(self, matrix: DeploymentMatrix) -> str:
        """Create a new deployment matrix."""
        if not matrix.matrix_id:
            raise ValueError("matrix_id cannot be empty")
        if matrix.matrix_id in self._matrices:
            raise ValueError(f"Matrix with ID {matrix.matrix_id} already exists")
        
        self._matrices[matrix.matrix_id] = matrix
        return matrix.matrix_id

    def add_cell(self, cell: DeploymentCell) -> str:
        """Add a new cell to the system."""
        if not cell.cell_id:
            raise ValueError("cell_id cannot be empty")
        if cell.cell_id in self._cells:
            raise ValueError(f"Cell with ID {cell.cell_id} already exists")
        
        self._cells[cell.cell_id] = cell
        self._test_results[cell.cell_id] = []
        return cell.cell_id

    def record_test_result(self, result: MatrixTestResult) -> None:
        """Record a test result for a deployment cell and update its status."""
        if result.cell_id not in self._cells:
            raise ValueError(f"Cell with ID {result.cell_id} not found")
        
        cell = self._cells[result.cell_id]
        
        # Don't update test counts for WAIVED or PASSED cells (already certified)
        if cell.status in (CertificationStatus.PASSED, CertificationStatus.WAIVED):
            return

        self._test_results[result.cell_id].append(result)
        
        cell.test_count += 1
        if result.passed:
            cell.pass_count += 1
        else:
            cell.fail_count += 1
            
        cell.last_tested = result.timestamp or datetime.utcnow().isoformat()
        
        if cell.fail_count > 0:
            cell.status = CertificationStatus.FAILED
        elif cell.pass_count > 0:
            cell.status = CertificationStatus.IN_PROGRESS

    def certify_cell(self, cell_id: str, certified_by: str) -> DeploymentCell:
        """Certify a cell if all its tests have passed."""
        if cell_id not in self._cells:
            raise ValueError(f"Cell with ID {cell_id} not found")
            
        cell = self._cells[cell_id]
        
        if cell.status == CertificationStatus.NOT_TESTED:
            raise ValueError("Cannot certify a cell that has not been tested")
            
        if cell.fail_count > 0 or cell.pass_count == 0:
            raise ValueError("Cannot certify a cell with failing or missing tests")
            
        cell.status = CertificationStatus.PASSED
        cell.certified_by = certified_by
        return cell

    def waive_cell(self, cell_id: str, reason: str) -> DeploymentCell:
        """Waive a cell from certification requirements."""
        if cell_id not in self._cells:
            raise ValueError(f"Cell with ID {cell_id} not found")
            
        if not reason:
            raise ValueError("Waiver reason must be provided")
            
        cell = self._cells[cell_id]
        cell.status = CertificationStatus.WAIVED
        cell.waiver_reason = reason
        return cell

    def get_matrix_coverage(self, matrix_id: str) -> Dict:
        """Get coverage statistics for a matrix."""
        if matrix_id not in self._matrices:
            raise ValueError(f"Matrix with ID {matrix_id} not found")
            
        matrix = self._matrices[matrix_id]
        if not matrix.cells:
            return {
                "overall_coverage": 0.0,
                "tested_ratio": "0/0",
                "passed_ratio": "0/0",
                "by_environment": {},
                "by_platform": {}
            }
            
        total_cells = len(matrix.cells)
        tested_cells = 0
        passed_or_waived_cells = 0
        
        env_stats = {}
        platform_stats = {}
        
        for cell_id in matrix.cells:
            if cell_id not in self._cells:
                continue
                
            cell = self._cells[cell_id]
            
            # Init stats
            if cell.environment not in env_stats:
                env_stats[cell.environment] = {"total": 0, "passed": 0, "tested": 0}
            if cell.platform not in platform_stats:
                platform_stats[cell.platform] = {"total": 0, "passed": 0, "tested": 0}
                
            env_stats[cell.environment]["total"] += 1
            platform_stats[cell.platform]["total"] += 1
            
            if cell.status != CertificationStatus.NOT_TESTED:
                tested_cells += 1
                env_stats[cell.environment]["tested"] += 1
                platform_stats[cell.platform]["tested"] += 1
                
            if cell.status in (CertificationStatus.PASSED, CertificationStatus.WAIVED):
                passed_or_waived_cells += 1
                env_stats[cell.environment]["passed"] += 1
                platform_stats[cell.platform]["passed"] += 1

        coverage = (passed_or_waived_cells / total_cells) * 100 if total_cells > 0 else 0.0
        
        return {
            "overall_coverage": coverage,
            "tested_ratio": f"{tested_cells}/{total_cells}",
            "passed_ratio": f"{passed_or_waived_cells}/{total_cells}",
            "by_environment": env_stats,
            "by_platform": platform_stats
        }

    def evaluate_matrix(self, matrix_id: str) -> DeploymentMatrix:
        """Evaluate overall matrix status against required environments and platforms."""
        if matrix_id not in self._matrices:
            raise ValueError(f"Matrix with ID {matrix_id} not found")
            
        matrix = self._matrices[matrix_id]
        
        if not matrix.cells:
            matrix.overall_status = CertificationStatus.NOT_TESTED
            matrix.coverage_pct = 0.0
            return matrix
            
        coverage_data = self.get_matrix_coverage(matrix_id)
        matrix.coverage_pct = coverage_data["overall_coverage"]
        
        # Check if all required environments have passing cells
        missing_envs = []
        for env in matrix.required_environments:
            stats = coverage_data["by_environment"].get(env, {})
            if stats.get("passed", 0) == 0:
                missing_envs.append(env)
                
        # Check if all required platforms have passing cells
        missing_platforms = []
        for plat in matrix.required_platforms:
            stats = coverage_data["by_platform"].get(plat, {})
            if stats.get("passed", 0) == 0:
                missing_platforms.append(plat)
                
        has_failures = any(
            self._cells[c].status == CertificationStatus.FAILED
            for c in matrix.cells if c in self._cells
        )
        has_in_progress = any(
            self._cells[c].status == CertificationStatus.IN_PROGRESS
            for c in matrix.cells if c in self._cells
        )
        has_untested = any(
            self._cells[c].status == CertificationStatus.NOT_TESTED
            for c in matrix.cells if c in self._cells
        )
        
        if has_failures:
            matrix.overall_status = CertificationStatus.FAILED
        elif missing_envs or missing_platforms or has_untested:
            matrix.overall_status = CertificationStatus.IN_PROGRESS if (has_in_progress or coverage_data["overall_coverage"] > 0) else CertificationStatus.NOT_TESTED
        else:
            matrix.overall_status = CertificationStatus.PASSED
            
        return matrix

    def get_failing_cells(self, matrix_id: str) -> List[DeploymentCell]:
        """Get all failing cells for a matrix."""
        if matrix_id not in self._matrices:
            raise ValueError(f"Matrix with ID {matrix_id} not found")
            
        matrix = self._matrices[matrix_id]
        return [
            self._cells[c] for c in matrix.cells 
            if c in self._cells and self._cells[c].status == CertificationStatus.FAILED
        ]

    def get_untested_cells(self, matrix_id: str) -> List[DeploymentCell]:
        """Get all untested cells for a matrix."""
        if matrix_id not in self._matrices:
            raise ValueError(f"Matrix with ID {matrix_id} not found")
            
        matrix = self._matrices[matrix_id]
        return [
            self._cells[c] for c in matrix.cells 
            if c in self._cells and self._cells[c].status == CertificationStatus.NOT_TESTED
        ]

    def get_certification_report(self, matrix_id: str) -> Dict:
        """Generate a full certification report for a matrix."""
        if matrix_id not in self._matrices:
            raise ValueError(f"Matrix with ID {matrix_id} not found")
            
        self.evaluate_matrix(matrix_id)
        matrix = self._matrices[matrix_id]
        coverage = self.get_matrix_coverage(matrix_id)
        
        cells_detail = []
        for c_id in matrix.cells:
            if c_id in self._cells:
                cell = self._cells[c_id]
                cells_detail.append({
                    "cell_id": cell.cell_id,
                    "environment": cell.environment,
                    "platform": cell.platform,
                    "status": cell.status,
                    "tests": f"{cell.pass_count}P / {cell.fail_count}F"
                })

        return {
            "matrix_id": matrix.matrix_id,
            "product_name": matrix.product_name,
            "version": matrix.version,
            "overall_status": matrix.overall_status,
            "coverage_pct": matrix.coverage_pct,
            "coverage_stats": coverage,
            "required_environments": matrix.required_environments,
            "required_platforms": matrix.required_platforms,
            "failing_cells": len(self.get_failing_cells(matrix_id)),
            "untested_cells": len(self.get_untested_cells(matrix_id)),
            "cells_detail": cells_detail
        }
