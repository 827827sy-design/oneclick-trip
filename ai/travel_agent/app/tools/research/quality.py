from __future__ import annotations

import re
from enum import StrEnum
from urllib.parse import urlsplit

from pydantic import Field

from app.domain.models import DomainModel, ToolResult
from app.tools.research.agent_reach import ResearchItem


class SourceTier(StrEnum):
    OFFICIAL = "official"
    TRUSTED = "trusted"
    COMMERCIAL = "commercial"
    COMMUNITY = "community"
    UNKNOWN = "unknown"


class RankedResearchItem(ResearchItem):
    source_tier: SourceTier
    authority_score: float = Field(ge=0, le=1)


class EvidenceClaim(DomainModel):
    metric: str
    lower: float
    upper: float
    unit: str
    source_count: int = Field(ge=1)
    source_urls: list[str]
    corroborated: bool


class ResearchQualityPipeline:
    def __init__(
        self,
        *,
        official_domains: list[str] | None = None,
        trusted_domains: list[str] | None = None,
    ) -> None:
        self._official_domains = _normalize_domains(official_domains or [])
        self._trusted_domains = _normalize_domains(trusted_domains or [])

    def enrich(self, result: ToolResult, *, max_results: int | None = None) -> ToolResult:
        if not result.success:
            return result
        items = [ResearchItem.model_validate(item) for item in result.data.get("items", [])]
        ranked = sorted(
            (self._rank(item) for item in items),
            key=lambda item: (item.authority_score, item.score or 0.0),
            reverse=True,
        )
        if max_results is not None:
            ranked = _diversify_items(ranked, max_results=max_results)
        claims = _extract_evidence_claims(ranked)
        hosts = {_host(item.url) for item in ranked}
        official_count = sum(item.source_tier is SourceTier.OFFICIAL for item in ranked)
        data = dict(result.data)
        data.update(
            {
                "items": [item.model_dump(mode="json") for item in ranked],
                "count": len(ranked),
                "evidence_claims": [claim.model_dump(mode="json") for claim in claims],
                "quality": {
                    "official_source_count": official_count,
                    "source_domain_count": len(hosts),
                    "corroborated_claim_count": sum(
                        claim.corroborated for claim in claims
                    ),
                    "official_source_missing": official_count == 0,
                },
            }
        )
        confidence = _quality_confidence(ranked, claims)
        return result.model_copy(update={"data": data, "confidence": confidence})

    def _rank(self, item: ResearchItem) -> RankedResearchItem:
        host = _host(item.url)
        tier, authority = _source_rating(
            host,
            official_domains=self._official_domains,
            trusted_domains=self._trusted_domains,
        )
        return RankedResearchItem(
            **item.model_dump(),
            source_tier=tier,
            authority_score=authority,
        )


_COMMERCIAL_DOMAINS = {
    "ctrip.com",
    "qunar.com",
    "fliggy.com",
    "mafengwo.cn",
}
_COMMUNITY_DOMAINS = {
    "xiaohongshu.com",
    "bilibili.com",
    "douyin.com",
    "toutiao.com",
    "zhihu.com",
}


def _source_rating(
    host: str,
    *,
    official_domains: set[str],
    trusted_domains: set[str],
) -> tuple[SourceTier, float]:
    if host.endswith(".gov.cn") or _matches_any(host, official_domains):
        return SourceTier.OFFICIAL, 0.98
    if _matches_any(host, trusted_domains):
        return SourceTier.TRUSTED, 0.82
    if _matches_any(host, _COMMERCIAL_DOMAINS):
        return SourceTier.COMMERCIAL, 0.64
    if _matches_any(host, _COMMUNITY_DOMAINS):
        return SourceTier.COMMUNITY, 0.46
    return SourceTier.UNKNOWN, 0.52


def _normalize_domains(domains: list[str]) -> set[str]:
    return {
        domain.lower().strip().removeprefix("www.").strip(".")
        for domain in domains
        if domain.strip()
    }


