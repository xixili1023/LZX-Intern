---
name: yfinance-data
description: Use when an LZX-Intern project needs Yahoo Finance price history, quotes, ETF or fund metadata, corporate actions, financial statements, analyst data, or reproducible market-data inputs, including A-share, Hong Kong, US, index, ETF, and mutual-fund tickers.
---

# YFinance Data

Use Yahoo Finance as a convenient secondary research source. Treat identifiers, timestamps, currency, adjustment status, and missing fields as data that must be verified—not assumptions.

## Codex workflow

1. Read `.codex/instructions.md`, the target project's `02_Data`, and existing acquisition code before acting.
2. Inspect the active Python environment. Use the project's existing environment when available. If `yfinance`, `pandas`, or `numpy` is missing, state the missing dependency and request permission before installing anything.
3. Normalize and verify the ticker before retrieval:
   - Shanghai: `600000.SS`, `510300.SS`
   - Shenzhen: `000001.SZ`, `159915.SZ`
   - Hong Kong: zero-pad to four digits, for example `0700.HK`
   - US: ordinary ticker, for example `SPY`
   - Index: verify provider symbol, for example `000300.SS` or `^GSPC`
   These are candidate mappings; confirm returned name, exchange, quote type and currency.
4. Fix explicit `start`, `end`, interval, timezone and adjustment settings. Record the request timestamp and actual first/last observations. Do not rely only on a relative period for reproducible research.
5. Fetch the smallest dataset needed. Use `yf.download()` for aligned multi-ticker histories and `Ticker` methods for metadata, actions, statements, holdings or analyst fields.
6. Validate empty responses, duplicates, non-positive prices, missingness, trading-calendar alignment, currency, corporate actions, timezone, and suspicious adjustments. Cross-check important fund facts, NAV and benchmark definitions with the exchange, fund manager, prospectus or another authoritative source.
7. Keep project-specific large/raw data outside Git under `~/Desktop/InternData/<项目数据目录>`; document lineage and small validation summaries in the project's `02_Data`. Never save data or create a report unless the user requested it.
8. When a report is requested, pass verified evidence to `report-generation`; save it under the project's `07_Report`. Use `data-processing` for a reusable pipeline and `backtest` before claiming strategy performance.

## Data routes

| Need | Preferred method |
|---|---|
| Current quote | `Ticker.fast_info`, then selected `Ticker.info` fields |
| Historical OHLCV | `Ticker.history()` or `yf.download()` |
| Dividends/splits | `Ticker.actions`, `Ticker.dividends`, `Ticker.splits` |
| ETF/fund metadata | `Ticker.info`, then authoritative-source verification |
| Financial statements | `income_stmt`, `balance_sheet`, `cashflow` and quarterly variants |
| Analyst/earnings data | corresponding `Ticker` properties; retain source timestamps |
| Multiple assets or benchmark alignment | one `yf.download()` call, then explicit common-date alignment |

Read `references/api_reference.md` only when exact yfinance methods or edge cases are needed.

## Evidence contract

Every delivered dataset or result must state:

- input ticker and verified security identity;
- source and retrieval timestamp;
- requested and actual date range, interval and timezone;
- currency, price field and adjustment policy;
- row count, missing/dropped observations and validation warnings;
- local artifact path and data/hash version when an artifact was requested.

Distinguish verified facts, calculations, interpretations and unavailable fields. Do not fabricate values, silently substitute a security, or frame the output as investment advice.

## Common mistakes

- Treating `510300` as a valid Yahoo symbol without testing `510300.SS` and verifying identity.
- Calling a stale `navPrice` current NAV without checking its as-of time.
- Mixing currencies, timezones, adjusted and unadjusted prices, or non-overlapping calendars.
- Installing packages automatically or writing fetched data into the Git repository.
- Using Yahoo Finance as the sole source for fund manager, fee, benchmark or legal facts.

