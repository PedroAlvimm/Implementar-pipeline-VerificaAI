from __future__ import annotations

import html
from typing import Any
from urllib.parse import urlsplit

import httpx
import streamlit as st

if __package__:
    from frontend.client import ApiClient
else:
    from client import ApiClient

BERTIMBAU_MESSAGE = "Análise linguística: aguardando integração do BERTimbau."

_STATUS = {
    "PENDING": ("Na fila", "gray"),
    "COLLECTING": ("Coletando conteúdo", "blue"),
    "EXTRACTING_CLAIMS": ("Extraindo afirmações", "blue"),
    "SEARCHING": ("Buscando fontes", "blue"),
    "CHECKING": ("Verificando evidências", "blue"),
    "COMPLETED": ("Concluída", "green"),
    "COMPLETED_WITH_LIMITATIONS": ("Concluída com limitações", "orange"),
    "FAILED": ("Falha técnica", "red"),
}

_VERDICTS = {
    "SUPPORTED": ("Sustentada", "green"),
    "REFUTED": ("Refutada", "red"),
    "NEI": ("Evidência insuficiente", "gray"),
    "CONFLICTING": ("Evidências conflitantes", "orange"),
}


def status_presentation(status: str) -> tuple[str, str]:
    return _STATUS.get(status, ("Estado desconhecido", "gray"))


def verdict_presentation(verdict: str) -> tuple[str, str]:
    return _VERDICTS.get(verdict, ("Resultado desconhecido", "gray"))


def consent_required(provider_mode: str, granted: bool) -> bool:
    return provider_mode == "real" and not granted


def _safe_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else None


def present_report(report: dict[str, Any]) -> dict[str, Any]:
    claims = []
    for claim in report.get("claims", []):
        verdict_label, verdict_color = verdict_presentation(str(claim.get("verdict", "")))
        evidence = []
        for item in claim.get("evidence", []):
            url = _safe_url(item.get("url"))
            if url:
                evidence.append(
                    {
                        "title": html.escape(str(item.get("title", "Fonte"))),
                        "url": url,
                        "excerpt": html.escape(str(item.get("excerpt", ""))),
                    }
                )
        claims.append(
            {
                "claim_id": str(claim.get("claim_id", "")),
                "text": html.escape(str(claim.get("text", ""))),
                "verdict_label": verdict_label,
                "verdict_color": verdict_color,
                "reason": html.escape(str(claim.get("reason", ""))),
                "evidence": evidence,
                "limitations": [html.escape(str(item)) for item in claim.get("limitations", [])],
            }
        )
    return {
        "status": report.get("status"),
        "risk_message": html.escape(str(report.get("risk_message", BERTIMBAU_MESSAGE))),
        "claims": claims,
        "limitations": [html.escape(str(item)) for item in report.get("limitations", [])],
    }


def run() -> None:
    st.set_page_config(page_title="VerificaAI", page_icon="🔎")
    st.title("VerificaAI")
    st.caption("Apoio auditável à verificação de informações")
    client = ApiClient()
    input_type = st.radio("Tipo de entrada", ["text", "url"], horizontal=True)
    content = st.text_area("Texto ou URL", height=180)
    consent = st.checkbox("Autorizo o processamento externo quando configurado")
    if st.button("Analisar", type="primary", disabled=not content.strip()):
        try:
            accepted = client.submit(input_type, content, consent=consent)
            st.session_state["analysis_id"] = accepted["analysis_id"]
        except httpx.HTTPError as exc:
            st.error(f"Não foi possível iniciar a análise: {exc}")

    @st.fragment(run_every="2s")
    def poll() -> None:
        analysis_id = st.session_state.get("analysis_id")
        if not analysis_id:
            return
        try:
            current = client.status(analysis_id)
            label, color = status_presentation(current["status"])
            st.markdown(f":{color}[{label}]")
            if current["status"] == "FAILED":
                st.error(current.get("error_message") or "Falha técnica")
            elif current["status"] in {"COMPLETED", "COMPLETED_WITH_LIMITATIONS"}:
                rendered = present_report(client.report(analysis_id))
                st.write(rendered["risk_message"])
                for claim in rendered["claims"]:
                    st.subheader(claim["text"])
                    st.markdown(
                        f":{claim['verdict_color']}[{claim['verdict_label']}] — {claim['reason']}"
                    )
                    for evidence in claim["evidence"]:
                        st.link_button(evidence["title"], evidence["url"])
                        st.caption(evidence["excerpt"])
                for limitation in rendered["limitations"]:
                    st.warning(limitation)
        except httpx.HTTPError as exc:
            st.error(f"Falha ao consultar a análise: {exc}")

    poll()


if __name__ == "__main__":
    run()
