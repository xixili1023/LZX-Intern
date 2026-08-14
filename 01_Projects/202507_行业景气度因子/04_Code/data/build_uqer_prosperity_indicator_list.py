"""Build a compact UQER indicator list for SW industry prosperity research."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import pyarrow.parquet as pq


AS_OF_DATE = date(2026, 8, 12)
RESEARCH_START = date(2018, 7, 1)
MAX_STALENESS_DAYS = {
    "日": 60,
    "周": 90,
    "旬": 120,
    "月": 180,
    "季": 270,
}
LOCAL_MARKERS = {
    "北京", "上海", "天津", "重庆", "河北", "河南", "山东", "山西", "陕西",
    "江苏", "浙江", "安徽", "福建", "江西", "湖北", "湖南", "广东", "广西",
    "海南", "四川", "贵州", "云南", "辽宁", "吉林", "黑龙江", "内蒙古",
    "甘肃", "青海", "宁夏", "新疆", "西藏", "杭州", "南京", "广州", "深圳",
    "成都", "武汉", "沈阳", "西安", "郑州", "邯郸", "唐山", "宁波", "无锡",
    "胜芳", "莱芜", "临沂", "海西", "太原", "济南", "青岛", "合肥", "福州",
    "厦门", "南昌", "长沙", "南宁", "海口", "贵阳", "昆明", "大连", "长春",
    "哈尔滨", "兰州", "西宁", "银川", "乌鲁木齐", "秦皇岛", "香港", "澳门", "台湾",
}
GLOBAL_MARKERS = {"全球", "世界", "国际"}
FOREIGN_MARKERS = {
    "美国", "日本", "德国", "英国", "法国", "韩国", "印度", "俄罗斯", "巴西",
    "澳大利亚", "欧盟", "加拿大", "意大利", "西班牙", "荷兰", "新加坡",
}
FREQUENCY_SCORE = {"日": 12.0, "周": 9.0, "旬": 7.0, "月": 5.0, "季": 1.0}
COMPACT_FIELDS = [
    "industry_code", "industry_name", "industry_rank", "uqer_indic_id", "uqer_name", "name_en",
    "frequency", "unit", "stat_type", "region", "country", "source", "api",
    "begin_date", "end_date", "is_update", "selection_score",
]


def _date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def deduplicate_metadata(rows):
    """Return one metadata record per indicID, preferring the latest end date."""
    result = {}
    for original in rows:
        row = dict(original)
        indicator_id = str(row.get("indicID", "")).strip()
        if not indicator_id:
            continue
        current = result.get(indicator_id)
        if current is None or (_date(row.get("endDate")) or date.min) >= (
            _date(current.get("endDate")) or date.min
        ):
            row["indicID"] = indicator_id
            result[indicator_id] = row
    return result


def load_uqer_metadata(metadata_root):
    """Load and deduplicate all fixed UQER metadata snapshots."""
    rows = []
    for path in sorted(Path(metadata_root).glob("snapshot=*/metadata/*.parquet")):
        rows.extend(pq.read_table(path).to_pylist())
    return deduplicate_metadata(rows)


def load_profiles(path):
    """Load the 28 industry relevance profiles."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_approved_ids(path):
    """Read UQER IDs already present in the approval-review list."""
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return {
            str(row.get("uqer_indic_id", "")).strip()
            for row in csv.DictReader(handle)
            if str(row.get("uqer_indic_id", "")).strip()
        }


def exclude_approved_ids(rows, approved_ids):
    """Remove rows whose UQER identifier already appears in the approval review."""
    excluded = {str(value).strip() for value in approved_ids}
    return [row for row in rows if str(row.get("indicID", "")).strip() not in excluded]


def is_metadata_eligible(row):
    """Apply history, update, frequency, and currentness gates for core candidates."""
    frequency = str(row.get("frequency", "")).strip()
    if frequency not in MAX_STALENESS_DAYS:
        return False
    if str(row.get("isUpdate", "")).strip().lower() not in {"1", "true"}:
        return False
    begin_date = _date(row.get("beginDate"))
    end_date = _date(row.get("endDate"))
    if begin_date is None or begin_date > RESEARCH_START or end_date is None:
        return False
    return (AS_OF_DATE - end_date).days <= MAX_STALENESS_DAYS[frequency]


