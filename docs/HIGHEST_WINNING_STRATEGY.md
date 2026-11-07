# Highest-Winning Published Trading Strategy — Mathematically Backed

**Researched:** 2026-11-07 (deep research of the live web)
**Question:** find the highest winning strategy out there right now, published, mathematically backed.
**Full research report:** `~/workspace/research_notes/highest-winning-published-trading-strate-20261107-1602/report.md` (outside this repo; this doc is the repo's copy of the findings)

---

## ⚠️ Read this first — what this document is, and what it is not

**This document has NOTHING to do with this repo's training data.**

- This repo (ARC-Neuron LLMBuilder) has **nothing to do with the datasets mentioned prior** — GSM8K, The Stack, or any other external dataset.
- The findings below are about **trading strategies for the crypto bots** (BrokeBot, Charm, Harvest — the separate crypto fleet). They are documented here **for reference only**.
- They are **NOT training data** for this repo. No model in this repo is trained on them. No strategy, number, or dataset in this document enters any training corpus in this repo.
- This repo's training uses **ONLY our own data** — the "us" corpus (general knowledge about our stuff and system). External datasets are **evaluation/benchmark references only** and **never enter the actual training data**. See [DATASET_ACQUISITION_MATRIX_3_0.md](./DATASET_ACQUISITION_MATRIX_3_0.md) and the training-data rule in the [README](../README.md).
- Testing of any strategy happens in the **continuous live running system** (the bots running, paper first) — not by mixing external test datasets into training.

If you are looking for what this repo trains on, stop here and read the dataset acquisition matrix. This document is a strategy reference for the trading bots, nothing more.

---

## Answer first — two different answers, and the distinction is the finding

- **By the reported numbers alone, the highest-winning published strategy is delta-neutral funding-rate / perpetual–spot cash-and-carry arbitrage, as reported by Werapun et al.: Sharpe ≈23.55 on Drift, ≈6.50 on ApolloX, best case +115.9% over six months with maximum drawdown 1.92%** — best case is Drift XRP at 7× leverage, selected from 60 scenarios. That is the headline winner. It is **not** a credible expectation for a small bot (see below).
- **The most credible version of that same winning family is He, Manela, Ross & von Wachter, "Fundamentals of Perpetual Futures" (arXiv:2212.06888): BTC Sharpe 1.80 at high (retail) trading costs, 2.00 in-sample, up to 3.5 for zero-fee market makers, ~6.4%/yr, active only ~20% of the time.** This is the strategy to work on — it is the existing TRON funding-rate arbitrage bot, formalised with a no-arbitrage derivation — but its edge has decayed sharply (see §3).
- **No published strategy credibly offers a high win rate *and* high returns to a small account.** The highest *credible* win rate found with a stated sample is BTC/ETH Ornstein–Uhlenbeck pairs trading at **61.7% on 47 trades — but p=0.062, i.e. not significant at 5%**. High win rates elsewhere came with the worst returns in their test. Win rate is not reported at all for most of the top-Sharpe papers.
- **The only mathematically *proven* item is not a trading signal at all: the Kelly criterion (Kelly 1956) proves log-optimal sizing *if* edge and odds are known. Avellaneda–Stoikov (2008) proves optimal quotes *under* its model assumptions. Everything else below is backtested, not proven.**

Confidence note from the research: `verified live` for arXiv/BIS/Quantpedia/QFC PDFs opened 2026-11-07; `index` (secondary summary) for the Werapun Sharpe 23.55 and Christin Sharpe 12.8, because the ScienceDirect page returned HTTP 400 on direct open — those two numbers are corroborated by two independent secondary summaries each, but were not read in the primary PDF.

---

## Ranked list — by reported Sharpe ratio (headline numbers, not credibility)

| Rank | Strategy | Publication | Math basis | Reported Sharpe | Reported return | Max DD | Win rate | Market / period | Small-bot implementable? |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Funding-rate arbitrage, CEX/DEX (delta-neutral) | Werapun et al., *Blockchain: Research and Applications* 7(4), 2025/2026, DOI 10.1016/j.bcra.2025.100354 | Funding-rate / perp–spot basis: long spot, short perp (or vice versa), collect 8h funding; delta-neutral | **23.55 (Drift), 6.50 (ApolloX), ~2.89 HODL benchmark** | **+115.9% over 6 months (best case, Drift XRP, 7× lev.)** | **1.92%** | Not reported | BTC/ETH/XRP/BNB/SOL; Binance, BitMEX, ApolloX, Drift; 60 scenarios; period not stated in abstract/summaries — short | Yes in code, **no in practice at that number** — niche DEX, thin liquidity, 7× lev., best-of-60 |
| 2 | Crypto carry trade (BTC cash-and-carry) | Christin, Routledge, Soska & Zetlin-Jones, "The Crypto Carry Trade", Carnegie Mellon WP, Aug 2022 | Same funding/carry: short perp, long spot; heterogeneous-beliefs / capital-constrained arbitrageurs, funding caps | **12.8 (USDT-settled), 7.0 (coin-settled)**; another secondary cites 8.76 for Tether-margined BTC — report as range **7–12.8, in-sample** | Not reported in sources found | Not reported | Not reported | BTC, Binance + BitMEX tick data | Yes — same two-leg bot as #1, on major CEX |
| 3 | Crypto carry (long-sample) | Schmeling, Schrimpf & Todorov, "Crypto Carry", BIS WP 1087 (Apr 2023, rev Oct 2025; now *Management Science*) + Borri, Liu, Tsyvinski & Wu, arXiv:2510.14435 v4 (2026) | Futures–spot basis / carry; convenience yield from trend-chasing leveraged longs + scarce arbitrage capital | **6.45 (2020–2025), 4.06 (from 2024), negative in 2025** (Borri et al.) | Carry averages >10%/yr, peaks 40–60%/yr (BIS) | Not reported (high carry predicts crashes; margin/liquidation spikes) | Not reported | BTC + ETH futures vs spot, CME + crypto-native venues | Yes, but edge is the decaying one — see §3 |
| 4 | Random-maturity perp–spot arbitrage | He, Manela, Ross & von Wachter, "Fundamentals of Perpetual Futures", arXiv:2212.06888 (Dec 2022, v7 Sep 2026) | **Random-maturity arbitrage**: no-arb perp price ∝ spot, constant ↑ in interest/funding ratio; bounds with trading costs; open when spread outside bound, close on return to no-cost relation | **1.80 retail (high costs), 2.00 in-sample, up to 3.5 zero-fee makers** (v6; v1 said up to 6.5, v3 said 1.92/3.94 — version drift, use 1.80 retail) | ~6.4%/yr, active ~20% of time; 0.3–1.1%/yr in 2022–23 (secondary summary, quantfirm) | Not reported | Not reported | BTC/ETH/BNB/DOGE/ADA, Binance 1h, BTC 2020-01-08–2024-03-11 (36,578 obs) | **Yes — best small-bot fit**: hourly data, threshold rule, no HFT needed |
| 5 | Avellaneda–Stoikov market making (+ regime extension) | Avellaneda & Stoikov (2008), *Quantitative Finance* 8(3) 217–224; empirical: HALO, QFC Texas State 2026 | **Stochastic control / HJB, CARA utility**: mid dS=σdW, Poisson arrivals λ(δ)=A·e^(−kδ); reservation price r=s−qγσ²(T−t); spread (2/γ)ln(1+γ/k)+γσ²(T−t) | **2.4 (HALO, SOL, 11.3 days — tiny sample); 1.52 A-S baseline / 1.84 regime-HJB (BTC LOB)**; honest Monte Carlo baseline **0.025** (500 paths) | Not reported as annual % | −5.2% (A-S baseline), −4.1% (HJB) | Not reported (fill % 44.1% in one BTC simulation) | SOL/USD tick (HALO); BTC LOB (baseline) | **Marginal / no for a small bot**: needs low latency, queue position, maker rebates; adverse selection dominates at fast cadences |
| 6 | BTC/ETH statistical arbitrage — cointegration / OU pairs | Whetstone, QFC Texas State 2026 | **Engle–Granger cointegration + Ornstein–Uhlenbeck spread** dZ=κ(μ−Z)dt+σdW; z-score entry \|z\|≥2, exit \|z\|≤0.5; half-life ln2/κ | **1.48 annualised** | **+22.3% total** (period: ~120,000×10-sec obs, date range not stated — ≈2 weeks by arithmetic, flag as derived) | **−8.3%** | **61.7% (47 round trips)** | BTC/ETH, Kraken via CCXT, 10-sec | Yes — $500/trade in backtest, 0.1% costs, ~42-min holds; but **p=0.062, not significant** |
| 7 | Time-series momentum (crypto) | Moskowitz, Ooi & Pedersen (2012), *JFE* 104(2) 228–250 (58 futures, 1985–2009); crypto update Kumar & Jenefer, *JOIREM* 4(4) Apr 2026 | **Time-series momentum**: sign of past 12m (or 252d) return predicts next return; volatility-scaled, monthly rebalance | **~1.0 diversified (MOP 2012); 0.82 pre-ETF / 1.22 post-ETF (crypto 2026)** | **18.03%/yr pre-ETF, 28.58%/yr post-ETF** (crypto, BTC/ETH/IBIT/FBTC/GLD/SPY, Jan 2018–Mar 2026) | −38.55% pre, −25.73% post | **52.57% pre, 52.23% post** | Crypto + traditional, 2018–2026 | Yes — simplest bot of all; but OOS replication 2010–2026 found gross Sharpe 0.42, net 0.38 (secondary) |
| 8 | Pairs trading — distance method (equities) | Gatev, Goetzmann & Rouwenhorst (2006), *Review of Financial Studies* 19(3) 797–827 | **Distance / mean reversion**: min sum-of-squared deviations of normalised prices, 12m formation / 6m trading, enter at 2 SD | **1.22 after costs (Quantpedia); ~1.4–1.5 before costs** | **11.16%/yr after costs** (top-20 pairs) | **−17%** | Not reported | US equities, 1962–2002 | Yes in code, **no as published for crypto**: needs shorting many equities, profits decayed to Sharpe ~0.4 post-2002 (Do & Faff) |

---

## 1. Funding-rate / perp–spot arbitrage (Ranks 1–4 — one family, four papers)

This is a single trade — long spot + short perp when funding/basis is positive, collect funding and/or basis convergence — measured four ways. The math is the strongest of any directional family: He et al. *derive* no-arbitrage bounds (random-maturity arbitrage, a weaker notion than classic arbitrage: positive payoff at an uncertain future time), and the trade is delta-neutral, so it does not bet on BTC direction. That is why it tops the list and why it matches the existing TRON funding-rate bot.

- **Werapun (#1):** 60 scenarios, best case is the winner. The 23.55 Sharpe is an in-sample, best-of-60, 7×-leveraged, niche-DEX (Drift, Solana) number. TradingStrategy's summary calls it "some of the highest in-sample Sharpe ratios ever reported for a crypto trading strategy" *and* warns the sample is short, venues are niche, and capacity is limited by venue liquidity. No win rate, no out-of-sample, no live track record found.
- **Christin (#2):** in-sample Sharpe 12.8 / 7.0, explicitly "benefit from not fully accounting for liquidation risk and exchange risk" (TradingStrategy summary). A different secondary cites 8.76 for the same Tether-margined BTC trade — the discrepancy is sample/spec, not error to resolve by picking one; report 7–12.8.
- **Borri/Schmeling (#3):** the long-sample reality check on the same trade. BIS: carry averages >10%/yr, peaks 40–60%/yr, but high carry predicts crashes and margin/liquidation spikes make the cash-and-carry risky. Borri et al.: Sharpe 6.45 (2020–2025) → 4.06 (from 2024) → **negative in 2025**.
- **He (#4):** the most implementable specification. Thresholds chosen as the model delivering the highest Sharpe in a 6-month validation sample among **210 model specifications** — itself a selection step to deflate for. Retail Sharpe 1.80 is the honest small-trader number; 3.5 requires zero fees (market-maker tier).

## 2. Market making — Avellaneda–Stoikov (Rank 5)

Proven *as a derivation*: under arithmetic Brownian motion + Poisson arrivals + CARA utility, the reservation-price / spread formulas are the HJB optimum. That proves optimal quoting *given the model*, not profitability in a real book. Empirical Sharpes (1.52 baseline, 1.84 regime, 2.4 HALO on 11.3 days of SOL) are short-sample / simulation-heavy; a deliberately honest Monte Carlo implementation reports Sharpe **0.025** across 500 paths once adverse selection and competition are included. HALO itself finds spread capture positive at all cadences but inventory mark-to-market losses from adverse selection dominate at faster cadences. For a small bot without maker rebates (none below ~0.5% of venue maker volume, per quantfirm review), queue priority, or co-location, this is the least transferable top strategy.

## 3. Statistical arbitrage — BTC/ETH OU (Rank 6) and equities pairs (Rank 8)

- BTC/ETH OU is the **only** top entry with both a win rate (61.7%) and a significance test — and the test fails (permutation p=0.062 on 1,000 shuffles, 47 trades). Hedge β=0.847, OU half-life ~28 min, avg hold ~42 min. Directly relevant to BTC/ETH spot+futures bots, cheap to implement, but the evidence is "statistically marginal but economically meaningful" in the authors' own words.
- Gatev equities pairs is the canonical stat-arb paper (11.16%/yr, Sharpe 1.22 after costs, vol 5.85%), with a true post-publication out-of-sample test (top-20, 10.4%/yr in 1999–2002) — rarer than most — but profitability decayed post-2002 (Sharpe ~0.4) and it is not a crypto strategy.

## 4. Momentum (Rank 7)

Moskowitz–Ooi–Pedersen is the most replicated anomaly in finance (58 futures, Sharpe ~1.0 diversified vs ~0.4 for equities). Crypto TSMOM (2026) reports 28.58%/yr, Sharpe 1.22 post-ETF, win rate ~52% — but the pre/post difference is not significant (Welch t, p=0.5835), MaxDD is −25.7% to −38.6%, and Liu & Tsyvinski's crypto momentum (top-quintile BTC +11.22% next week, Sharpe 0.45) is 2011–2018, pre-costs, pre-institutional. Cross-sectional momentum (Jegadeesh & Titman 1993, JF: ~1%/month, 1965–1989, winners-minus-losers) is the same family, not separately ranked — it is the long-short cousin of TSMOM.

## 5. Uniswap v3 concentrated liquidity — the existing spot activity, not a top strategy

Included because the bots run it, **not** ranked in the top 8: Loesch et al. / Topaze Blue & Bancor (2021, arXiv:2111.09192), 17 pools, 5 May–20 Sep 2021, ~17,000 wallets: **49.5% of LPs had negative returns vs simply holding; fees $199.3m vs impermanent loss $260.1m; IL exceeded fees in 80% of pools.** Only active managers who rebalanced often profited. Simulation-only improvements exist (DPRS: Sharpe 1.21, CIL 10.3% vs 25.8% static, 22.5% yield on ETH/USDC; DRL DDQN: Sortino 2.128, win rate 41.2%) — simulations, not live. A passive/small Uniswap v3 position is, on the published evidence, a volatility-selling bet whose fees on average did not cover IL.

## 6. Kelly criterion — mathematically proven, not a strategy

Kelly (1956), *Bell System Technical Journal* 35(4) 917–926: f*=(bp−q)/b, maximise E[log W]; max growth rate = information rate. Proved (for known p, b) to dominate any other fixed-fraction strategy almost surely in the long run. **It generates no signal, no Sharpe, no win rate.** Its practical content is sizing: full Kelly implies P(ever losing half the bankroll)=1/2 and P(ever −90%)=1/10; half-Kelly keeps ~75% of growth at half the stake. Practitioners use ¼–½ Kelly because p is estimated, not known. Use it to *size* the funding/carry bot below, not as a standalone strategy. A BTC illustration (7,003 trades, win 36.2%, payoff 2:1) gives f*=4.3% per trade — secondary, illustrative only.

---

## Single highest-winning strategy — what the numbers actually prove

**Headline winner: Werapun et al. funding-rate arbitrage on Drift (Sharpe 23.55, +115.9%/6mo, MDD 1.92%).**

What it proves:

- **Backtest only, not live.** No live or paper-trading track record was found for that number; the paper is a 60-scenario backtest comparison vs HODL.
- **Sample size / selection:** best of 60 scenarios. By Bailey–López de Prado logic, the expected best Sharpe after ~45–50 independent tries on 5 years of daily data is ~1.0 even with zero true edge; a best-of-60 Sharpe of 23.55 on a short, low-volatility, 7×-leveraged DEX sample is a selection artefact until replicated out-of-sample. No deflated Sharpe or PBO was reported for it.
- **Overfitting risk: very high.** Short sample, niche venue (Drift/ApolloX), 7× leverage (Sharpe is leverage-invariant in theory, but leverage amplifies liquidation/basis risk that Sharpe does not see), no stated out-of-sample window.
- **Realistic for a small account? No at 23.55; yes at 1.8.** A small account *can* run the same two-leg trade on Binance BTC/ETH (He et al. retail Sharpe 1.80), and on TRX cross-venue funding spreads (live 2026-11-07 snapshots showed TRX cross-venue captures up to ~42% APY before fees, 5-day averages ~15–25% APY — a snapshot, not a backtest). It cannot reproduce Drift-XRP 7× economics: capacity, liquidity, funding caps, and liquidation risk on a thin DEX leg bind first. Recent realised funding is far lower (mean +2.11%/yr BTC, Nov 2025–May 2026).

**Recommendation: work on the He et al. random-maturity / funding-carry family (Rank 4 as specified, Ranks 1–3 as the same family at inflated Sharpes), sized with fractional Kelly, validated walk-forward with a deflated Sharpe / PBO check — and expect Sharpe ~0.5–1.8, single-digit %/yr on BTC/ETH at retail fees in 2025–26, not 23.55 or 115.9%/6mo.** If the bot must pick one paper to implement, implement He et al.'s threshold rule (open outside the no-arb bound, close on return to the no-cost relation, 8h funding cycle, Binance BTC/ETH first, TRX cross-venue second), not Werapun's best-case Drift-XRP scenario.

---

## Proven (theorem) vs merely backtested

| Item | Status |
|---|---|
| Kelly criterion (1956) | **Proven** — log-optimal growth, IF p and odds known. Sizing only. |
| Avellaneda–Stoikov (2008) | **Proven under model** — HJB optimum for CARA market maker under ABM + Poisson flow. Profitability is *not* proven; depends on flow toxicity, queue, fees. |
| He et al. no-arb bounds | **Derived (random-maturity arbitrage)** — bounds are theorems under stated frictions; the *Sharpe* is empirical/backtested. |
| Cointegration / OU (Engle–Granger, OU process) | **Statistical theory** — stationarity tests and OU mean-reversion are theorems; that BTC/ETH *is* cointegrated in a given window is an empirical test (here, marginal). |
| Werapun, Christin, Borri, Moskowitz, Gatev, TSMOM-crypto, BTC/ETH OU, Uniswap DPRS/DRL | **Backtested only** — no theorem guarantees future returns. |

---

## Limitations — honest

- **Huge capital / HFT / rebates:** Avellaneda–Stoikov at published Sharpes needs maker-tier fees, queue position and latency; the 3.5 Sharpe in He et al. needs zero fees; Werapun's 23.55 needs a thin DEX leg a small account cannot scale. No rebates below ~0.5% of venue maker volume.
- **Single backtest, no out-of-sample:** Werapun (best-of-60, no OOS stated), Christin (in-sample, liquidation risk not fully counted), BTC/ETH OU (47 trades, p=0.062, date range not stated), HALO (11.3 days), crypto TSMOM 2026 (p=0.5835 for pre/post difference). Gatev is the exception with a genuine post-publication OOS window.
- **Decay is documented, not hypothetical:** carry Sharpe 6.45 → 4.06 → negative in 2025 (Borri); pairs Sharpe 1.4 → 0.4 post-2002 (Do & Faff); TSMOM OOS Sharpe 0.42 vs ~1.0 in-sample (secondary replication); funding mean +2.11%/yr in late 2025–26 vs >10%/yr historical average.
- **Win rate ≠ profit:** highest win rates found (Bollinger mean reversion 65.7% in a CoinQuant BTC test, +10.4% total, Sharpe 0.22; BTC/ETH OU 61.7%) do not imply highest returns; trend/momentum wins ~20–52% of trades and profits from a few large winners (BTC trend following: 20% win rate, profit factor 2.02).
- **Leverage and Sharpe:** Sharpe does not capture liquidation, funding-cap, exchange-failure, or basis-widening risk — the exact risks BIS and Christin flag for carry. A 7× leveraged 1.92% MaxDD is a backtest artefact if one liquidation wipes the leg.
- **Overfitting yardstick:** Bailey & López de Prado (2014) Deflated Sharpe; Bailey et al. (2017) PBO; Harvey–Liu–Zhu (2016) t>3.0 hurdle; McLean & Pontiff (2016) −26% OOS, −58% post-publication. Apply DSR/PBO to *any* strategy before live capital — none of the top-Sharpe crypto papers above reports a DSR.

## Could not verify

- Werapun et al. primary PDF: ScienceDirect page returned HTTP 400 on direct open (2026-11-07); Sharpe 23.55 / 6.50 and 115.9%/1.92% are corroborated by TradingStrategy docs and QMX research notes, not read in the primary paper. Win rate, exact sample dates, and fee treatment for Werapun were not found in any accessible source.
- Christin et al. Sharpe: 12.8/7.0 (TradingStrategy) vs 8.76 (FutureFinanceLab/GMU secondary) — different samples/specs; reported as a range.
- He et al. Sharpe by version: 1.80/3.5 (Jul 2024, v6), 1.92/3.94 (Apr 2023, v3), up to 6.5 (v1); used v6 retail figure 1.80.
- BTC/ETH OU backtest date range: not stated in the PDF text extracted; ~120,000 10-sec observations implies a short (≈2-week) window, labelled as derived, not stated.
- No published TRX-specific funding-arbitrage paper was found; TRX is covered only by the generic funding/carry papers and live funding dashboards.
- No win rate was found for Werapun, Christin, He, Borri/Schmeling, Gatev, or Avellaneda–Stoikov (original).

## Sources

- Werapun et al. (2025/2026) — https://www.sciencedirect.com/science/article/pii/S2096720925000818 — DOI 10.1016/j.bcra.2025.100354 — index/secondary corroboration, direct open failed 2026-11-07; corroborated at https://github.com/tradingstrategy-ai/docs/blob/HEAD/source/learn/carry-trade.rst and https://openalex.org/works/W4413003388
- He, Manela, Ross, von Wachter, "Fundamentals of Perpetual Futures" — https://arxiv.org/abs/2212.06888 — verified live 2026-11-07; PDF v6 at https://storage.googleapis.com/arxiv-dataset/arxiv/arxiv/pdf/2212/2212.06888v6.pdf
- Christin et al., "The Crypto Carry Trade" (2022) — via https://github.com/tradingstrategy-ai/docs/blob/HEAD/source/learn/carry-trade.rst (lines 121–134)
- Schmeling, Schrimpf & Todorov, "Crypto Carry", BIS WP 1087 — https://www.bis.org/publ/work1087.htm — verified live 2026-11-07
- Borri, Liu, Tsyvinski & Wu, "Cryptocurrency as an Investable Asset Class: Coming of Age", arXiv:2510.14435 — https://arxiv.org/abs/2510.14435 — verified live 2026-11-07
- Moskowitz, Ooi & Pedersen (2012), *JFE* 104(2) 228–250 — via https://foxholm.com/q/research/moskowitz-ooi-pedersen-time-series-momentum/ and https://rpmfonder.squarespace.com/s/Time-Series-Momentum-Moskowitz-et-al.pdf
- Kumar & Jenefer (2026), TSMOM in crypto, *JOIREM* 4(4) — https://zenodo.org/records/19671502/files/TIME-SERIES%20MOMENTUM%20IN%20CRYPTOCURRENCY%20MARKETS%20A%20PRE%20AND%20POST%20SPOT%20BITCOIN%20ETF%20ANALYSIS.pdf
- Liu & Tsyvinski (2021), *RFS* 34(6) 2689–2727 — https://www.nber.org/papers/w24877 (cited via secondaries)
- Jegadeesh & Titman (1993), *Journal of Finance* — via https://signalstrike.trade/blog/momentum-investing-research
- Gatev, Goetzmann & Rouwenhorst (2006), *RFS* 19(3) 797–827 — https://quantpedia.com/strategies/pairs-trading-with-stocks — verified live 2026-11-07
- Whetstone, QFC, BTC/ETH stat arb (2026) — https://www.quantfinancecollective.org/papers/Stat_Arb_Paper.pdf — verified live 2026-11-07
- Avellaneda & Stoikov (2008), *Quantitative Finance* 8(3) 217–224 — via https://www.submillisecond.com/glossary/market-making/avellaneda-stoikov and https://deepwiki.com/ahmetsbilgin/regime-aware-optimal-quoting/4.2-avellaneda-stoikov-baseline ; HALO — https://www.quantfinancecollective.org/papers/Halo_Paper__2_.pdf
- Kelly (1956), *Bell System Technical Journal* 35(4) 917–926 — https://bpb-us-w2.wpmucdn.com/u.osu.edu/dist/7/36891/files/2017/07/Kelly1956-1uwz47o.pdf
- Loesch et al. / Topaze Blue & Bancor (2021), Uniswap v3, arXiv:2111.09192 — via https://www.jewelswap.io/blog/concentrated-liquidity-clmm-explained
- Bailey & López de Prado (2014) Deflated Sharpe; Bailey et al. (2017) PBO — via https://alphaprime.trading/en/learn/backtest-overfitting-research/ and https://www.turbinefi.com/blog/why-backtests-lie-prediction-market-overfitting-2026
- TRX live funding (snapshot 2026-11-07, not a backtest) — https://www.coinglass.com/FundingRate/TRX and https://www.gametophournow.com/funding/trx