def _matches_any(host: str, domains: set[str]) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def _host(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.")


_CLAIM_PATTERNS = (
    (
        "total_distance",
        "km",
        re.compile(
            r"(?:全程|总里程)[^。；\n]{0,24}?(\d+(?:\.\d+)?)"
            r"(?:\s*[-–—~至到]\s*(\d+(?:\.\d+)?))?\s*(?:公里|km)",
            re.IGNORECASE,
        ),
    ),
    (
        "duration",
        "day",
        re.compile(
            r"(?:需|需要|耗时|建议|通常)[^。；\n]{0,20}?(\d+(?:\.\d+)?)"
            r"(?:\s*[-–—~至到]\s*(\d+(?:\.\d+)?))?\s*(?:天|日)",
        ),
    ),
    (
        "ascent",
        "m",
        re.compile(
            r"(?:累计爬升|总爬升|爬升(?:约|超过|超|近))\s*"
            r"(\d+(?:\.\d+)?)\s*(?:余)?(?:米|m)",
            re.IGNORECASE,
        ),
    ),
)


def _extract_evidence_claims(items: list[RankedResearchItem]) -> list[EvidenceClaim]:
    observations: list[tuple[str, float, float, str, str]] = []
    for item in items:
        for metric, unit, pattern in _CLAIM_PATTERNS:
            for match in pattern.finditer(item.summary):
                lower = float(match.group(1))
                upper_value = match.group(2) if (match.lastindex or 0) >= 2 else None
                upper = float(upper_value or match.group(1))
                observations.append((metric, min(lower, upper), max(lower, upper), unit, item.url))

    clusters: list[dict[str, object]] = []
    for metric, lower, upper, unit, url in observations:
        cluster = next(
            (
                item
                for item in clusters
                if item["metric"] == metric
                and _ranges_are_close(
                    lower,
                    upper,
                    float(item["lower"]),
                    float(item["upper"]),
                )
            ),
            None,
        )
        if cluster is None:
            clusters.append(
                {
                    "metric": metric,
                    "lower": lower,
                    "upper": upper,
                    "unit": unit,
                    "urls": {url},
                }
            )
            continue
        cluster["lower"] = min(float(cluster["lower"]), lower)
        cluster["upper"] = max(float(cluster["upper"]), upper)
        urls = cluster["urls"]
        assert isinstance(urls, set)
        urls.add(url)

    claims = []
    for cluster in clusters:
        urls = sorted(cluster["urls"])
        claims.append(
            EvidenceClaim(
                metric=str(cluster["metric"]),
                lower=float(cluster["lower"]),
                upper=float(cluster["upper"]),
                unit=str(cluster["unit"]),
                source_count=len({_host(url) for url in urls}),
                source_urls=urls,
                corroborated=len({_host(url) for url in urls}) >= 2,
            )
        )
    return sorted(claims, key=lambda claim: (claim.corroborated, claim.source_count), reverse=True)


def _ranges_are_close(
    left_lower: float,
    left_upper: float,
    right_lower: float,
    right_upper: float,
) -> bool:
    tolerance = max(left_upper, right_upper) * 0.1
    return left_lower <= right_upper + tolerance and right_lower <= left_upper + tolerance


def _quality_confidence(
    items: list[RankedResearchItem], claims: list[EvidenceClaim]
) -> float:
    if not items:
        return 0.0
    authority = sum(item.authority_score for item in items) / len(items)
    corroboration_bonus = min(sum(claim.corroborated for claim in claims) * 0.05, 0.15)
    return round(min(authority + corroboration_bonus, 1.0), 3)


def _diversify_items(
    items: list[RankedResearchItem],
    *,
    max_results: int,
    max_per_domain: int = 2,
) -> list[RankedResearchItem]:
    selected: list[RankedResearchItem] = []
    deferred: list[RankedResearchItem] = []
    domain_counts: dict[str, int] = {}
    for item in items:
        host = _host(item.url)
        if domain_counts.get(host, 0) >= max_per_domain:
            deferred.append(item)
            continue
        selected.append(item)
        domain_counts[host] = domain_counts.get(host, 0) + 1
        if len(selected) >= max_results:
            return selected
    for item in deferred:
        selected.append(item)
        if len(selected) >= max_results:
            break
    return selected
