from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any

from backend.ids import stable_id
from backend.models import (
    AssertionStatus,
    ClaimLevel,
    Evidence,
    Fact,
    PkmSnapshot,
    Relationship,
    SourceFile,
    Symbol,
    VerificationStatus,
)
from backend.semantic_layer import ComponentUnderstanding, ProvenanceKind


class SemanticUnderstandingEngine:
    """Multi-level code understanding engine for RepoFlow AI."""

    def __init__(self, snapshot: PkmSnapshot, source_files_map: dict[str, str]):
        self.snapshot = snapshot
        self.source_files_map = source_files_map  # rel_path -> file content
        self.repo_id = snapshot.revision.repository_id
        self.rev_id = snapshot.revision.pkm_revision_id
        self._parsed_trees: dict[str, ast.AST] = {}
        self._import_tables: dict[str, dict[str, tuple[str, str]]] = {}  # file_path -> {imported_name: (target_file, target_symbol)}
        self._symbols_by_id: dict[str, Symbol] = {s.symbol_id: s for s in snapshot.symbols}
        self._symbols_by_qualified: dict[str, Symbol] = {s.qualified_name: s for s in snapshot.symbols}
        self._symbols_by_file_name: dict[tuple[str, str], Symbol] = {(s.qualified_name.split(":", 1)[0], s.name): s for s in snapshot.symbols}

    def parse_all(self) -> None:
        """Parse all Python files and build cross-file resolution tables."""
        for path, content in self.source_files_map.items():
            if path.endswith(".py"):
                try:
                    tree = ast.parse(content, filename=path)
                    self._parsed_trees[path] = tree
                except SyntaxError:
                    continue

        self._build_import_tables()

    def _build_import_tables(self) -> None:
        """Map imports in each file to their target file and target symbol."""
        file_paths = set(self.source_files_map.keys())

        for path, tree in self._parsed_trees.items():
            table: dict[str, tuple[str, str]] = {}
            current_dir = Path(path).parent

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        target_name = alias.asname or alias.name
                        # Check if module matches a file directly (e.g. 'import app' -> 'app.py')
                        candidates = [
                            f"{alias.name}.py",
                            f"{alias.name}/__init__.py",
                            (current_dir / f"{alias.name}.py").as_posix(),
                        ]
                        for c in candidates:
                            normalized = Path(c).as_posix().lstrip("./")
                            if normalized in file_paths:
                                table[target_name] = (normalized, alias.name)
                                break

                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    # Resolve relative or direct module name
                    candidates = [
                        f"{mod.replace('.', '/')}.py",
                        f"{mod.replace('.', '/')}/__init__.py",
                        (current_dir / f"{mod.replace('.', '/')}.py").as_posix(),
                    ]
                    resolved_file = None
                    for c in candidates:
                        normalized = Path(c).as_posix().lstrip("./")
                        if normalized in file_paths:
                            resolved_file = normalized
                            break

                    if resolved_file:
                        for alias in node.names:
                            local_name = alias.asname or alias.name
                            target_symbol_name = alias.name
                            table[local_name] = (resolved_file, target_symbol_name)

            self._import_tables[path] = table

    def resolve_call(self, caller_file: str, func_name: str) -> Symbol | None:
        """Resolve a called function name within caller_file to its Symbol across files."""
        # 1. Local symbol in the same file
        local = self._symbols_by_file_name.get((caller_file, func_name))
        if local:
            return local

        # 2. Check imports table for caller_file
        import_table = self._import_tables.get(caller_file, {})
        if func_name in import_table:
            target_file, target_sym_name = import_table[func_name]
            target_sym = self._symbols_by_file_name.get((target_file, target_sym_name))
            if target_sym:
                return target_sym

        # 3. Check dotted access: e.g. 'app.get_user'
        if "." in func_name:
            prefix, attr = func_name.split(".", 1)
            if prefix in import_table:
                target_file, _ = import_table[prefix]
                target_sym = self._symbols_by_file_name.get((target_file, attr))
                if target_sym:
                    return target_sym

        return None

    def discover_cross_file_relationships(
        self,
        evidence_list: list[Evidence],
    ) -> list[Relationship]:
        """Discover calls, instantiations, and dependencies across files with full evidence."""
        new_relationships: list[Relationship] = []
        seen: set[str] = {r.relationship_id for r in self.snapshot.relationships}

        for path, tree in self._parsed_trees.items():
            content = self.source_files_map.get(path, "")
            lines = content.splitlines(keepends=True)

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    caller_symbol = self._symbols_by_file_name.get((path, node.name))
                    if not caller_symbol:
                        continue

                    # Search calls inside this function
                    for child in ast.walk(node):
                        if isinstance(child, ast.Call):
                            call_name = None
                            if isinstance(child.func, ast.Name):
                                call_name = child.func.id
                            elif isinstance(child.func, ast.Attribute) and isinstance(child.func.value, ast.Name):
                                call_name = f"{child.func.value.id}.{child.func.attr}"

                            if call_name:
                                callee_symbol = self.resolve_call(path, call_name)
                                if callee_symbol and callee_symbol.symbol_id != caller_symbol.symbol_id:
                                    rel_type = "instantiates" if callee_symbol.kind == "class" else "calls"
                                    rel_id = stable_id("rel", caller_symbol.symbol_id, callee_symbol.symbol_id, rel_type, str(child.lineno))
                                    if rel_id not in seen:
                                        seen.add(rel_id)
                                        # Record evidence for call
                                        ev_id = stable_id("evidence", self.repo_id, self.rev_id, path, str(child.lineno), "cross_file_call")
                                        call_line = lines[child.lineno - 1].strip() if child.lineno <= len(lines) else call_name
                                        evidence_list.append(Evidence(
                                            evidence_id=ev_id,
                                            repository_id=self.repo_id,
                                            pkm_revision_id=self.rev_id,
                                            source_path=path,
                                            line_start=child.lineno,
                                            line_end=getattr(child, "end_lineno", child.lineno),
                                            excerpt=call_line,
                                            evidence_type="cross_file_call",
                                            extraction_method="cross_file_ast_resolution",
                                            verification_method="resolved_symbol_target",
                                            verification_status=VerificationStatus.VERIFIED,
                                            parser_version="repoflow-semantic-1.0",
                                        ))
                                        new_relationships.append(Relationship(
                                            relationship_id=rel_id,
                                            repository_id=self.repo_id,
                                            pkm_revision_id=self.rev_id,
                                            source_id=caller_symbol.symbol_id,
                                            target_id=callee_symbol.symbol_id,
                                            relationship_type=rel_type,
                                            status="verified",
                                            claim_level=ClaimLevel.RESOLVED_STATIC,
                                            evidence_ids=[ev_id],
                                            verification_method="cross_file_ast_resolution",
                                            verification_status=VerificationStatus.VERIFIED,
                                            confidence=1.0,
                                            created_by="semantic-understanding-engine",
                                        ))

        return new_relationships

    def analyze_components(self) -> dict[str, ComponentUnderstanding]:
        """Derive structured multi-level understanding for all important components."""
        understandings: dict[str, ComponentUnderstanding] = {}

        for symbol in self.snapshot.symbols:
            if symbol.kind not in {"function", "class", "module"}:
                continue

            file_path = symbol.qualified_name.split(":", 1)[0]
            content = self.source_files_map.get(file_path, "")
            lines = content.splitlines()

            comp = self._analyze_symbol(symbol, file_path, lines)
            understandings[symbol.symbol_id] = comp

        # Connect dependents based on discovered relationships
        for rel in self.snapshot.relationships:
            if rel.source_id in understandings and rel.target_id in understandings:
                src = understandings[rel.source_id]
                tgt = understandings[rel.target_id]
                if tgt.component_id not in src.dependencies:
                    src.dependencies.append(tgt.component_id)
                if src.component_id not in tgt.dependents:
                    tgt.dependents.append(src.component_id)

        return understandings

    def _analyze_symbol(self, symbol: Symbol, file_path: str, lines: list[str]) -> ComponentUnderstanding:
        """Analyze a single symbol across understanding levels 1-5."""
        tree = self._parsed_trees.get(file_path)
        node = None
        if tree:
            for n in ast.walk(tree):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == symbol.name:
                    if getattr(n, "lineno", None) == symbol.line_start:
                        node = n
                        break

        # Level 1: Local understanding
        inputs: list[dict[str, Any]] = []
        outputs: list[dict[str, Any]] = []
        state_reads: list[str] = []
        state_writes: list[str] = []
        transformations: list[str] = []
        conditions: list[str] = []
        error_paths: list[dict[str, Any]] = []
        external_interactions: list[str] = []
        role = "domain_logic"
        docstring = ""

        if node and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            docstring = ast.get_docstring(node) or ""
            # Inputs
            for arg in node.args.args:
                anno = ast.unparse(arg.annotation) if arg.annotation else "Any"
                inputs.append({"name": arg.arg, "type": anno})

            # Return type
            ret_anno = ast.unparse(node.returns) if node.returns else "None"
            outputs.append({"type": ret_anno, "description": f"Returns {ret_anno}"})

            # Inspect function body
            for child in ast.walk(node):
                if isinstance(child, ast.Return) and child.value:
                    val_str = ast.unparse(child.value)
                    transformations.append(f"Returns constructed value: {val_str}")
                elif isinstance(child, ast.If):
                    cond_str = ast.unparse(child.test)
                    conditions.append(cond_str)
                elif isinstance(child, ast.Raise):
                    exc_name = ast.unparse(child.exc) if child.exc else "Exception"
                    error_paths.append({"type": "raises", "exception": exc_name, "line": child.lineno})
                elif isinstance(child, ast.Try):
                    handlers = [ast.unparse(h.type) if h.type else "Exception" for h in child.handlers]
                    error_paths.append({"type": "catches", "handlers": handlers, "line": child.lineno})
                elif isinstance(child, ast.Assign):
                    for target in child.targets:
                        target_str = ast.unparse(target)
                        val_str = ast.unparse(child.value)
                        transformations.append(f"{target_str} = {val_str}")

            # Determine execution role
            is_route = any(
                isinstance(dec, ast.Call) and any(verb in ast.unparse(dec) for verb in ["get", "post", "put", "delete", "route"])
                for dec in getattr(node, "decorator_list", [])
            ) or ("route" in symbol.name.lower() or "api" in file_path.lower())

            if is_route:
                role = "request_handler"
            elif "load" in symbol.name.lower() or "get" in symbol.name.lower() or "fetch" in symbol.name.lower():
                role = "data_access"
            elif "service" in symbol.name.lower() or "process" in symbol.name.lower():
                role = "domain_service"
            else:
                role = "function"

        elif node and isinstance(node, ast.ClassDef):
            role = "entity_model"
            docstring = ast.get_docstring(node) or ""
            # Inspect class attributes
            for child in node.body:
                if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                    inputs.append({"name": child.target.id, "type": ast.unparse(child.annotation) if child.annotation else "Any"})

        # Derive responsibility & problem solved
        if role == "request_handler":
            responsibility = f"Exposes and handles request flow for '{symbol.name}', receiving parameters and shaping API response."
            problem_solved = f"Provides an external access interface to retrieve and format data from {file_path}."
            mod_guidance = "Verify parameter types and ensure downstream services accept the incoming request schema."
        elif role == "entity_model":
            responsibility = f"Represents domain data structure '{symbol.name}' and encapsulates entity attributes."
            problem_solved = f"Ensures consistent type-safe representation of {symbol.name} across the application."
            mod_guidance = "Changing fields requires checking all instantiation and attribute access sites across caller modules."
        elif role == "data_access":
            responsibility = f"Encapsulates retrieval and instantiation of {symbol.name.replace('load_', '').replace('get_', '')} entities."
            problem_solved = "Decouples data construction and loading logic from presentation or API route layers."
            mod_guidance = "Maintain deterministic return guarantees; handle entity absence or lookup failure cleanly."
        else:
            responsibility = f"Performs specific computation for '{symbol.name}' within {file_path}."
            problem_solved = f"Implements core business operation for {symbol.name}."
            mod_guidance = f"Inspect existing unit tests and callers before altering {symbol.name}."

        summary = docstring or f"{symbol.kind.capitalize()} {symbol.name} in {file_path} ({role.replace('_', ' ')})."

        limitations = [
            "Runtime execution performance and dynamic input data cannot be established from static AST alone.",
            "Persistence backing (e.g. database transactions) is unverified at runtime without live telemetry."
        ]

        evidence_ids = [e.evidence_id for e in self.snapshot.evidence if e.file_id == symbol.file_id and e.line_start == symbol.line_start]

        return ComponentUnderstanding(
            component_id=symbol.symbol_id,
            name=symbol.name,
            kind=symbol.kind,
            file_path=file_path,
            line_range=(symbol.line_start, symbol.line_end),
            summary=summary,
            responsibility=responsibility,
            problem_solved=problem_solved,
            inputs=inputs,
            outputs=outputs,
            state_reads=state_reads,
            state_writes=state_writes,
            transformations=transformations[:5],
            conditions=conditions,
            error_paths=error_paths,
            external_interactions=external_interactions,
            execution_role=role,
            modification_guidance=mod_guidance,
            limitations=limitations,
            provenance=ProvenanceKind.DETERMINISTIC_DERIVED,
            evidence_ids=evidence_ids,
            confidence=1.0,
        )
