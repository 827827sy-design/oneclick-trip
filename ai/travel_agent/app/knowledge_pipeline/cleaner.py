from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd

from app.knowledge_pipeline.models import (
    CleanedKnowledgeRecord,
    KnowledgeQualityReport,
    RawKnowledgeRecord,
    RejectedKnowledgeRecord,
)


SUPPORTED_BASES = {"poi", "food", "hotel", "transport", "ticket", "guide"}
CATEGORY_ALIASES = {
    "景点": ("景点", "poi"),
    "景区": ("景点", "poi"),
    "poi": ("景点", "poi"),
    "美食": ("美食", "food"),
    "餐饮": ("美食", "food"),
    "food": ("美食", "food"),
    "酒店": ("酒店", "hotel"),
    "住宿": ("酒店", "hotel"),
    "hotel": ("酒店", "hotel"),
    "交通": ("交通", "transport"),
    "transport": ("交通", "transport"),
    "门票": ("门票", "ticket"),
    "ticket": ("门票", "ticket"),
    "攻略": ("攻略", "guide"),
    "guide": ("攻略", "guide"),
}
TRACKING_QUERY_PREFIXES = ("utm_", "spm", "from", "source", "ref")
DESTINATION_ALIASES = {
    "北京": ("北京",),
    "上海": ("上海",),
    "天津": ("天津",),
    "重庆": ("重庆", "重慶"),
    "成都": ("成都", "都江堰", "青城山"),
    "杭州": ("杭州", "西湖"),
    "西安": ("西安", "長安", "长安"),
    "南京": ("南京",),
    "苏州": ("苏州", "蘇州"),
    "广州": ("广州", "廣州"),
    "深圳": ("深圳",),
    "厦门": ("厦门", "廈門", "鼓浪屿", "鼓浪嶼"),
    "武汉": ("武汉", "武漢"),
    "长沙": ("长沙", "長沙"),
    "青岛": ("青岛", "青島"),
    "大连": ("大连", "大連"),
    "哈尔滨": ("哈尔滨", "哈爾濱"),
    "昆明": ("昆明",),
    "大理": ("大理",),
    "丽江": ("丽江", "麗江"),
    "三亚": ("三亚", "三亞"),
    "桂林": ("桂林",),
    "张家界": ("张家界", "張家界"),
    "拉萨": ("拉萨", "拉薩"),
    "新疆": (
        "新疆", "北疆", "南疆", "乌鲁木齐", "烏魯木齊", "喀什",
        "伊犁", "阿勒泰", "喀纳斯", "喀納斯", "禾木", "赛里木湖", "賽里木湖",
    ),
    "内蒙古": ("内蒙古", "內蒙古", "呼和浩特", "呼倫貝爾", "呼伦贝尔"),
}


