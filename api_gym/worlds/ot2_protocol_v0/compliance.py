"""Static check that a protocol stays inside the official Opentrons Python API.

The rules come from the collaborator's operating specification: compose only
the listed ``protocol_api`` actions, take geometry only from library objects,
and never rebuild an existing action from raw coordinates, bypass the library,
or use undocumented interfaces. The official analyzer judges whether the
protocol runs; this module judges how it was written.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

ALLOWED_ACTIONS = frozenset({
    "load_labware", "load_labware_from_definition", "load_instrument", "define_liquid", "load_liquid",
    "pick_up_tip", "drop_tip", "aspirate", "dispense", "blow_out", "air_gap", "touch_tip", "mix",
    "move_to", "delay", "comment", "home", "pause",
})
GEOMETRY_METHODS = frozenset({"top", "bottom", "center", "move"})
LABWARE_ACCESSORS = frozenset({"wells", "rows", "columns", "wells_by_name", "rows_by_name", "columns_by_name"})
# Documented protocol_api methods that are outside the agreed action set.
OUTSIDE_AGREED_SET = frozenset({
    "transfer", "distribute", "consolidate", "return_tip", "reset_tipracks", "move_labware", "load_module",
    "load_adapter", "load_trash_bin", "load_waste_chute", "set_rail_lights", "configure_nozzle_layout",
    "prepare_to_aspirate", "detect_liquid_presence", "require_liquid_presence", "measure_liquid_height",
    "set_offset", "home_plunger", "drop_tip_in_place", "move_to_addressable_area", "transfer_with_liquid_class",
    "load_labware_by_name", "load_labware_object",
})
ALLOWED_IMPORTS = {
    "opentrons": frozenset({"protocol_api", "types"}),
    "opentrons.protocol_api": None,
    "opentrons.types": frozenset({"Point", "Location", "Mount"}),
    "math": None,
    "typing": None,
}
FORBIDDEN_BUILTINS = frozenset({
    "exec", "eval", "compile", "__import__", "open", "getattr", "setattr", "delattr", "globals", "locals",
    "vars", "input", "breakpoint",
})
DEFINITION_KEYS = frozenset({
    "wells", "depth", "diameter", "dimensions", "cornerOffsetFromSlot", "ordering", "totalLiquidVolume",
    "xDimension", "yDimension", "zDimension",
})


@dataclass(frozen=True)
class Violation:
    code: str
    line: int
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "line": self.line, "detail": self.detail}


def check_protocol_source(source: str) -> tuple[Violation, ...]:
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        return (Violation("SYNTAX_ERROR", error.lineno or 0, str(error.msg)),)
    visitor = _ComplianceVisitor()
    visitor.visit(tree)
    return tuple(sorted(visitor.violations, key=lambda v: (v.line, v.code)))


class _ComplianceVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[Violation] = []

    def _add(self, code: str, node: ast.AST, detail: str) -> None:
        self.violations.append(Violation(code, getattr(node, "lineno", 0), detail))

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name not in ALLOWED_IMPORTS:
                self._add("IMPORT_NOT_ALLOWED", node, f"import {alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        if node.level or module not in ALLOWED_IMPORTS:
            self._add("IMPORT_NOT_ALLOWED", node, f"from {module} import ...")
        else:
            allowed = ALLOWED_IMPORTS[module]
            for alias in node.names:
                if allowed is not None and alias.name not in allowed:
                    self._add("IMPORT_NOT_ALLOWED", node, f"from {module} import {alias.name}")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("_"):
            self._add("PRIVATE_INTERFACE", node, f"access to private attribute .{node.attr}")
        if isinstance(node.value, ast.Name) and node.value.id == "opentrons" and node.attr not in ALLOWED_IMPORTS["opentrons"]:
            self._add("IMPORT_NOT_ALLOWED", node, f"use of opentrons.{node.attr}")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id.startswith("__") and node.id != "__name__":
            self._add("PRIVATE_INTERFACE", node, f"access to {node.id}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name):
            if func.id in FORBIDDEN_BUILTINS:
                self._add("FORBIDDEN_BUILTIN", node, f"call to {func.id}()")
            if func.id == "Location":
                self._add("RAW_COORDINATE_LOCATION", node, "Location built from coordinates instead of a library object")
        elif isinstance(func, ast.Attribute):
            name = func.attr
            if name == "Location":
                self._add("RAW_COORDINATE_LOCATION", node, "Location built from coordinates instead of a library object")
            elif name in OUTSIDE_AGREED_SET:
                self._add("ACTION_NOT_IN_AGREED_SET", node, f".{name}() is outside the agreed action set")
            elif name == "get" and node.args and _string_constant(node.args[0]) in DEFINITION_KEYS:
                self._add("RECOMPUTED_GEOMETRY", node, f"reads '{_string_constant(node.args[0])}' from a definition")
        for keyword in node.keywords:
            if keyword.arg == "force_direct" and not (
                isinstance(keyword.value, ast.Constant) and keyword.value.value is False
            ):
                self._add("FORCE_DIRECT", keyword.value, "force_direct is not False")
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        key = _string_constant(node.slice)
        if key in DEFINITION_KEYS:
            self._add("RECOMPUTED_GEOMETRY", node, f"reads '{key}' from a definition")
        self.generic_visit(node)


def _string_constant(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None
