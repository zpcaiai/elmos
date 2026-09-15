import pytest
from elmos_multilang_project_generation.domain_slot import (
    DomainSlotSpec, DomainSlotParser, SlotParameter, SlotInvariant, SlotType
)

def test_domain_slot_parser_find_and_replace():
    code = (
        "package main\n"
        "// [[ELMOS_DOMAIN_SLOT_START: SLOT_TEST | TestMethod]]\n"
        "func TestMethod() int {\n"
        "    return 42\n"
        "}\n"
        "// [[ELMOS_DOMAIN_SLOT_END: SLOT_TEST]]\n"
        "func Other() {}\n"
    )

    slots = DomainSlotParser.find_slots_in_content(code)
    assert len(slots) == 1
    slot_id, slot_name, body = slots[0]
    assert slot_id == "SLOT_TEST"
    assert slot_name == "TestMethod"
    assert "return 42" in body

    new_body = "func TestMethod() int {\n    return 100\n}"
    updated = DomainSlotParser.replace_slot(code, "SLOT_TEST", new_body, comment_prefix="//")
    assert "return 100" in updated
    assert "return 42" not in updated
    assert "// [[ELMOS_DOMAIN_SLOT_START: SLOT_TEST | TestMethod]]" in updated
    assert "// [[ELMOS_DOMAIN_SLOT_END: SLOT_TEST]]" in updated

def test_domain_slot_python_hash_comment():
    py_code = (
        "class Svc:\n"
        "# [[ELMOS_DOMAIN_SLOT_START: SLOT_PY | PyMethod]]\n"
        "    def calc(self):\n"
        "        return 1\n"
        "# [[ELMOS_DOMAIN_SLOT_END: SLOT_PY]]\n"
    )
    slots = DomainSlotParser.find_slots_in_content(py_code)
    assert len(slots) == 1
    assert slots[0][0] == "SLOT_PY"

    updated = DomainSlotParser.replace_slot(py_code, "SLOT_PY", "    def calc(self):\n        return 999", comment_prefix="#")
    assert "return 999" in updated
    assert "# [[ELMOS_DOMAIN_SLOT_END: SLOT_PY]]" in updated