class PandasKnowledgeCleaner:
    """Batch cleaner where normalization, scoring and dedupe are DataFrame operations."""

    def clean(
        self,
        records: list[RawKnowledgeRecord],
    ) -> tuple[list[CleanedKnowledgeRecord], list[RejectedKnowledgeRecord], KnowledgeQualityReport]:
        frame = pd.DataFrame([record.model_dump(mode="python") for record in records])
        frame.insert(0, "row_index", range(len(frame)))
        frame["title"] = frame["title"].fillna("").map(_clean_text)
        frame["content"] = frame["content"].fillna("").map(_clean_content)
        frame["city"] = frame["city"].fillna("").map(_normalize_city)
        frame["category"] = frame["category"].fillna("").map(_clean_text)
        aliases = frame["category"].str.casefold().map(CATEGORY_ALIASES)
        frame["normalized_category"] = aliases.map(
            lambda value: value[0] if isinstance(value, tuple) else ""
        )
        inferred_base = aliases.map(
            lambda value: value[1] if isinstance(value, tuple) else ""
        )
        frame["knowledge_base"] = frame["knowledge_base"].fillna("").map(
            lambda value: _clean_text(str(value)).casefold()
        )
        frame["knowledge_base"] = frame["knowledge_base"].where(
            frame["knowledge_base"].ne(""), inferred_base
        )
        frame["source"] = frame["source"].fillna("manual").map(_clean_text)
        frame["source_tier"] = frame["source_tier"].fillna("unknown").map(
            lambda value: _normalize_source_tier(str(value))
        )
        frame["content_source"] = frame["content_source"].fillna("manual").map(
            lambda value: _normalize_content_source(str(value))
        )
        frame["source_url"] = frame["source_url"].map(_canonical_url)
        frame["tags"] = frame["tags"].map(_normalize_tags)
        frame["updated_at"] = pd.to_datetime(frame["updated_at"], utc=True, errors="coerce")
        frame["updated_at"] = frame["updated_at"].fillna(pd.Timestamp.now(tz="UTC"))
        city_audit = frame.apply(_audit_city_consistency, axis=1)
        frame["city_consistency"] = city_audit.map(lambda value: value[0])
        frame["detected_cities"] = city_audit.map(lambda value: value[1])
        frame["reasons"] = frame.apply(_rejection_reasons, axis=1)

        rejected_frame = frame[frame["reasons"].map(bool)].copy()
        valid = frame[~frame["reasons"].map(bool)].copy()
        if not valid.empty:
            valid["quality_score"] = valid.apply(_quality_score, axis=1)
            valid["fingerprint"] = valid.apply(_fingerprint, axis=1)
            valid["dedupe_key"] = valid.apply(
                lambda row: f"url:{row['source_url']}" if row["source_url"] else f"text:{row['fingerprint']}",
                axis=1,
            )
            valid = valid.sort_values(
                ["quality_score", "updated_at"], ascending=[False, False]
            )
            duplicate_mask = valid.duplicated("dedupe_key", keep="first")
            duplicate_rows = valid[duplicate_mask]
            valid = valid[~duplicate_mask].sort_values("row_index")
        else:
            duplicate_rows = valid

        rejected = [
            RejectedKnowledgeRecord(
                row_index=int(row.row_index),
                title=str(row.title),
                reasons=list(row.reasons),
                city=str(row.city),
                detected_cities=list(row.detected_cities),
            )
            for row in rejected_frame.itertuples()
        ]
        rejected.extend(
            RejectedKnowledgeRecord(
                row_index=int(row.row_index),
                title=str(row.title),
                reasons=["DUPLICATE_RECORD"],
                city=str(row.city),
                detected_cities=list(row.detected_cities),
            )
            for row in duplicate_rows.itertuples()
        )
        cleaned = [_to_cleaned_record(row) for _, row in valid.iterrows()]
        report = _quality_report(records, cleaned, rejected, len(duplicate_rows))
        return cleaned, sorted(rejected, key=lambda item: item.row_index), report


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" \t\r\n，,。；;")


