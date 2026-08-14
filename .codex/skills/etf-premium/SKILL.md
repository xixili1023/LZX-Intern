---
name: etf-premium
description: Use when an LZX-Intern project analyzes an ETF's premium or discount to NAV or IOPV, market-price divergence, bid-ask spread, creation-redemption arbitrage, peer comparison, or abnormal intraday premium, including Chinese exchange-traded funds.
---

# ETF Premium and Discount

Measure an ETF market price against a NAV value with the same definition and as-of time. A precise formula applied to stale or mismatched data is not a valid premium estimate.

## Codex workflow

1. Read `.codex/instructions.md`, the target project's `02_Data`, and any existing fund research.
2. Use `yfinance-data` for Yahoo retrieval. If dependencies are missing, request permission before installation. Accept user-supplied or licensed data when Yahoo lacks reliable NAV/IOPV coverage.
3. Verify fund identity, exchange, currency, benchmark, fund type and trading status. For Chinese ETFs, test `.SS`/`.SZ` candidate mappings and confirm them against the exchange or fund manager.
4. Define the measurement before calculating:
   - closing price versus same-day official NAV;
   - intraday price versus contemporaneous IOPV/iNAV;
   - latest quote versus a disclosed but stale NAV.
   Label the third case as an indicative mismatch, not a live arbitrage signal.
5. Record both price and NAV timestamps. Align timezone, currency, valuation date and adjustment basis.
6. Calculate `premium_pct = (market_price / nav_or_iopv - 1) * 100`. Compare its magnitude with the bid-ask spread and, when available, creation/redemption, settlement, quota, suspension and underlying-market-hour constraints.
7. For peer comparison, use comparable funds tracking the same or closely related benchmark; disclose differences in fees, currency hedging, leverage, replication and market hours.
8. For a historical study, report distribution, persistence and extreme observations—not only the latest value. Investigate stale NAV, market closure, illiquidity, data errors and structural frictions before attributing a cause.
9. If the user requests an artifact, keep large/raw project data outside Git under `~/Desktop/InternData/<项目数据目录>` and put evidence-linked analysis in the target project. Send report-ready findings to `report-generation` for `07_Report`.

Read `references/etf_premium_reference.md` for formulas and interpretation. Read `references/gamma_squeeze_reference.md` only when the user explicitly requests options/dealer-gamma analysis and suitable options data exists.

## Required output

| Field | Requirement |
|---|---|
| Security | verified name, ticker, exchange and benchmark |
| Market price | value, field, currency and as-of timestamp |
| NAV/IOPV | value, definition, source and as-of timestamp |
| Premium/discount | percentage and formula |
| Trading context | spread, liquidity and underlying-market status when available |
| Comparison | matched peers and comparability limits |
| Evidence | source, retrieval time, observation count and validation warnings |

State whether the result is verified, indicative, stale, or unavailable. Never call a discount a bargain or a premium overvaluation by itself, and never recommend a trade from this metric alone.

## Common mistakes

- Comparing a live price with prior-day NAV without labeling the timestamp mismatch.
- Treating Yahoo `navPrice` as authoritative or uniformly available.
- Applying US ETF thresholds to Chinese, cross-border, bond, commodity or leveraged ETFs.
- Ignoring bid-ask spread, trading hours, suspension, FX and creation/redemption constraints.
- Inventing dealer-gamma explanations without options-chain, open-interest and hedge-model evidence.

