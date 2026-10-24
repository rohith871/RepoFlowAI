from __future__ import annotations

import ast
import hashlib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from backend.config import Settings
from backend.ids import stable_id
from backend.models import (
    AssertionStatus,
    ClaimLevel,
    Evidence,
    Fact,
    PkmRevision,
    PkmSnapshot,
    Relationship,
    Repository,
    SourceFile,
    Status,
    Symbol,
    VerificationStatus,
)
from backend.storage import PkmStore


@dataclass(frozen=True)
class AnalysisResult:
    snapshot: PkmSnapshot
    source_root: Path
    warnings: list[str]


SUPPORTED = {".py": "python", ".js": "javascript", ".jsx": "javascript", ".ts": "typescript", ".tsx": "typescript", ".json": "json", ".sql": "sql", ".md": "markdown", ".toml": "toml", ".yaml": "yaml", ".yml": "yaml"}
IGNORE_DIRS = {".git", ".venv", "venv", "node_modules", "dist", "build", "__pycache__", ".mypy_cache", ".pytest_cache"}


def _hash(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _excerpt(lines: list[str], start: int, end: int, limit: int = 2400) -> str:
    return "".join(lines[max(0, start - 1):end])[:limit]


class RepositoryAnalyzer:
    def __init__(self, settings: Settings, store: PkmStore):
        self.settings = settings
        self.store = store

    def analyse(self, root: Path, repository_id: str | None = None) -> AnalysisResult:
        root = root.resolve()
        if not root.is_dir():
            raise ValueError(f"Repository path is not a directory: {root}")
        repository_id = repository_id or stable_id("repo", str(root))
        previous = self.store.get_snapshot(repository_id)
        files: list[SourceFile] = []
        symbols: list[Symbol] = []
        facts: list[Fact] = []
        evidence: list[Evidence] = []
        relationships: list[Relationship] = []
        warnings: list[str] = []
        total_bytes = 0
        source_files: list[tuple[Path, str, bytes]] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file() or any(part in IGNORE_DIRS for part in path.relative_to(root).parts):
                continue
            data = path.read_bytes()
            total_bytes += len(data)
            if len(data) > self.settings.max_file_bytes or total_bytes > self.settings.max_total_bytes:
                warnings.append(f"Skipped oversized file: {path.relative_to(root)}")
                continue
            rel = path.relative_to(root).as_posix()
            source_files.append((path, rel, data))

        revision_id = stable_id("pkmrev", repository_id, *[f"{rel}:{_hash(data)}" for _, rel, data in source_files])
        run_id = stable_id("run", repository_id, revision_id)
        parent_id = previous.revision.pkm_revision_id if previous else None
        snapshot_dir = self.settings.storage_dir / "repositories" / repository_id / "snapshots" / revision_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        if previous and previous.revision.pkm_revision_id == revision_id:
            return AnalysisResult(snapshot=previous, source_root=snapshot_dir, warnings=["Reused unchanged immutable PKM revision."])

        repo = Repository(repository_id=repository_id, name=root.name, root_label=root.name, isolation_key=repository_id)
        for path, rel, data in source_files:
            destination = snapshot_dir / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
            language = SUPPORTED.get(path.suffix.lower(), "unsupported")
            text = data.decode("utf-8", errors="replace")
            lines = text.splitlines(keepends=True)
            file_id = stable_id("file", repository_id, rel)
            file_item = SourceFile(file_id=file_id, repository_id=repository_id, pkm_revision_id=revision_id,
                                   path=rel, content_hash=_hash(data), language=language,
                                   size_bytes=len(data), analysis_status="analysed" if language != "unsupported" else "unsupported",
                                   unsupported_reason=None if language != "unsupported" else f"No analyser for {path.suffix}",
                                   line_count=len(lines))
            files.append(file_item)
            if language == "python":
                self._analyse_python(repository_id, revision_id, file_item, text, lines, symbols, facts, evidence, relationships, warnings)
            elif language in {"javascript", "typescript"}:
                self._analyse_web(repository_id, revision_id, file_item, text, lines, symbols, facts, evidence, relationships)
            elif language == "sql":
                self._analyse_sql(repository_id, revision_id, file_item, text, lines, facts, evidence)
            else:
                if language == "unsupported":
                    warnings.append(f"Unsupported language for {rel}: {path.suffix or 'no extension'}")
                self._analyse_text(repository_id, revision_id, file_item, text, lines, facts, evidence)

        revision = PkmRevision(pkm_revision_id=revision_id, repository_id=repository_id, parent_revision_id=parent_id,
                               source_snapshot_id=stable_id("snap", repository_id, revision_id), analysis_run_id=run_id,
                               status=Status.PUBLISHED, parser_versions={"python-ast": "stdlib", "web-regex": "0.1"},
                               validation_summary={"errors": 0, "warnings": len(warnings)})
        snapshot = PkmSnapshot(revision=revision, repositories=[repo], files=files, symbols=symbols,
                               facts=facts, evidence=evidence, relationships=relationships)
        self._validate(snapshot)
        self.store.save_snapshot(snapshot)
        self.store.export_snapshot(snapshot, self.settings.storage_dir / "exports" / f"{revision_id}.json")
        return AnalysisResult(snapshot=snapshot, source_root=snapshot_dir, warnings=warnings)

    def _add_evidence(self, repo: str, rev: str, file: SourceFile, lines: list[str], start: int, end: int,
                      evidence: list[Evidence], evidence_type: str, method: str = "python_ast") -> str:
        evidence_id = stable_id("evidence", repo, rev, file.path, str(start), str(end), evidence_type)
        evidence.append(Evidence(evidence_id=evidence_id, repository_id=repo, pkm_revision_id=rev, file_id=file.file_id,
                                 source_path=file.path, line_start=start, line_end=end,
                                 excerpt=_excerpt(lines, start, end), evidence_type=evidence_type,
                                 extraction_method=method, verification_method="parser_location",
                                 verification_status=VerificationStatus.VERIFIED, parser_version="stdlib",
                                 content_hash=file.content_hash))
        return evidence_id

    def _analyse_python(self, repo: str, rev: str, file: SourceFile, text: str, lines: list[str], symbols: list[Symbol], facts: list[Fact], evidence: list[Evidence], relationships: list[Relationship], warnings: list[str]) -> None:
        try:
            tree = ast.parse(text, filename=file.path)
        except SyntaxError as exc:
            warnings.append(f"Parser failed for {file.path}: {exc.msg} at line {exc.lineno}")
            return
        symbol_by_name: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                kind = "class" if isinstance(node, ast.ClassDef) else "function"
                symbol_id = stable_id("sym", repo, file.path, kind, node.name, str(node.lineno))
                symbol_by_name[node.name] = symbol_id
                end = getattr(node, "end_lineno", node.lineno)
                evidence_id = self._add_evidence(repo, rev, file, lines, node.lineno, end, evidence, "symbol_declaration")
                signature = None if kind == "class" else ast.unparse(node.args) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else None
                symbols.append(Symbol(symbol_id=symbol_id, repository_id=repo, pkm_revision_id=rev, file_id=file.file_id, kind=kind,
                                      qualified_name=f"{file.path}:{node.name}", name=node.name, signature=signature,
                                      line_start=node.lineno, line_end=end))
                facts.append(Fact(fact_id=stable_id("fact", symbol_id, "symbol"), repository_id=repo, pkm_revision_id=rev,
                                  fact_type=kind, subject_id=symbol_id, attributes={"name": node.name},
                                  assertion_status=AssertionStatus.VERIFIED_STATIC, evidence_ids=[evidence_id],
                                  extraction_method="python_ast", extractor_version="stdlib"))
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for child in ast.walk(node):
                        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                            target = symbol_by_name.get(child.func.id)
                            if target:
                                rel_evidence = self._add_evidence(repo, rev, file, lines, child.lineno, getattr(child, "end_lineno", child.lineno), evidence, "call_expression")
                                relationships.append(Relationship(relationship_id=stable_id("rel", symbol_id, target, "calls", str(child.lineno)),
                                    repository_id=repo, pkm_revision_id=rev, source_id=symbol_id, target_id=target,
                                    relationship_type="calls", status="verified", claim_level=ClaimLevel.RESOLVED_STATIC,
                                    evidence_ids=[rel_evidence], verification_method="python_ast_name_resolution",
                                    verification_status=VerificationStatus.VERIFIED, confidence=0.95, created_by="python-ast"))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    evidence_id = self._add_evidence(repo, rev, file, lines, node.lineno, node.lineno, evidence, "import")
                    facts.append(Fact(fact_id=stable_id("fact", repo, file.path, "import", alias.name), repository_id=repo,
                                      pkm_revision_id=rev, fact_type="import", subject_id=file.file_id,
                                      attributes={"module": alias.name, "alias": alias.asname}, assertion_status=AssertionStatus.VERIFIED_STATIC,
                                      evidence_ids=[evidence_id], extraction_method="python_ast", extractor_version="stdlib"))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                evidence_id = self._add_evidence(repo, rev, file, lines, node.lineno, node.lineno, evidence, "import")
                facts.append(Fact(fact_id=stable_id("fact", repo, file.path, "from", module), repository_id=repo,
                                  pkm_revision_id=rev, fact_type="import", subject_id=file.file_id,
                                  attributes={"module": module, "names": [a.name for a in node.names]},
                                  assertion_status=AssertionStatus.VERIFIED_STATIC, evidence_ids=[evidence_id],
                                  extraction_method="python_ast", extractor_version="stdlib"))
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                line = getattr(node, "lineno", 1)
                value = getattr(node, "value", None)
                if isinstance(value, ast.Constant) and isinstance(value.value, (str, int, float, bool)):
                    evidence_id = self._add_evidence(repo, rev, file, lines, line, line, evidence, "configuration")
                    facts.append(Fact(fact_id=stable_id("fact", repo, file.path, "config", str(line)), repository_id=repo,
                                      pkm_revision_id=rev, fact_type="configuration", subject_id=file.file_id,
                                      attributes={"line": line}, assertion_status=AssertionStatus.VERIFIED_STATIC,
                                      evidence_ids=[evidence_id], extraction_method="python_ast", extractor_version="stdlib"))
        self._add_python_framework_facts(repo, rev, file, text, lines, facts, evidence)

    def _add_python_framework_facts(self, repo: str, rev: str, file: SourceFile, text: str, lines: list[str], facts: list[Fact], evidence: list[Evidence]) -> None:
        patterns = [(r"@(?:app|router)\.(get|post|put|patch|delete)\([\"']([^\"']+)", "api_route"),
                    (r"class\s+(\w+)\s*\([^)]*(?:BaseModel|Model|DeclarativeBase)[^)]*\)", "database_model")]
        for pattern, fact_type in patterns:
            for match in re.finditer(pattern, text):
                line = text.count("\n", 0, match.start()) + 1
                eid = self._add_evidence(repo, rev, file, lines, line, line, evidence, fact_type, "python_ast+framework_regex")
                attrs = {"method": match.group(1), "path": match.group(2)} if fact_type == "api_route" else {"name": match.group(1)}
                facts.append(Fact(fact_id=stable_id("fact", repo, file.path, fact_type, str(line)), repository_id=repo,
                                  pkm_revision_id=rev, fact_type=fact_type, subject_id=file.file_id, attributes=attrs,
                                  assertion_status=AssertionStatus.VERIFIED_DECLARED, evidence_ids=[eid],
                                  extraction_method="python_ast+framework_regex", extractor_version="0.1"))

    def _analyse_web(self, repo: str, rev: str, file: SourceFile, text: str, lines: list[str], symbols: list[Symbol], facts: list[Fact], evidence: list[Evidence], relationships: list[Relationship]) -> None:
        for match in re.finditer(r"(?:export\s+)?(?:default\s+)?(?:function|class)\s+(\w+)|(?:const|let)\s+(\w+)\s*=\s*(?:\([^)]*\)|[^=])\s*=>", text):
            name = match.group(1) or match.group(2)
            line = text.count("\n", 0, match.start()) + 1
            sid = stable_id("sym", repo, file.path, name, str(line))
            eid = self._add_evidence(repo, rev, file, lines, line, line, evidence, "frontend_symbol", "web_regex")
            symbols.append(Symbol(symbol_id=sid, repository_id=repo, pkm_revision_id=rev, file_id=file.file_id, kind="frontend_component" if name[:1].isupper() else "function", qualified_name=f"{file.path}:{name}", name=name, line_start=line, line_end=line))
            facts.append(Fact(fact_id=stable_id("fact", sid), repository_id=repo, pkm_revision_id=rev, fact_type="frontend_symbol", subject_id=sid, attributes={"name": name}, assertion_status=AssertionStatus.VERIFIED_STATIC, evidence_ids=[eid], extraction_method="web_regex", extractor_version="0.1"))
        for match in re.finditer(r"(?:fetch|axios\.(?:get|post|put|delete))\s*\(\s*[\"'`]([^\"'`]+)", text):
            line = text.count("\n", 0, match.start()) + 1
            eid = self._add_evidence(repo, rev, file, lines, line, line, evidence, "api_client_call", "web_regex")
            facts.append(Fact(fact_id=stable_id("fact", repo, file.path, "api_client", str(line)), repository_id=repo, pkm_revision_id=rev, fact_type="api_client_call", subject_id=file.file_id, attributes={"path": match.group(1)}, assertion_status=AssertionStatus.VERIFIED_DECLARED, evidence_ids=[eid], extraction_method="web_regex", extractor_version="0.1"))

    def _analyse_sql(self, repo: str, rev: str, file: SourceFile, text: str, lines: list[str], facts: list[Fact], evidence: list[Evidence]) -> None:
        for match in re.finditer(r"\b(CREATE\s+TABLE|ALTER\s+TABLE|SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM)\b", text, re.IGNORECASE):
            line = text.count("\n", 0, match.start()) + 1
            eid = self._add_evidence(repo, rev, file, lines, line, line, evidence, "sql_statement", "sql_regex")
            facts.append(Fact(fact_id=stable_id("fact", repo, file.path, "sql", str(line)), repository_id=repo, pkm_revision_id=rev, fact_type="query", subject_id=file.file_id, attributes={"operation": match.group(1).upper()}, assertion_status=AssertionStatus.VERIFIED_DECLARED, evidence_ids=[eid], extraction_method="sql_regex", extractor_version="0.1"))

    def _analyse_text(self, repo: str, rev: str, file: SourceFile, text: str, lines: list[str], facts: list[Fact], evidence: list[Evidence]) -> None:
        for token in ("dependencies", "entrypoint", "script", "database", "api"):
            if token in text.lower():
                line = next((i for i, line in enumerate(lines, 1) if token in line.lower()), 1)
                eid = self._add_evidence(repo, rev, file, lines, line, line, evidence, "text_reference", "text_search")
                facts.append(Fact(fact_id=stable_id("fact", repo, file.path, token), repository_id=repo, pkm_revision_id=rev, fact_type="text_reference", subject_id=file.file_id, attributes={"token": token}, assertion_status=AssertionStatus.VERIFIED_STATIC, evidence_ids=[eid], extraction_method="text_search", extractor_version="0.1"))

    def _validate(self, snapshot: PkmSnapshot) -> None:
        ids = {item.file_id for item in snapshot.files} | {item.symbol_id for item in snapshot.symbols} | {item.fact_id for item in snapshot.facts} | {item.evidence_id for item in snapshot.evidence}
        for relationship in snapshot.relationships:
            if relationship.source_id not in ids or relationship.target_id not in ids:
                raise ValueError(f"Relationship endpoint missing: {relationship.relationship_id}")
            if relationship.claim_level == ClaimLevel.RUNTIME_OBSERVED:
                raise ValueError("Static analysis cannot create runtime_observed relationships")
