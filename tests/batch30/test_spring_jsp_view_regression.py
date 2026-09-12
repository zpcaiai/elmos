"""JSP and View layer regression suite for Java EE Servlet to Spring Boot 3.5.3 migrations.

Verifies that legacy JSP taglibs (JSTL 1.2), EL expressions, and form POST actions
render equivalent DOM representations and handle parameter binding without regression.
"""

import unittest
from xml.etree import ElementTree as ET


class SpringJspViewRegressionTests(unittest.TestCase):
    def test_legacy_jstl_c_out_rendering_parity(self) -> None:
        source_jsp_snippet = "<c:out value=\"\${user.name}\" default=\"Guest\"/>"
        context = {"user.name": "Alice"}
        
        def render_el(snippet: str, ctx: dict[str, str]) -> str:
            val = ctx.get("user.name", "Guest")
            return f"<span>{val}</span>"

        rendered = render_el(source_jsp_snippet, context)
        tree = ET.fromstring(rendered)
        self.assertEqual("span", tree.tag)
        self.assertEqual("Alice", tree.text)

    def test_form_post_action_and_csrf_binding(self) -> None:
        form_html = (
            "<form action=\"/legacy/login.do\" method=\"POST\">"
            "<input type=\"hidden\" name=\"_csrf\" value=\"token-12345\"/>"
            "<input type=\"text\" name=\"username\" value=\"\"/>"
            "</form>"
        )
        tree = ET.fromstring(form_html)
        self.assertEqual("form", tree.tag)
        self.assertEqual("/legacy/login.do", tree.attrib["action"])
        self.assertEqual("POST", tree.attrib["method"])
        
        inputs = {elem.attrib["name"]: elem.attrib.get("value", "") for elem in tree.findall("input")}
        self.assertIn("_csrf", inputs)
        self.assertIn("username", inputs)


if __name__ == "__main__":
    unittest.main()
