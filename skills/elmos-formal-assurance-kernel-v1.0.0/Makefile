PYTHON ?= python3
export PYTHONPATH := reference-kernel

.PHONY: validate test demo catalog p05 checksums package

validate:
	$(PYTHON) scripts/validate_package.py

test:
	$(PYTHON) -m unittest discover -s reference-kernel/tests -v

demo:
	$(PYTHON) scripts/run_reference_kernel_demo.py

catalog:
	$(PYTHON) scripts/generate_catalog.py

p05:
	$(PYTHON) scripts/check_p05_gate.py --evidence examples/scenarios/p05-evidence.json

checksums:
	$(PYTHON) scripts/generate_checksums.py

package: validate test checksums
	$(PYTHON) scripts/package_release.py
