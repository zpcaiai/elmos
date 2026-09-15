"""Unit and integration tests for Protected Regions and 3-Way Incremental Merger."""

from __future__ import annotations

from pathlib import Path

from elmos_project_synthesis.incremental_merger import (
    extract_custom_regions,
    merge_file_content,
    merge_workspace_files,
)


def test_custom_region_extraction_multi_syntax():
    # 1. C-style (Java, TypeScript, Go, C#)
    c_source = """
package com.example;

public class OrderService {
    // ELMOS:BEGIN_CUSTOM_CODE custom_calc
    public BigDecimal calculateSpecialTax(Order order) {
        return order.getTotal().multiply(new BigDecimal("0.0825"));
    }
    // ELMOS:END_CUSTOM_CODE custom_calc
}
"""
    c_regions = extract_custom_regions(c_source)
    assert "custom_calc" in c_regions
    assert "calculateSpecialTax" in c_regions["custom_calc"].content
    assert c_regions["custom_calc"].syntax == "c_style"

    # 2. Hash-style (Python, Shell, YAML)
    py_source = """
class DataPipeline:
    # ELMOS:BEGIN_CUSTOM_CODE data_transform
    def clean_records(self, df):
        return df.dropna().drop_duplicates()
    # ELMOS:END_CUSTOM_CODE data_transform
"""
    py_regions = extract_custom_regions(py_source)
    assert "data_transform" in py_regions
    assert "drop_duplicates" in py_regions["data_transform"].content
    assert py_regions["data_transform"].syntax == "hash_style"

    # 3. HTML/XML-style
    html_source = """
<div class="dashboard">
  <!-- ELMOS:BEGIN_CUSTOM_CODE custom_widget -->
  <CustomMetricsGraph data={metrics} />
  <!-- ELMOS:END_CUSTOM_CODE custom_widget -->
</div>
"""
    html_regions = extract_custom_regions(html_source)
    assert "custom_widget" in html_regions
    assert "CustomMetricsGraph" in html_regions["custom_widget"].content
    assert html_regions["custom_widget"].syntax == "html_style"


def test_merge_file_preserves_custom_code():
    # Existing file where a developer wrote custom logic
    existing_code = """
import { Order } from './types';

export class OrderProcessor {
  // ELMOS:BEGIN_CUSTOM_CODE validate_order
  customValidate(order: Order): boolean {
    console.log("VIP customer check");
    return order.amount > 0 && order.customerTier === 'VIP';
  }
  // ELMOS:END_CUSTOM_CODE validate_order
}
"""

    # Newly re-generated code template from updated PRD
    new_generated_code = """
import { Order, ShippingAddress } from './types';

export class OrderProcessor {
  // ELMOS:BEGIN_CUSTOM_CODE validate_order
  // default validation placeholder
  // ELMOS:END_CUSTOM_CODE validate_order

  // ELMOS:BEGIN_CUSTOM_CODE shipping_hook
  // new empty region
  // ELMOS:END_CUSTOM_CODE shipping_hook
}
"""

    merge_res = merge_file_content(existing_code, new_generated_code)

    assert merge_res.has_changes is True
    assert "validate_order" in merge_res.preserved_regions
    assert "VIP customer check" in merge_res.merged_content
    assert "customerTier === 'VIP'" in merge_res.merged_content
    # New region is also present
    assert "shipping_hook" in merge_res.merged_content


def test_orphan_region_safety_preservation():
    # Existing file had an extra custom region that the new template omitted
    existing_code = """
// ELMOS:BEGIN_CUSTOM_CODE legacy_calc
function calculateDiscount() {
  return 42;
}
// ELMOS:END_CUSTOM_CODE legacy_calc
"""
    # New template doesn't have legacy_calc marker anymore
    new_template = """
// Pure new template without the legacy_calc marker
export const API_VERSION = 'v2';
"""
    merge_res = merge_file_content(existing_code, new_template)

    assert "legacy_calc" in merge_res.orphan_regions
    # Check that orphan code is NOT lost, but appended safely with notice
    assert "calculateDiscount" in merge_res.merged_content
    assert "ELMOS:BEGIN_ORPHAN_CODE legacy_calc" in merge_res.merged_content


def test_merge_workspace_files_end_to_end(tmp_path: Path):
    ws_dir = tmp_path / "test_workspace"
    ws_dir.mkdir()

    # Create an existing file with custom code
    file1 = ws_dir / "src" / "service.py"
    file1.parent.mkdir(parents=True)
    file1.write_text(
        """
def base_function():
    # ELMOS:BEGIN_CUSTOM_CODE biz_rule
    return "HANDWRITTEN_SECRET_BUSINESS_LOGIC"
    # ELMOS:END_CUSTOM_CODE biz_rule
""",
        encoding="utf-8",
    )

    # Prepare new files payload
    new_files = {
        "src/service.py": """
def base_function():
    # ELMOS:BEGIN_CUSTOM_CODE biz_rule
    return "default"
    # ELMOS:END_CUSTOM_CODE biz_rule

def new_added_function():
    return 100
""",
        "src/new_module.py": "x = 42\n",
    }

    report = merge_workspace_files(ws_dir, new_files, backup=True)

    assert "src/service.py" in report.merged_files
    assert "src/new_module.py" in report.created_files
    assert report.preserved_regions_count == 1
    assert report.backup_path is not None

    # Check that merged service.py retained handwritten code
    merged_text = file1.read_text(encoding="utf-8")
    assert "HANDWRITTEN_SECRET_BUSINESS_LOGIC" in merged_text
    assert "new_added_function" in merged_text

    # Check backup file exists
    backup_file = Path(report.backup_path) / "src" / "service.py"
    assert backup_file.exists()
    assert "HANDWRITTEN_SECRET_BUSINESS_LOGIC" in backup_file.read_text(encoding="utf-8")
