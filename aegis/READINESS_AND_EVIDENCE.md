# AEGIS NIFTY Backtesting — Evidence and Readiness Register
Status as of 2026-11-06 (Asia/Kolkata). **No trade backtest has been executed.**
Evidence: https://github.com/amitabhkumar/hello-world1/actions/runs/42182650334
Source acquisition: https://github.com/amitabhkumar/hello-world1/actions/runs/42155340491
Storage: https://drive.google.com/drive/folders/1QKdK4ZBp9vtN2aL_e-NMsI7V9i8MpZhv

## Confirmed inputs (source-file coverage, not session-level completeness)
| Input | Rows | Min timestamp/date | Max timestamp/date | Initial schema/time audit |
|---|---:|---|---|---|
| 2024 intraday options | 14,592,609 | 2024-10-01 | 2024-12-31 | Passed |
| 2025 intraday options | 69,687,860 | 2025-01-01 | 2025-12-31 | Passed |
| 2026 intraday options | 40,177,780 | 2026-01-01 | 2026-07-21 | Passed |
| 2024 daily options | 394,150 | 2024-01-01 | 2024-12-31 | Passed |
| 2025 daily options | 394,283 | 2025-01-01 | 2025-12-31 | Passed |
| 2026 daily options | 215,562 | 2026-01-01 | 2026-06-29 | Passed |

Intraday schema fields: date, timestamp, underlying, expiry, strike, option_type, exercise_style, open, high, low, close, volume, oi, settle_price, source, granularity.
No historical option **bid/ask quotes** or precomputed **Greeks** in these files. Presence of OI column does **not** prove OI is populated or accurate.
The first pass verifies file/column/date boundaries; it does not prove every trading session, minute, strike, or expiry is covered or liquid.

## Readiness register (do not claim complete without executable evidence)
| Component | Status | Acceptance criterion |
|---|---|---|
| Free options daily datasets 2024–2026 | Downloaded | All source hashes verified; daily dataset extends through 2026-06-29 |
| Free options minute datasets 2024–2026 | Downloaded | All source hashes verified; minute dataset extends through 2026-07-21 |
| Initial options schema/time QA | Passed | All six jobs succeeded and audit artifacts saved in Drive |
| Comprehensive quality audit | Pending | Validate dates vs NSE trading calendar, unique keys, strikes/expiries, OHLC consistency, gaps, missing candles, liquidity |
| NIFTY spot 1-minute / futures 1-minute alignment | Pending | Verified synchronized dataset; no look-ahead |
| Historical India VIX | Pending | Align with NSE session dates and timestamps; regime definitions frozen |
| Options coverage after 2026-07-21 | Pending | Acquire through requested test end date or truncate the test with disclosure |
| Expiry/lot-size/calendar/cost engine | Pending | Historical date-effective rules and validated unit tests |
| Bid/ask-based execution | Not available | Obtain quotes or use a clearly labeled slippage proxy with sensitivity analysis |
| Greek inference | Pending | Fitted per-expiry/strike IV using forward and rates, negative/no-solution cases flagged |
| Signal & trade simulator | Not implemented | AEGIS modes A/B/C and risk stops codified without look-ahead; multi-leg execution |
| Walk-forward / out-of-sample testing | Not run | Frozen training parameters; untouched holdout; cost-adjusted statistics |
| Net P&L/win-rate/drawdown etc. | Not available | Derived only from executed evidence-backed strategy backtest |

## Why downloads did not complete the strategy
The download/split/reassemble GitHub Actions workflows do *not* implement historical signal construction, option pricing, multi-leg trade simulation, transaction-cost calculation or model validation. These are separate jobs that require supporting inputs and code. Do not report a profitable expectancy until executed against data.

## Next priority order
1. Complete trading-session/strike/expiry and minute missingness audit.
2. Source NSE spot/futures/VIX time series and fill 2026 gaps.
3. Implement historical expiry/lot-size/fees rules with tests.
4. Freeze and code AEGIS rules; run realistic fill/slippage sensitivity.
5. Publish per-trade ledger, train/test splits and out-of-sample metrics (or explicit missingness limitations).
