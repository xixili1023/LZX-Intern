"""通过 Anemoi 内网网关补查四只多资产配置指数。

接入规则来自 ``/Users/lizhexi/Downloads/anemoi_gateway/INTERN_GUIDE.md``：
不安装 ``uqer``，不使用通联 token，通过管理员提供的 ``client.py``
导入 ``DataAPI``。网关地址与个人 key 由环境变量读取，本脚本不打印、
不保存 key。

使用实习仓库根目录已定义的虚拟环境，在项目根目录运行：

    /Users/lizhexi/Desktop/LZX-Intern/.venv/bin/python scripts/uqer_supplement.py

产物：

* ``results/UQER查询审计.csv``：逐笔记录状态、行数和错误分类；
* ``results/uqer/UQER_*.csv``：网关实际返回的原始表。

只有网关成功返回空 DataFrame 时才记为“空结果”。网关不可达、key
失效、配额用尽或上游权限不足，都不得写成“UQER 没数据”。
"""

from __future__ import annotations

import argparse
import importlib
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLIENT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "results" / "uqer"
STATUS_OUTPUT = PROJECT_ROOT / "results" / "UQER查询审计.csv"
QUERY_END_DATE = "20260805"

INDEX_NAMES = {
    "CI011800.WI": "国泰海通资产配置指数",
    "CICSF040.WI": "中信期货大类资产配置指数",
    "CI011001.WI": "国泰海通大类资产全天候增强指数",
    "GALLW.WI": "中国银河全天候指数",
}

INDEX_BEGIN_DATES = {
    "CI011800.WI": "20221231",
    "CICSF040.WI": "20150105",
    "CI011001.WI": "20090108",
    "GALLW.WI": "20210701",
}

# 先用少量关键日探测覆盖，有数据后再扩展到所有调仓日。
DEFAULT_SNAPSHOT_DATES = (
    "20231231",
    "20241231",
    "20251231",
    "20260630",
    QUERY_END_DATE,
)

INFO_FIELDS = (
    "secID,publishDate,secShortName,ticker,indexTypeCD,indexType,porgFullName,"
    "baseDate,basePoint,endDate,indexGroup,consType,consMkt,returnType,wMethodCD,"
    "updateTime,pubName,sortName"
)
DAILY_FIELDS = (
    "indexID,ticker,porgFullName,secShortName,exchangeCD,tradeDate,preCloseIndex,"
    "openIndex,lowestIndex,highestIndex,closeIndex,CHG,CHGPct"
)
CONSTITUENT_FIELDS = (
    "secID,intoDate,secShortName,ticker,consID,consShortName,consTickerSymbol,"
    "consExchangeCD,outDate,isNew"
)

WEIGHT_ENDPOINT_DECLARATION = (
    "IdxCloseWeightGet的参数说明枚举中债、上证、中证、深证、国证及"
    "通联DY系列等代码，未列入这四个Wind策略指数代码；本脚本仍做"
    "一次实际探测，但不将其外推到其他UQER接口。"
)


@dataclass(frozen=True)
class QuerySpec:
    wind_ticker: str
    endpoint: str
    purpose: str
    params: dict[str, Any]
    query_kind: str

    @property
    def uqer_ticker(self) -> str:
        return normalize_wind_ticker(self.wind_ticker)


def normalize_wind_ticker(ticker: str) -> str:
    """仅移除 Wind 代码末尾的 ``.WI``。"""

    value = str(ticker).strip()
    return value[:-3] if value.upper().endswith(".WI") else value


def classify_query_error(error: BaseException) -> str:
    """将网关/上游错误分成不会误导数据覆盖的状态。"""

    message = str(error).lower()
    if any(
        text in message
        for text in ("无法连接网关", "请求网关超时", "与网关通信失败")
    ):
        return "网关不可达"
    if any(
        text in message
        for text in ("无效的 key", "key 已吊销", "key 已过期", "unauthorized")
    ):
        return "网关认证失败"
    if any(
        text in message
        for text in ("今日额度已用尽", "traffic limit", "daily traffic")
    ):
        return "配额用尽"
    if any(
        text in message
        for text in ("接口使用权限", "need privilege", "无uqer sdk权限")
    ):
        return "上游无接口权限"
    if any(text in message for text in ("请求超时", "query timeout", "read timed out")):
        return "上游请求超时"
    return "查询失败"