def _search_text(row):
    return " ".join(
        str(row.get(field, ""))
        for field in ("indicName", "nameEN", "region", "country")
    ).lower()


def has_disallowed_scope(row, profile):
    """Reject narrow local data and unapproved global scope."""
    text = _search_text(row)
    allowed_foreign = set(profile.get("allowed_foreign_markers", []))
    for marker in FOREIGN_MARKERS:
        if marker.lower() in text and marker not in allowed_foreign:
            return True
    if any(marker.lower() in text for marker in GLOBAL_MARKERS):
        return not bool(profile.get("global_scope_allowed"))
    region = str(row.get("region", ""))
    name = str(row.get("indicName", ""))
    allowed_local = set(profile.get("allowed_local_markers", []))
    return any(
        (marker in region or marker in name) and marker not in allowed_local
        for marker in LOCAL_MARKERS
    )


def is_company_specific(row):
    """Identify listed-company series that cannot represent a whole industry."""
    source = str(row.get("infoSource", ""))
    name = str(row.get("indicName", ""))
    return (
        "上市公司公告" in source
        or "公司公告" in source
        or "股份有限公司" in name
        or "有限责任公司" in name
    )


def indicator_family(name):
    """Collapse value, YoY, MoM, and cumulative variants of one underlying series."""
    text = str(name or "").strip()
    text = re.sub(r"^(?:开盘价|收盘价|最高价|最低价|结算价):", "价格:", text)
    text = text.replace("定基价格指数", "价格指数").replace("环比价格指数", "价格指数")
    patterns = [
        r"\((?:上年同月|上年同期|上月|上季)=100\)$",
        r":?(?:最低价|最高价)$",
        r":?(?:当月|累计|当周|当日|当旬|本期|周|旬)?(?:涨跌幅|涨跌|值|同比|环比)$",
    ]
    previous = None
    while previous != text:
        previous = text
        for pattern in patterns:
            text = re.sub(pattern, "", text).rstrip(":： ")
    return text.lower()


def _term_in_text(term, text):
    term = str(term).lower()
    if re.search(r"[a-z0-9]", term):
        return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None
    return term in text


def score_candidate(industry_code, row, profile):
    """Score semantic fit before geography, source, and frequency."""
    del industry_code
    text = _search_text(row)
    if has_disallowed_scope(row, profile) or is_company_specific(row):
        return float("-inf")
    if any(str(term).lower() in text for term in profile.get("exclude_terms", [])):
        return float("-inf")
    core_matches = {
        str(term).lower()
        for term in profile.get("core_terms", [])
        if _term_in_text(term, text)
    }
    if not core_matches:
        return float("-inf")
    support_matches = {
        str(term).lower()
        for term in profile.get("support_terms", [])
        if _term_in_text(term, text)
    }
    score = 100.0 + 2.0 * (len(core_matches) - 1) + 8.0 * len(support_matches)
    if str(row.get("dataApiName", "")) in profile.get("preferred_apis", []):
        score += 20.0
    if str(row.get("region", "")) in {"全国", "中国", "中国大陆", ""}:
        score += 10.0
    score += FREQUENCY_SCORE.get(str(row.get("frequency", "")), 0.0)
    name = str(row.get("indicName", ""))
    if re.search(r"\(\d{6,10}\)", name):
        score -= 20.0
    score -= 0.4 * max(len(name) - 45, 0)
    return score


def select_industry_candidates(industry_code, rows, profile, limit=30):
    """Return the highest-scoring unique indicator IDs for one industry."""
    unique = {}
    for row in rows:
        indicator_id = str(row.get("indicID", "")).strip()
        if not indicator_id:
            continue
        score = score_candidate(industry_code, row, profile)
        if score == float("-inf"):
            continue
        candidate = dict(row)
        candidate["_score"] = score
        current = unique.get(indicator_id)
        if current is None or score > current["_score"]:
            unique[indicator_id] = candidate
    ranked = sorted(
        unique.values(),
        key=lambda row: (-row["_score"], str(row.get("indicName", "")), str(row["indicID"])),
    )
    families = {}
    for row in ranked:
        family = indicator_family(row.get("indicName", ""))
        if family not in families:
            families[family] = row
    max_per_term = int(profile.get("max_per_core_term", max(4, math.ceil(limit / 5))))
    term_counts = Counter()
    selected = []
    for row in families.values():
        text = _search_text(row)
        matched_terms = [
            str(term).lower()
            for term in profile.get("core_terms", [])
            if _term_in_text(term, text)
        ]
        primary_term = max(matched_terms, key=len, default="")
        if term_counts[primary_term] >= max_per_term:
            continue
        term_counts[primary_term] += 1
        selected.append(row)
        if len(selected) == limit:
            break
    return selected