def _clean_content(value: str) -> str:
    text = re.sub(r"[\u200b-\u200f\ufeff]", "", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def _normalize_city(value: str) -> str:
    city = _clean_text(value)
    return city[:-1] if len(city) > 2 and city.endswith("市") else city


def _audit_city_consistency(row: pd.Series) -> tuple[str, list[str]]:
    declared = str(row["city"] or "")
    title = str(row["title"] or "")
    content = str(row["content"] or "")
    scores: dict[str, int] = {}
    title_scores: dict[str, int] = {}
    for city, aliases in DESTINATION_ALIASES.items():
        title_count = sum(title.count(alias) for alias in aliases)
        body_count = min(sum(content.count(alias) for alias in aliases), 12)
        if title_count or body_count:
            title_scores[city] = title_count
            scores[city] = title_count * 4 + body_count

    detected = [
        city for city, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    ]
    if not declared:
        return "UNKNOWN", detected

    declared_city = next(
        (
            city
            for city, aliases in DESTINATION_ALIASES.items()
            if declared == city or any(alias in declared or declared in alias for alias in aliases)
        ),
        declared,
    )
    declared_score = scores.get(declared_city, 0)
    other_scores = {
        city: score for city, score in scores.items() if city != declared_city
    }
    if not other_scores:
        return ("MATCH" if declared_score else "UNKNOWN"), detected

    dominant_other, dominant_score = max(other_scores.items(), key=lambda item: item[1])
    title_conflict = (
        title_scores.get(dominant_other, 0) > 0
        and title_scores.get(declared_city, 0) == 0
        and dominant_score >= 4
    )
    overwhelming_conflict = dominant_score >= max(6, declared_score * 3)
    if title_conflict or overwhelming_conflict:
        return "MISMATCH", detected
    return ("MATCH" if declared_score else "UNKNOWN"), detected


def _normalize_source_tier(value: str) -> str:
    tier = value.strip().casefold()
    return tier if tier in {"official", "trusted", "commercial", "community", "unknown"} else "unknown"


def _normalize_content_source(value: str) -> str:
    source = value.strip().casefold()
    return source if source in {"full_page", "search_summary", "manual"} else "manual"


def _canonical_url(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parts = urlsplit(raw)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            return None
        query = [
            (key, val)
            for key, val in parse_qsl(parts.query, keep_blank_values=True)
            if not key.casefold().startswith(TRACKING_QUERY_PREFIXES)
        ]
        path = re.sub(r"/{2,}", "/", parts.path).rstrip("/") or "/"
        return urlunsplit((parts.scheme.casefold(), parts.netloc.casefold(), path, urlencode(query), ""))
    except ValueError:
        return None


def _normalize_tags(value: object) -> list[str]:
    raw = value if isinstance(value, list) else re.split(r"[,，、|]", str(value or ""))
    result: list[str] = []
    for item in raw:
        tag = _clean_text(str(item))
        if tag and tag not in result:
            result.append(tag)
    return result[:12]


def _rejection_reasons(row: pd.Series) -> list[str]:
    reasons = []
    if not row["title"]:
        reasons.append("TITLE_MISSING")
    if len(row["content"]) < 12:
        reasons.append("CONTENT_TOO_SHORT")
    if not row["city"]:
        reasons.append("CITY_MISSING")
    if not row["normalized_category"]:
        reasons.append("CATEGORY_UNSUPPORTED")
    if row["knowledge_base"] not in SUPPORTED_BASES:
        reasons.append("KNOWLEDGE_BASE_UNSUPPORTED")
    if row["city_consistency"] == "MISMATCH":
        reasons.append("CITY_CONTENT_MISMATCH")
    return reasons


def _quality_score(row: pd.Series) -> float:
    score = 0.45
    score += min(len(row["content"]) / 400, 1) * 0.2
    score += 0.12 if row["source_url"] else 0
    score += {"official": 0.18, "trusted": 0.14, "commercial": 0.08, "community": 0.05}.get(
        row["source_tier"], 0
    )
    score += 0.05 if row["tags"] else 0
    score += 0.03 if row["content_source"] == "full_page" else 0
    score -= 0.08 if row["content_source"] == "search_summary" else 0
    score -= 0.08 if row["city_consistency"] == "UNKNOWN" else 0
    return round(min(score, 1.0), 3)


def _fingerprint(row: pd.Series) -> str:
    value = "|".join(
        re.sub(r"[^\w\u4e00-\u9fff]+", "", str(item).casefold())
        for item in (row["city"], row["normalized_category"], row["title"], row["content"][:180])
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _to_cleaned_record(row: pd.Series) -> CleanedKnowledgeRecord:
    updated_at = row["updated_at"].to_pydatetime()
    record_id = hashlib.sha256(
        f"{row['knowledge_base']}|{row['city']}|{row['fingerprint']}".encode("utf-8")
    ).hexdigest()[:24]
    return CleanedKnowledgeRecord(
        record_id=record_id,
        title=row["title"],
        content=row["content"],
        city=row["city"],
        category=row["normalized_category"],
        knowledge_base=row["knowledge_base"],
        source=row["source"] or "manual",
        source_url=row["source_url"],
        source_tier=row["source_tier"],
        content_source=row["content_source"],
        updated_at=updated_at.astimezone(UTC),
        tags=row["tags"],
        price_text=_optional_text(row.get("price_text")),
        opening_hours=_optional_text(row.get("opening_hours")),
        quality_score=float(row["quality_score"]),
        fingerprint=row["fingerprint"],
        city_consistency=row["city_consistency"],
        detected_cities=row["detected_cities"],
    )


def _optional_text(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = _clean_text(str(value))
    return text or None


def _quality_report(
    raw: list[RawKnowledgeRecord],
    cleaned: list[CleanedKnowledgeRecord],
    rejected: list[RejectedKnowledgeRecord],
    duplicate_count: int,
) -> KnowledgeQualityReport:
    reason_counts = Counter(reason for item in rejected for reason in item.reasons)
    input_count = len(raw)
    complete = sum(
        bool(item.title and item.content and item.city and item.category and item.source)
        for item in raw
    )
    official = sum(item.source_tier == "official" for item in cleaned)
    average = sum(item.quality_score for item in cleaned) / len(cleaned) if cleaned else 0
    base_counts = Counter(item.knowledge_base for item in cleaned)
    return KnowledgeQualityReport(
        input_count=input_count,
        cleaned_count=len(cleaned),
        rejected_count=len(rejected),
        duplicate_count=duplicate_count,
        completeness_rate=round(complete / input_count, 3) if input_count else 0,
        official_source_rate=round(official / len(cleaned), 3) if cleaned else 0,
        average_quality_score=round(average, 3),
        knowledge_base_counts=dict(base_counts),
        rejection_reason_counts=dict(reason_counts),
    )