def _safe_error_summary(error: BaseException) -> str:
    message = re.sub(r"anemoi_[A-Za-z0-9_-]+", "anemoi_[REDACTED]", str(error))
    return " ".join(message.split())[:300]


def _param_summary(params: dict[str, Any]) -> str:
    visible = dict(params)
    if "field" in visible:
        visible["field"] = f"{len(str(visible['field']).split(','))}个字段"
    return "; ".join(f"{key}={value}" for key, value in visible.items())


def _declared_coverage(spec: QuerySpec) -> tuple[str, str]:
    if spec.endpoint == "IdxCloseWeightGet":
        return "未列入接口枚举", WEIGHT_ENDPOINT_DECLARATION
    return "文档未限定", "须以网关实际返回判断。"


def build_query_plan(
    snapshot_dates: Iterable[str] = DEFAULT_SNAPSHOT_DATES,
) -> list[QuerySpec]:
    """构造一组节省流量、可复现的覆盖探测。"""

    plan: list[QuerySpec] = []
    for wind_ticker, name in INDEX_NAMES.items():
        ticker = normalize_wind_ticker(wind_ticker)
        plan.extend(
            [
                QuerySpec(
                    wind_ticker,
                    "IdxGet",
                    "按Wind通用代码核对UQER映射与基本信息",
                    {"ticker": ticker, "field": INFO_FIELDS, "pandas": "1"},
                    "ticker_info",
                ),
                QuerySpec(
                    wind_ticker,
                    "IdxGet",
                    "按中文名搜索映射候选（不自动替代）",
                    {"secShortName": name, "field": INFO_FIELDS, "pandas": "1"},
                    "name_candidate",
                ),
                QuerySpec(
                    wind_ticker,
                    "MktIdxdGet",
                    "日行情覆盖与Wind点位对账",
                    {
                        "ticker": ticker,
                        "beginDate": INDEX_BEGIN_DATES[wind_ticker],
                        "endDate": QUERY_END_DATE,
                        "field": DAILY_FIELDS,
                        "pandas": "1",
                    },
                    "daily",
                ),
            ]
        )
        for snapshot_date in snapshot_dates:
            plan.append(
                QuerySpec(
                    wind_ticker,
                    "IdxConsGet",
                    "历史成分覆盖探测",
                    {
                        "ticker": ticker,
                        "intoDate": str(snapshot_date),
                        "field": CONSTITUENT_FIELDS,
                        "pandas": "1",
                    },
                    f"constituents_{snapshot_date}",
                )
            )
        plan.append(
            QuerySpec(
                wind_ticker,
                "IdxCloseWeightGet",
                "历史收盘权重覆盖探测",
                {
                    "ticker": ticker,
                    "beginDate": INDEX_BEGIN_DATES[wind_ticker],
                    "endDate": QUERY_END_DATE,
                    "field": "",
                    "pandas": "1",
                },
                "close_weights",
            )
        )
    return plan


def _status_row(
    spec: QuerySpec, status: str, rows: int | None, error: str = ""
) -> dict[str, Any]:
    coverage, coverage_note = _declared_coverage(spec)
    return {
        "查询时间": datetime.now().astimezone().isoformat(timespec="seconds"),
        "Wind代码": spec.wind_ticker,
        "指数名称": INDEX_NAMES[spec.wind_ticker],
        "UQER查询代码": spec.uqer_ticker,
        "接口": spec.endpoint,
        "查询类型": spec.query_kind,
        "查询目的": spec.purpose,
        "参数摘要": _param_summary(spec.params),
        "接口声明覆盖": coverage,
        "接口声明说明": coverage_note,
        "状态": status,
        "返回行数": rows,
        "错误摘要": error,
        "可否据此判断无覆盖": "是" if status == "空结果" else "否",
    }


