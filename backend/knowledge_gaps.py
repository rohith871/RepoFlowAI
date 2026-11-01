from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from backend.ids import stable_id
from backend.models import Evidence, PkmSnapshot, Symbol
from backend.semantic_layer import ComponentUnderstanding, ExecutionPath, KnowledgeGap


class KnowledgeGapDetector:
    """Detects knowledge gaps, unresolved symbols, and contradictions across the repository."""

    def __init__(
        self,
        snapshot: PkmSnapshot,
        components: dict[str, ComponentUnderstanding],
        execution_paths: list[ExecutionPath],
        source_files_map: dict[str, str],
    ):
        self.snapshot = snapshot
        self.components = components
        self.execution_paths = execution_paths
        self.source_files_map = source_files_map
        self.repo_id = snapshot.revision.repository_id
        self.rev_id = snapshot.revision.pkm_revision_id
        self._symbols_by_name = {s.name: s for s in snapshot.symbols}
        self._symbols_by_id = {s.symbol_id: s for s in snapshot.symbols}
        self._files_by_path = {f.path: f for f in snapshot.files}

    def detect_all(self) -> list[KnowledgeGap]:
        """Run all gap and contradiction detectors and apply resolution policy."""
        gaps: list[KnowledgeGap] = []
        gaps.extend(self._detect_unresolved_calls())
        gaps.extend(self._detect_doc_contradictions())
        gaps.extend(self._detect_incomplete_paths())
        gaps.extend(self._detect_runtime_uncertainties())
        gaps.extend(self._detect_anchor_validity())
        return gaps

    def _detect_unresolved_calls(self) -> list[KnowledgeGap]:
        """Detect calls to symbols that could not be resolved inside repository."""
        gaps: list[KnowledgeGap] = []
        known_stdlib = {"print", "len", "range", "enumerate", "isinstance", "int", "str", "float", "bool", "dict", "list", "set", "tuple", "min", "max", "sum", "sorted", "super", "open", "getattr", "setattr", "hasattr"}

        for file_path, content in self.source_files_map.items():
            if not file_path.endswith(".py"):
                continue
            try:
                tree = ast.parse(content, filename=file_path)
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    call_name = node.func.id
                    if call_name not in known_stdlib and call_name not in self._symbols_by_name:
                        # Unresolved external symbol call
                        gap_id = stable_id("gap", "unresolved_call", file_path, call_name, str(node.lineno))
                        gaps.append(KnowledgeGap(
                            gap_id=gap_id,
                            category="unresolved_symbol",
                            subject_id=None,
                            subject_name=call_name,
                            description=f"Invocation of '{call_name}' at {file_path}:{node.lineno} cannot be statically resolved to a local repository symbol.",
                            evidence_ids=[],
                            resolution_attempt="Checked local symbols and stdlib primitives.",
                            resolution_status="unresolved",
                            limitation_note=f"Static analysis cannot inspect dynamic or external dependency '{call_name}' without runtime telemetry.",
                        ))
        return gaps

    def _detect_doc_contradictions(self) -> list[KnowledgeGap]:
        """Detect contradictions between documentation (README, docstrings) and AST code."""
        gaps: list[KnowledgeGap] = []
        readme_content = ""
        for path, text in self.source_files_map.items():
            if path.lower().endswith("readme.md"):
                readme_content = text
                break

        if readme_content:
            # Check for referenced function/module names in README that do not exist
            words = set(re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b", readme_content))
            for word in ["database", "sqlite", "postgres", "redis", "auth"]:
                if word in words:
                    has_matching_symbol = any(word in s.name.lower() or word in s.qualified_name.lower() for s in self.snapshot.symbols)
                    if not has_matching_symbol:
                        gap_id = stable_id("gap", "readme_feature", word)
                        gaps.append(KnowledgeGap(
                            gap_id=gap_id,
                            category="doc_conflict",
                            subject_name=word,
                            description=f"README mentions '{word}', but no corresponding Python symbol or active connection was found in the analyzed source.",
                            resolution_status="disclosed_limitation",
                            limitation_note=f"Documentation describes '{word}', but implementation remains static declarations or external configuration.",
                        ))

        # Check docstring vs code return consistency
        for comp in self.components.values():
            if comp.kind == "function" and comp.summary:
                # If docstring says 'returns None' but outputs has return value
                doc_lower = comp.summary.lower()
                has_returns_doc = "return" in doc_lower
                has_return_val = bool(comp.outputs and comp.outputs[0].get("type") not in {"None", "NoneType", ""})
                if has_returns_doc and "returns none" in doc_lower and has_return_val:
                    gap_id = stable_id("gap", "doc_return_conflict", comp.component_id)
                    gaps.append(KnowledgeGap(
                        gap_id=gap_id,
                        category="doc_conflict",
                        subject_id=comp.component_id,
                        subject_name=comp.name,
                        description=f"Docstring for {comp.name} mentions returning None, but code specifies return type '{comp.outputs[0].get('type')}'.",
                        resolution_status="unresolved",
                        limitation_note="Implementation takes precedence over docstring text in verified architecture.",
                    ))

        return gaps

    def _detect_incomplete_paths(self) -> list[KnowledgeGap]:
        """Detect execution paths that terminate without a clear return or handler."""
        gaps: list[KnowledgeGap] = []
        for path in self.execution_paths:
            if not path.steps or path.steps[-1].operation_type not in {"return", "entry_call"}:
                gap_id = stable_id("gap", "incomplete_path", path.path_id)
                gaps.append(KnowledgeGap(
                    gap_id=gap_id,
                    category="incomplete_path",
                    subject_id=path.path_id,
                    subject_name=path.name,
                    description=f"Execution path '{path.name}' lacks an explicit terminal return or exit operation.",
                    resolution_status="unresolved",
                    limitation_note="Path may rely on unhandled exceptions or external framework lifecycle.",
                ))
        return gaps

    def _detect_runtime_uncertainties(self) -> list[KnowledgeGap]:
        """Detect SQL schemas, unhandled errors, or external network bounds."""
        gaps: list[KnowledgeGap] = []
        for path, content in self.source_files_map.items():
            if path.endswith(".sql"):
                gap_id = stable_id("gap", "sql_schema", path)
                gaps.append(KnowledgeGap(
                    gap_id=gap_id,
                    category="runtime_uncertainty",
                    subject_name=path,
                    description=f"SQL schema file '{path}' contains static DDL/DML, but runtime database engine connection is unverified statically.",
                    resolution_status="disclosed_limitation",
                    limitation_note="Do not claim database tables were created or populated at runtime without live DB verification.",
                ))
        return gaps

    def _detect_anchor_validity(self) -> list[KnowledgeGap]:
        """Ensure all symbols and evidence have valid, existing line ranges in snapshot files."""
        gaps: list[KnowledgeGap] = []
        for sym in self.snapshot.symbols:
            file_path = sym.qualified_name.split(":", 1)[0]
            file_content = self.source_files_map.get(file_path)
            if file_content is not None:
                line_count = len(file_content.splitlines())
                if sym.line_end > line_count + 1:
                    gap_id = stable_id("gap", "invalid_anchor", sym.symbol_id)
                    gaps.append(KnowledgeGap(
                        gap_id=gap_id,
                        category="missing_evidence",
                        subject_id=sym.symbol_id,
                        subject_name=sym.name,
                        description=f"Symbol '{sym.name}' line_end ({sym.line_end}) exceeds file length ({line_count}).",
                        resolution_status="unresolved",
                        limitation_note="Source snapshot anchor mismatch detected.",
                    ))
        return gaps
