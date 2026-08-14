---
name: stock-correlation
description: Use when an LZX-Intern project examines correlation, beta, co-movement, diversification, concentration, rolling relationships, or regime-dependent dependence among funds, ETFs, stocks, indexes, factors, holdings, or portfolio returns.
---

# Asset and Fund Correlation

Estimate dependence from aligned returns, then test whether it is stable enough to support the stated research question. Correlation is descriptive, regime-dependent and not causation.

## Codex workflow

1. Read `.codex/instructions.md`, the target project's research question, `02_Data`, `04_Backtest` and existing experiments.
2. Obtain validated series through `yfinance-data` or the project's existing data pipeline. If dependencies are missing, request permission before installing them.
3. Define the estimand before computation: assets, benchmark, frequency, explicit date range, adjusted-price or NAV return, arithmetic or log return, Pearson/Spearman method, rolling window, currency treatment and missing-data rule.
4. Verify identity, currency, timezone, first/last dates, corporate-action adjustment and overlapping observations. Never forward-fill returns across non-trading dates merely to enlarge the sample.
5. Select the analysis:
   - pairwise correlation and directional beta for two series;
   - correlation matrix and concentration diagnostics for a fund or portfolio;
   - rolling correlation for stability;
   - regime-conditional correlation for stress behavior;
   - fund-versus-benchmark correlation, beta, tracking error and active-return diagnostics;
   - holdings-based analysis only when holdings dates and weights are available and verified.
6. Report sample size, full-sample estimate, rolling distribution and stress-period result when relevant. For many assets, identify clusters, redundant exposures and diversifiers without converting the result into a trade recommendation.
7. Record every dropped asset/date and test sensitivity to at least one reasonable lookback or window when the conclusion matters.
8. If the user requests an artifact, record formal runs in `06_Experiment/experiment_log.md`, keep raw/large project data outside Git under `~/Desktop/InternData/<项目数据目录>`, and send report-ready evidence to `report-generation` for the project's `07_Report`.

Read `references/sector_universes.md` only when dynamically constructing a US equity peer universe. For Chinese funds or securities, prefer a user-provided, licensed, exchange-defined or project-documented universe; do not reuse US sector lists.

## Minimum outputs

- verified assets and benchmark;
- requested and actual sample dates, frequency and observation count;
- return, adjustment, currency and missing-data conventions;
- correlation method and direction of beta;
- full-sample estimate plus stability or regime evidence;
- dropped observations/assets and sensitivity results;
- source, retrieval timestamp and data version;
- limitations: non-causality, sampling error and possible regime change.

## Interpretation guardrails

- Define beta explicitly, for example `beta(asset B | benchmark A) = cov(B,A) / var(A)`.
- Do not equate high correlation with cointegration or a profitable pair trade.
- Do not infer diversification from a calm-period correlation alone; inspect drawdown or high-volatility regimes.
- Do not compare correlations computed from different calendars, frequencies, currencies or return definitions.
- Do not fabricate holdings, classifications, causal links or negative-correlation hedges.
