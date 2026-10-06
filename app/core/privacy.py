from __future__ import annotations

from dataclasses import dataclass


class ExternalProcessingConsentRequired(PermissionError):
    pass


@dataclass(frozen=True)
class PrivacyConsent:
    granted: bool

    def require_external_processing(self) -> None:
        if not self.granted:
            raise ExternalProcessingConsentRequired(
                "É necessário consentimento para processamento externo."
            )