def build_shortlists(metadata, profiles, approved_ids, limit=80):
    """Build labeled per-industry shortlists from eligible, unapproved metadata."""
    eligible = [row for row in metadata.values() if is_metadata_eligible(row)]
    eligible = exclude_approved_ids(eligible, approved_ids)
    output = []
    for industry_code, profile in profiles.items():
        selected = select_industry_candidates(industry_code, eligible, profile, limit=limit)
        for row in selected:
            candidate = dict(row)
            candidate["industry_code"] = industry_code
            candidate["industry_name"] = profile["industry_name"]
            candidate["selection_score"] = candidate.pop("_score")
            output.append(candidate)
    return output


def compact_candidate(row):
    """Map raw UQER metadata to the compact audit-list schema."""
    return {
        "industry_code": str(row.get("industry_code", "")),
        "industry_name": str(row.get("industry_name", "")),
        "industry_rank": row.get("industry_rank", ""),
        "uqer_indic_id": str(row.get("indicID", "")),
        "uqer_name": str(row.get("indicName", "")),
        "name_en": str(row.get("nameEN", "") or ""),
        "frequency": str(row.get("frequency", "") or ""),
        "unit": str(row.get("unit", "") or ""),
        "stat_type": str(row.get("statType", "") or ""),
        "region": str(row.get("region", "") or ""),
        "country": str(row.get("country", "") or ""),
        "source": str(row.get("infoSource", "") or ""),
        "api": str(row.get("dataApiName", "") or ""),
        "begin_date": str(row.get("beginDate", "") or ""),
        "end_date": str(row.get("endDate", "") or ""),
        "is_update": str(row.get("isUpdate", "") or ""),
        "selection_score": row.get("selection_score", ""),
    }


def write_csv(path, rows, fieldnames):
    """Write a UTF-8 BOM CSV that opens cleanly in Excel."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def finalize_candidates(shortlist_rows, profiles, per_industry=30):
    """Take the first reviewed rows per industry and enforce exact coverage."""
    grouped = {code: [] for code in profiles}
    for row in shortlist_rows:
        code = str(row.get("industry_code", ""))
        if code in grouped:
            grouped[code].append(dict(row))
    shortages = {
        code: len(rows)
        for code, rows in grouped.items()
        if len(rows) < per_industry
    }
    if shortages:
        details = ", ".join(f"{code}={count}" for code, count in shortages.items())
        raise ValueError(f"行业候选不足：{details}")
    final = []
    for code in profiles:
        for rank, row in enumerate(grouped[code][:per_industry], start=1):
            row["industry_rank"] = rank
            final.append(row)
    return final


def main(argv=None):
    parser = argparse.ArgumentParser(description="筛选可反映申万一级行业景气度的 UQER 指标。")
    parser.add_argument("--metadata-root", default="/private/tmp/uqer-metadata-audit")
    parser.add_argument(
        "--approved-csv",
        default=str(Path(__file__).with_name("uqer_approval_reaudit_20260811.csv")),
    )
    parser.add_argument(
        "--profiles",
        default=str(Path(__file__).with_name("uqer_prosperity_industry_profiles.json")),
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).with_name("uqer_prosperity_shortlist_20260811.csv")),
    )
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument("--final", action="store_true")
    args = parser.parse_args(argv)

    metadata = load_uqer_metadata(args.metadata_root)
    profiles = load_profiles(args.profiles)
    approved_ids = load_approved_ids(args.approved_csv)
    rows = [
        compact_candidate(row)
        for row in build_shortlists(metadata, profiles, approved_ids, limit=args.limit)
    ]
    if args.final:
        rows = finalize_candidates(rows, profiles, per_industry=30)
    write_csv(args.output, rows, COMPACT_FIELDS)
    counts = Counter(row["industry_code"] for row in rows)
    print(
        json.dumps(
            {
                "industries": len(counts),
                "rows": len(rows),
                "per_industry_min": min(counts.values(), default=0),
                "per_industry_max": max(counts.values(), default=0),
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
