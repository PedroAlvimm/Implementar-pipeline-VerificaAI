from __future__ import annotations

from datetime import datetime
from typing import Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.claims.schemas import ClaimId, ShortText
from app.core.enums import Verdict
from app.fact_checking.quotation import map_quote_to_original


class JudgmentValidationError(ValueError):
    pass


class JudgmentEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    text: str
    source_title: str
    source_url: str
    source_domain: str
    published_at: datetime | None
    retrieved_at: datetime
    independence_group: str
    is_primary_source: bool
    temporal_match: bool | None


class EvidenceDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: ClaimId
    evidence_id: ClaimId
    label: Verdict
    reason: str = Field(max_length=2048)
    quoted_excerpt: str = Field(max_length=4096)
    limitations: list[ShortText] = Field(max_length=16)

    @field_validator("label")
    @classmethod
    def pair_label_only(cls, value: Verdict) -> Verdict:
        if value is Verdict.CONFLICTING:
            raise ValueError("CONFLICTING é resultado agregado, não rótulo por evidência")
        return value


def validate_decision(
    decision: EvidenceDecision, claim_id: str, evidence: JudgmentEvidence
) -> EvidenceDecision:
    if decision.claim_id != claim_id:
        raise JudgmentValidationError("A decisão referencia uma claim desconhecida")
    if decision.evidence_id != evidence.evidence_id:
        raise JudgmentValidationError("A decisão referencia uma evidência desconhecida")
    if decision.label is not Verdict.NEI:
        try:
            mapped = map_quote_to_original(decision.quoted_excerpt, evidence.text)
        except ValueError as exc:
            raise JudgmentValidationError(str(exc)) from exc
        return decision.model_copy(update={"quoted_excerpt": mapped.text})
    if decision.quoted_excerpt:
        try:
            map_quote_to_original(decision.quoted_excerpt, evidence.text)
        except ValueError as exc:
            raise JudgmentValidationError(str(exc)) from exc
    return decision


SchemaT = TypeVar("SchemaT", bound=BaseModel)


class JsonProvider(Protocol):
    def generate_json(self, schema: type[SchemaT], messages: list[dict[str, str]]) -> SchemaT: ...


_SYSTEM_PROMPT = """Você é um componente de inferência baseado em evidências.
Use exclusivamente as evidências fornecidas.
Não utilize memória, conhecimento externo ou suposições.
Não invente informações.
Não altere números, datas ou nomes.
Se a evidência não for suficiente, responda NEI.
Se fontes relevantes entrarem em conflito, sinalize o conflito.
Cite exatamente quais evidências sustentam sua decisão."""


class LlmEvidenceJudge:
    def __init__(self, provider: JsonProvider) -> None:
        self._provider = provider

    def judge(self, claim_id: str, claim_text: str, evidence: JudgmentEvidence) -> EvidenceDecision:
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"<claim id='{claim_id}'>{claim_text}</claim>\n"
                    f"<evidencia id='{evidence.evidence_id}'>"
                    f"{evidence.text}</evidencia>"
                ),
            },
        ]
        last_error: JudgmentValidationError | None = None
        for attempt in range(2):
            decision = self._provider.generate_json(EvidenceDecision, messages)
            try:
                return validate_decision(decision, claim_id, evidence)
            except JudgmentValidationError as exc:
                last_error = exc
                if attempt == 0:
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "A citação não existe na evidência. Corrija sem criar fatos."
                            ),
                        }
                    )
        raise JudgmentValidationError("Decisão inválida após uma correção") from last_error
