from __future__ import annotations

import re
from dataclasses import dataclass

from backend.models import PkmSnapshot


@dataclass(frozen=True)
class RetrievalItem:
    item_id: str
    kind: str
    rank: float
    text: str
    evidence_ids: list[str]


@dataclass(frozen=True)
class RetrievalResult:
    items: list[RetrievalItem]
    unresolved_questions: list[str]


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-Z0-9_/.:-]+", value.lower()) if len(token) > 1}


class EvidenceRetriever:
    def retrieve(self, snapshot: PkmSnapshot, query: str, max_items: int = 20) -> RetrievalResult:
        query_tokens = _tokens(query)
        evidence_by_id = {item.evidence_id: item for item in snapshot.evidence}
        items: list[RetrievalItem] = []
        for fact in snapshot.facts:
            text = f"{fact.fact_type} {fact.attributes} {fact.subject_id}"
            score = float(len(query_tokens & _tokens(text)))
            for evidence_id in fact.evidence_ids:
                evidence = evidence_by_id.get(evidence_id)
                if evidence:
                    score += len(query_tokens & _tokens(evidence.excerpt or "")) * 0.5
            if score:
                items.append(RetrievalItem(fact.fact_id, "fact", score, text, fact.evidence_ids))
        for symbol in snapshot.symbols:
            text = f"{symbol.kind} {symbol.qualified_name} {symbol.name}"
            score = float(len(query_tokens & _tokens(text)))
            if score:
                symbol_evidence = [e.evidence_id for e in snapshot.evidence if e.file_id == symbol.file_id and e.line_start == symbol.line_start]
                items.append(RetrievalItem(symbol.symbol_id, "symbol", score, text, symbol_evidence))
        for relationship in snapshot.relationships:
            text = f"{relationship.relationship_type} {relationship.source_id} {relationship.target_id} {relationship.status}"
            score = float(len(query_tokens & _tokens(text)))
            if score:
                items.append(RetrievalItem(relationship.relationship_id, "relationship", score, text, relationship.evidence_ids))
        for evidence in snapshot.evidence:
            text = f"{evidence.source_path} {evidence.excerpt or ''}"
            score = float(len(query_tokens & _tokens(text)))
            if score:
                items.append(RetrievalItem(evidence.evidence_id, "evidence", score, text, [evidence.evidence_id]))
        items.sort(key=lambda item: (-item.rank, item.item_id))
        unresolved = [
            f"Relationship {relationship.relationship_id} remains {relationship.status}: {relationship.unresolved_reason or 'static analysis did not establish the path.'}"
            for relationship in snapshot.relationships
            if relationship.status in {"ambiguous", "unresolved"}
        ]
        if not items:
            unresolved.append("No matching structured evidence was found for this question.")
        return RetrievalResult(items=items[:max_items], unresolved_questions=unresolved[:10])


def build_deterministic_explanation(snapshot: PkmSnapshot, query: str, result: RetrievalResult) -> dict[str, object]:
    if not result.items:
        return {"answer": "The analysed repository does not contain enough matching evidence to answer this question.", "claims": [], "assumptions": [], "unresolved_questions": result.unresolved_questions}
    evidence_by_id = {item.evidence_id: item for item in snapshot.evidence}
    claims: list[dict[str, object]] = []
    explanations: list[str] = []

    for item in result.items[:6]:
        excerpts = [evidence_by_id[eid].excerpt for eid in item.evidence_ids if eid in evidence_by_id and evidence_by_id[eid].excerpt]
        fact_item = next((f for f in snapshot.facts if f.fact_id == item.item_id), None)
        if fact_item and fact_item.fact_type == "component_understanding":
            attrs = fact_item.attributes
            name = attrs.get("name")
            role = str(attrs.get("execution_role", "")).replace("_", " ")
            resp = attrs.get("responsibility", "")
            inputs = ", ".join(f"{inp.get('name')}: {inp.get('type')}" for inp in attrs.get("inputs", [])) or "none"
            outputs = attrs.get("outputs", [{}])[0].get("type", "None") if attrs.get("outputs") else "None"
            claim_text = f"{name} acts as {role}: {resp} Accepts: {inputs}. Returns: {outputs}."
            claims.append({"text": claim_text, "classification": "verified_component_understanding", "evidence_ids": item.evidence_ids, "excerpts": excerpts[:2]})
            explanations.append(claim_text)
        elif fact_item and fact_item.fact_type == "execution_path":
            attrs = fact_item.attributes
            name = attrs.get("name")
            steps_desc = " -> ".join(str(s.get("description", "")).split(".")[0] for s in attrs.get("steps", [])[:4])
            claim_text = f"Execution path {name}: {steps_desc}."
            claims.append({"text": claim_text, "classification": "verified_execution_flow", "evidence_ids": item.evidence_ids, "excerpts": excerpts[:2]})
            explanations.append(claim_text)
        elif fact_item and fact_item.fact_type == "knowledge_gap":
            attrs = fact_item.attributes
            claim_text = f"Known limitation for {attrs.get('subject_name')}: {attrs.get('limitation_note')}."
            claims.append({"text": claim_text, "classification": "disclosed_knowledge_gap", "evidence_ids": item.evidence_ids, "excerpts": []})
        else:
            claims.append({"text": item.text, "classification": "verified_fact" if item.kind != "relationship" else "static_relationship", "evidence_ids": item.evidence_ids, "excerpts": excerpts[:2]})

    answer_text = " ".join(explanations) if explanations else f"Evidence-ranked findings for: {query}"
    return {
        "answer": answer_text,
        "claims": claims,
        "assumptions": ["Based on statically verified repository revision."],
        "unresolved_questions": result.unresolved_questions,
    }
