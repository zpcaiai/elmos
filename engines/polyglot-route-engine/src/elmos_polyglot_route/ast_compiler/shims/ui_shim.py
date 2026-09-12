"""UI Cross-Framework Component and Event Shim Registry."""

from __future__ import annotations

from typing import Dict, Any


class UIShimRegistry:
    """Maps universal UI tags and events across React, Flutter, Swift, and VB6."""

    TAG_MAPPINGS: Dict[str, Dict[str, str]] = {
        "Button": {
            "react": "<button onClick={{{handler}}}>{text}</button>",
            "flutter": "ElevatedButton(onPressed: {handler}, child: Text('{text}'))",
            "swift": "Button('{text}') { {handler}() }",
            "vb6": "CommandButton (Caption = '{text}')",
        },
        "Text": {
            "react": "<span>{text}</span>",
            "flutter": "Text('{text}')",
            "swift": "Text('{text}')",
            "vb6": "Label (Caption = '{text}')",
        },
        "Container": {
            "react": "<div className='container'>{children}</div>",
            "flutter": "Container(child: {children})",
            "swift": "VStack { {children} }",
            "vb6": "Frame",
        },
        "TextField": {
            "react": "<input type='text' onChange={{{handler}}} />",
            "flutter": "TextField(onChanged: {handler})",
            "swift": "TextField('{placeholder}', text: ${binding})",
            "vb6": "TextBox",
        }
    }

    @classmethod
    def get_tag_template(cls, tag: str, target_lang: str) -> str:
        lang = target_lang.lower().strip()
        tag_dict = cls.TAG_MAPPINGS.get(tag, {})
        return tag_dict.get(lang, f"<{tag}>{{children}}</{tag}>")
