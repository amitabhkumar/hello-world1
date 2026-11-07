"""Date-effective NIFTY F&O rulebook for AEGIS research (not order routing).

Primary evidence:
* NSE/FAOP/64625 18 Oct 2024:
  https://nsearchives.nseindia.com/content/circulars/FAOP64625.pdf
  NIFTY 25 -> 75; weekly Dec19 2024 final legacy, weekly Jan02 2025
  first new; monthly Jan30 2025 last legacy, Feb27 2025 first new.
  New contracts introduced after 20 Nov 2024 have 75 but already listed
  contracts retain prior lots through expiry, so exact contract file remains
  the authority (this helper only addresses ordinary weekly/monthly maturities).
* NSE/FAOP/70616 03 Oct 2025:
  https://nsearchives.nseindia.com/content/circulars/FAOP70616.pdf
  NIFTY 75 -> 65, weekly Jan06 2026 and monthly Jan27 2026.
* NSE/FAOP/68747: expiry Thursday prior to Sep 2025 -> Tuesday after.
  https://nsearchives.nseindia.com/content/circulars/FAOP68747.pdf
* NSE/FAOP/74467: F&O market close 15:40 on 03 Aug 2026.
  https://nsearchives.nseindia.com/content/circulars/FAOP74467.pdf
* NSE option STT: 0.10% through Mar31 2026, 0.15% Apr01 onward.
  https://www.nseindia.in/static/products-services/equity-derivatives-securities-transaction-tax
* Upstox NSE option transaction charge 0.03503% Oct2024-Feb2026,
  revised to 0.03553% from 01 March 2026.
  https://upstox.com/brokerage-charges/

All non-weekly/non-monthly long-dated expiries need source contract metadata.
The model must never imply bid/ask or exchange-executed fills are available.
"""
from __future__ import annotations
import datetime as dt

RESEARCH_START=dt.date(2024,11,6)
RESEARCH_END=dt.date(2026,11,5)
CIRCULARS={
    "2024_nifty_lot":"NSE/FAOP/64625",
    "2026_nifty_lot":"NSE/FAOP/70616",
    "expiry_shift":"NSE/FAOP/68747",
    "cas":"NSE/FAOP/74467",
}

def nifty_option_lot(trade_date:dt.date,expiry:dt.date)->int|None:
    """Ordinary weekly/monthly NIFTY lots, keyed to exact *expiry*.

    For long-dated quarterlies use per-date exchange contract master instead.
    """
    if expiry<trade_date:
        return None
    # Every weekly/monthly expiry up to Dec 2024 stays 25. 2025
    # Jan monthly is an explicit exception, preserving its old 25 lot.
    if expiry<=dt.date(2024,12,31) or expiry==dt.date(2025,1,30):
        return 25
    if expiry<=dt.date(2025,12,30):
        return 75
    if expiry>=dt.date(2026,1,6):
        return 65
    return None

def is_expiry_weekday_plausible(expiry:dt.date)->bool:
    # Holiday shifts move expiry to prior open session, which can be
    # Wed before Sep2025, Mon before Sep2025, or Mon after Sep2025.
    if expiry<dt.date(2025,9,1):
        return expiry.weekday() in (0,1,2,3)
    return expiry.weekday() in (0,1)

def fo_session_last_minute(day:dt.date)->dt.time:
    return dt.time(15,39) if day>=dt.date(2026,8,3) else dt.time(15,29)

def is_regular_fo_minute(day:dt.date,minute:dt.time)->bool:
    return dt.time(9,15)<=minute<=fo_session_last_minute(day)

def option_stt_sale_rate(day:dt.date)->float:
    return 0.0015 if day>=dt.date(2026,4,1) else 0.0010

def nse_option_transaction_rate(day:dt.date)->float:
    return 0.0003553 if day>=dt.date(2026,3,1) else 0.0003503

def model_scope():
    return {"endpoints":"historical option-market OHLC only",
            "lot_size_authority":"NSE contract master overrides heuristic; no long dated legs",
            "execution_model":"adverse OHLC mark with slippage floor, no bid-ask/queue",
            "expiry":"no expiration-day exercise, squared off before expiry",
            "oos":"2026 previously evaluated and NOT a pristine holdout"}
