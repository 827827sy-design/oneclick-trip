from __future__ import annotations


class DestinationResearchPolicy:
    """Code-owned mapping of destinations to verified official web domains."""

    _OFFICIAL_DOMAINS: dict[str, tuple[str, ...]] = {
        "峨眉山": ("ems517.com", "emeishan.gov.cn"),
    }

    def official_domains(self, destination: str | None, query: str = "") -> list[str]:
        text = f"{destination or ''} {query}"
        domains: list[str] = []
        for keyword, configured in self._OFFICIAL_DOMAINS.items():
            if keyword not in text:
                continue
            for domain in configured:
                if domain not in domains:
                    domains.append(domain)
        return domains