def execute_query_plan(
    api: Any, plan: Iterable[QuerySpec]
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """调用网关；前置连接/认证/配额失败后不继续轮询。"""

    specs = list(plan)
    statuses: list[dict[str, Any]] = []
    outputs: dict[str, pd.DataFrame] = {}
    blocking_status = ""

    for spec in specs:
        if blocking_status:
            statuses.append(
                _status_row(spec, f"未执行（前置{blocking_status}）", None)
            )
            continue
        try:
            result = getattr(api, spec.endpoint)(**spec.params)
            frame = result.copy() if isinstance(result, pd.DataFrame) else pd.DataFrame(result)
            if frame.empty:
                statuses.append(_status_row(spec, "空结果", 0))
                continue

            frame.insert(0, "query_kind", spec.query_kind)
            frame.insert(0, "query_endpoint", spec.endpoint)
            frame.insert(0, "query_uqer_ticker", spec.uqer_ticker)
            frame.insert(0, "query_wind_ticker", spec.wind_ticker)
            if "intoDate" in spec.params:
                frame.insert(4, "query_snapshot_date", spec.params["intoDate"])
            outputs[f"{spec.endpoint}__{spec.wind_ticker}__{spec.query_kind}"] = frame
            statuses.append(_status_row(spec, "有数据", len(frame)))
        except Exception as error:
            status = classify_query_error(error)
            statuses.append(_status_row(spec, status, None, _safe_error_summary(error)))
            if status in {"网关不可达", "网关认证失败", "配额用尽"}:
                blocking_status = status

    return pd.DataFrame(statuses), outputs


def write_outputs(
    status: pd.DataFrame,
    outputs: dict[str, pd.DataFrame],
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    status_output: Path = STATUS_OUTPUT,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    status_output.parent.mkdir(parents=True, exist_ok=True)
    status.to_csv(status_output, index=False, encoding="utf-8-sig")
    written = [status_output]

    by_endpoint: dict[str, list[pd.DataFrame]] = {}
    for frame in outputs.values():
        endpoint = str(frame["query_endpoint"].iloc[0])
        by_endpoint.setdefault(endpoint, []).append(frame)
    for endpoint, frames in by_endpoint.items():
        path = output_dir / f"UQER_{endpoint}.csv"
        pd.concat(frames, ignore_index=True, sort=False).to_csv(
            path, index=False, encoding="utf-8-sig"
        )
        written.append(path)
    return written


def load_gateway_api(client_dir: Path = DEFAULT_CLIENT_DIR) -> Any:
    """从管理员提供的 ``client.py`` 加载 DataAPI。"""

    client_path = client_dir / "client.py"
    if not client_path.is_file():
        raise RuntimeError(f"未找到网关客户端：{client_path}")
    sys.path.insert(0, str(client_dir))
    return importlib.import_module("client").DataAPI


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="通过Anemoi网关补查四只多资产配置指数。"
    )
    parser.add_argument("--client-dir", type=Path, default=DEFAULT_CLIENT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-output", type=Path, default=STATUS_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan = build_query_plan()
    try:
        api = load_gateway_api(args.client_dir)
        # INTERN_GUIDE 要求批量取数前先查全账号当日流量。
        traffic = api.getTraffic()
        print(
            "gateway traffic: remain={} bytes, used={}%".format(
                traffic.get("bytes_remain"), traffic.get("used_pct")
            )
        )
        status, outputs = execute_query_plan(api, plan)
    except Exception as error:
        status_name = classify_query_error(error)
        status = pd.DataFrame(
            [_status_row(plan[0], status_name, None, _safe_error_summary(error))]
            + [
                _status_row(spec, f"未执行（前置{status_name}）", None)
                for spec in plan[1:]
            ]
        )
        outputs = {}

    written = write_outputs(status, outputs, args.output_dir, args.status_output)
    print(f"UQER audit rows: {len(status)}")
    print(status["状态"].value_counts(dropna=False).to_string())
    for path in written:
        print(path)
    return 0 if (status["状态"] == "有数据").any() else 2


if __name__ == "__main__":
    raise SystemExit(main())
