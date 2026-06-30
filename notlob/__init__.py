try:
    from importlib.metadata import version as _pkg_version
    __version__: str = _pkg_version("notlob")
except Exception:
    __version__ = "dev"

from .parser import parse, parse_file, to_dict, to_json
from .model import (
    from_tree,
    Ref, Span,
    Module, Subheading, CodeBlock, Claim, ProseBlock, BulletBlock,
    PostText, TestsSection, TestGroup,
    BindingSection, ReferencesSection, AppendixSection,
)
from .graph import (
    build, enrich, validate_refs,
    NameGraph, Node, NodeKind, Edge, EdgeKind,
    RefError,
    module_address, subheading_address, symbol_address,
    property_address, claim_address,
)
from .project import build_package

__all__ = [
    "parse", "parse_file", "to_dict", "to_json",
    "from_tree",
    "Ref", "Span",
    "Module", "Subheading", "CodeBlock", "Claim", "ProseBlock",
    "PostText", "TestsSection", "TestGroup",
    "BindingSection", "ReferencesSection", "AppendixSection",
    "build", "enrich", "validate_refs", "build_package",
    "NameGraph", "Node", "NodeKind", "Edge", "EdgeKind",
    "RefError",
    "module_address", "subheading_address", "symbol_address",
    "property_address", "claim_address",
]
