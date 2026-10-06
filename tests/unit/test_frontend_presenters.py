from __future__ import annotations

from frontend.app import (
    BERTIMBAU_MESSAGE,
    consent_required,
    present_report,
    status_presentation,
    verdict_presentation,
)


def test_portuguese_status_and_verdict_labels_include_color() -> None:
    assert status_presentation("CHECKING") == ("Verificando evidências", "blue")
    assert verdict_presentation("REFUTED") == ("Refutada", "red")
    assert verdict_presentation("NEI") == ("Evidência insuficiente", "gray")


def test_real_mode_requires_consent_prompt() -> None:
    assert consent_required("real", granted=False)
    assert not consent_required("real", granted=True)
    assert not consent_required("fake", granted=False)


def test_report_presenter_keeps_clickable_evidence_and_limitations() -> None:
    presented = present_report(
        {
            "status": "COMPLETED_WITH_LIMITATIONS",
            "risk_message": BERTIMBAU_MESSAGE,
            "limitations": ["claim_02: search indisponível"],
            "claims": [
                {
                    "claim_id": "claim_01",
                    "text": "O contrato registra 8 unidades.",
                    "verdict": "REFUTED",
                    "reason": "O número diverge.",
                    "limitations": [],
                    "evidence": [
                        {
                            "title": "Contrato oficial",
                            "url": "https://gov.example/contrato",
                            "excerpt": "O contrato registra 8 unidades.",
                        }
                    ],
                }
            ],
        }
    )

    assert presented["claims"][0]["verdict_label"] == "Refutada"
    assert presented["claims"][0]["evidence"][0]["url"].startswith("https://")
    assert presented["limitations"] == ["claim_02: search indisponível"]
    assert presented["risk_message"] == BERTIMBAU_MESSAGE


def test_technical_error_is_not_presented_as_nei() -> None:
    technical = status_presentation("FAILED")
    nei = verdict_presentation("NEI")
    assert technical[0] == "Falha técnica"
    assert technical != nei
    assert BERTIMBAU_MESSAGE == "Análise linguística: aguardando integração do BERTimbau."

