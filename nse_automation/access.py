"""Security/series evidence joins. Snapshot eligibility is not live order clearance.

Definitions: CMTR73927 Part D Annexures 1/10; CMTR74466 Annexure A;
CMTR74969 (effective 2026-09-07). No filename-derived effective dates.
"""
import csv
import gzip
import hashlib
import io
import re
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

MASTER_SOURCE = 'https://nsearchives.nseindia.com/content/circulars/CMTR73927.zip'
CAS_SOURCE = 'https://nsearchives.nseindia.com/content/circulars/CMTR74466.zip'
PREOPEN_SOURCE = 'https://nsearchives.nseindia.com/content/circulars/CMTR74969.zip'
HOSTS = {'nseindia.com', 'www.nseindia.com', 'nsearchives.nseindia.com',
         'archives.nseindia.com', 'nseindia.in', 'www.nseindia.in', 'nsearchives.nseindia.in'}

def official_url(url):
    p = urlparse(url)
    return p.scheme == 'https' and p.hostname in HOSTS and not p.username and not p.password and p.port in (None, 443)

def decode_master(payload):
    if len(payload) > 20_000_000:
        raise ValueError('MASTER_COMPRESSED_SIZE_LIMIT')
    with gzip.GzipFile(fileobj=io.BytesIO(payload)) as stream:
        raw = stream.read(80_000_001)
    if len(raw) > 80_000_000:
        raise ValueError('MASTER_EXPANDED_SIZE_LIMIT')
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    required = {'FinInstrmId','TckrSymb','SctySrs','ISIN','PricRg',
                'SctyStsNrmlMkt','ElgbltyNrmlMkt','CallAuctnInd','DelFlg',
                'ElgbltyClsgAuctnSsn'}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError('MASTER_REQUIRED_COLUMNS_MISSING')
    rows = list(reader)
    if not rows:
        raise ValueError('MASTER_EMPTY')
    keys = set()
    for row in rows:
        if None in row or any(v is None for v in row.values()):
            raise ValueError('MASTER_RAGGED_ROW')
        key = (row['TckrSymb'].strip(), row['SctySrs'].strip())
        if not all(key) or not row['FinInstrmId'].isdigit() or not row['ISIN'].strip():
            raise ValueError('MASTER_IDENTIFIER_MISSING')
        if key in keys:
            raise ValueError('MASTER_DUPLICATE_SYMBOL_SERIES: ' + repr(key))
        keys.add(key)
    return rows, raw

def parse_range(value):
    if not re.fullmatch(r'\d+(?:\.\d+)?-\d+(?:\.\d+)?', value or ''):
        return None
    lo, hi = map(Decimal, value.split('-'))
    if not lo.is_finite() or not hi.is_finite() or lo <= 0 or hi < lo:
        return None
    return {'lower_inr': str(lo), 'upper_inr': str(hi)}

def normalize_date(value):
    if isinstance(value, date):
        return value.date() if isinstance(value, datetime) else value
    for fmt in ('%Y-%m-%d', '%d-%b-%Y', '%Y%m%d', '%d%m%Y'):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            pass
    raise ValueError('INVALID_EFFECTIVE_DATE: ' + str(value))

def band_status(value):
    """Blank is missing; explicit No Band does not prove derivative membership."""
    value = str(value or '').strip()
    if value.lower() == 'no band':
        return 'NO_FIXED_BAND_REPORTED'
    try:
        n = Decimal(value)
        if n.is_finite() and 0 < n <= 100:
            return 'FIXED_PERCENT_BAND'
    except InvalidOperation:
        pass
    return 'UNKNOWN'

def resolve_band_timeline(baseline_rows, deltas, target_date, *,
                          baseline_effective_date, coverage_through):
    """Apply verified deltas to a verified baseline, never manufacture its dates.

    Caller must supply independently verified baseline applicability and continuous
    official delta coverage. Dates are evidence inputs, not inferred from filenames.
    Rows require Symbol/Series/Band; deltas require Symbol/Series/To/Effective_Date.
    Conflicting same-day revisions require explicit supersession, not row ordering.
    This pure evaluator does not fetch, certify evidence or grant trading access.
    """
    target = normalize_date(target_date)
    start = normalize_date(baseline_effective_date)
    end = normalize_date(coverage_through)
    if not start <= target <= end:
        raise ValueError('BASELINE_OR_DELTA_COVERAGE_DOES_NOT_COVER_TARGET')
    result = {}
    for row in baseline_rows:
        key = (row.get('Symbol'), row.get('Series'))
        if not all(key) or key in result:
            raise ValueError('MISSING_OR_DUPLICATE_BASELINE_IDENTITY')
        result[key] = dict(row, Effective_Date=start.isoformat())
    grouped, future = {}, []
    for row in deltas:
        key = (row.get('Symbol'), row.get('Series'))
        if not all(key):
            raise ValueError('DELTA_SERIES_REQUIRED')
        effective = normalize_date(row['Effective_Date'])
        if effective > target:
            future.append(dict(row))
            continue
        if effective < start:
            continue
        if key not in result:
            raise ValueError('DELTA_IDENTITY_NOT_IN_BASELINE: ' + repr(key))
        grouped.setdefault((key, effective), set()).add(str(row['To']).strip())
    for (key, effective), values in sorted(grouped.items(), key=lambda x:x[0][1]):
        if len(values) != 1:
            raise ValueError('CONFLICTING_SAME_DATE_REVISIONS: ' + repr(key))
        value = next(iter(values))
        if band_status(value) == 'UNKNOWN':
            raise ValueError('INVALID_DELTA_BAND')
        result[key].update(Band=value, Effective_Date=effective.isoformat())
    return dict(records=list(result.values()), future_deltas=future,
                target_date=target.isoformat(), coverage_through=end.isoformat())

def master_record(row):
    unknown = []
    status = {'1':'PREOPEN','2':'OPEN','3':'SUSPENDED','4':'PREOPEN_EXTENDED',
              '5':'OPENS_WITH_MARKET','6':'PRICE_DISCOVERY'}
    mode = {'1':'NORMAL_MAINBOARD','2':'IPO_SPECIAL_PREOPEN','3':'RELIST_SPECIAL_PREOPEN',
            '4':'PERIODIC_CALL_AUCTION','5':'NORMAL_SME'}
    for key, allowed in [('SctyStsNrmlMkt',status),('CallAuctnInd',mode),
                         ('ElgbltyNrmlMkt',{'0','1'}),('DelFlg',{'N','Y'}),
                         ('ElgbltyClsgAuctnSsn',{'0','1'})]:
        if row.get(key) not in allowed:
            unknown.append(key + '=' + str(row.get(key)))
    limits = parse_range(row.get('PricRg'))
    if limits is None:
        unknown.append('PRICE_RANGE_INVALID_OR_MISSING')
    blocked = []
    if row.get('DelFlg') == 'Y': blocked.append('MASTER_DELETED')
    if row.get('SctyStsNrmlMkt') == '3': blocked.append('MASTER_NORMAL_MARKET_SUSPENDED')
    if row.get('ElgbltyNrmlMkt') == '0': blocked.append('MASTER_NORMAL_MARKET_NOT_ELIGIBLE')
    return dict(symbol=row['TckrSymb'],series=row['SctySrs'],isin=row['ISIN'],
                instrument_id=row['FinInstrmId'],price_range=limits,
                master_status=status.get(row.get('SctyStsNrmlMkt'),'UNKNOWN'),
                session_mode=mode.get(row.get('CallAuctnInd'),'UNKNOWN'),
                normal_market_eligible={'0':False,'1':True}.get(row.get('ElgbltyNrmlMkt')),
                closing_auction_eligible={'0':False,'1':True}.get(row.get('ElgbltyClsgAuctnSsn')),
                raw_codes={k:row.get(k) for k in ('SctyStsNrmlMkt','ElgbltyNrmlMkt','CallAuctnInd','ElgbltyClsgAuctnSsn','DelFlg','UpdDt')},
                unknown=unknown,blockers=blocked,
                definition_sources=[MASTER_SOURCE,CAS_SOURCE,PREOPEN_SOURCE],
                scope='File snapshot, not live market state; a preopen code is not an executed trade')

def reconcile(reg_records, master_rows, band_rows, band_evidence, target_date):
    """Do not propagate a dated change's proof to unaffected full-list rows.

    band_evidence contains only independently row-matched change-file records.
    A master snapshot has no embedded effective-date field. Keep its report date
    outside this function and do not convert its local update time into publication.
    """
    masters = {(r['TckrSymb'],r['SctySrs']):r for r in master_rows}
    bands = {}
    for row in band_rows:
        bands.setdefault((row.get('Symbol'),row.get('Series')), []).append(row)
    proven = {}
    for evidence in band_evidence:
        if evidence.get('status') != 'ROW_MATCH_VERIFIED' or evidence.get('effective_date') != target_date:
            continue
        for pair in evidence.get('records',[]):
            r = pair['csv_record']
            proven.setdefault((r['Symbol'],r['Series']),[]).append(r['To'])
    output = []
    for reg in reg_records:
        key = (reg['symbol'], reg['series'])
        master = master_record(masters[key]) if key in masters else None
        candidates = bands.get(key,[])
        values = set(r.get('Band') for r in candidates)
        band = next(iter(values)) if len(values) == 1 else None
        proof = proven.get(key,[])
        verified = len(proof) == 1 and band == proof[0]
        scope_current = reg.get('effective_trading_date') == target_date
        reasons = []
        if not scope_current: reasons.append('REG1_EFFECTIVE_DATE_MISMATCH')
        if master is None: reasons.append('SECURITY_SERIES_NOT_IN_MASTER')
        elif master['unknown']: reasons.extend(master['unknown'])
        if not candidates: reasons.append('COMPLETE_BAND_ROW_MISSING')
        elif len(values) != 1: reasons.append('CONFLICTING_COMPLETE_BAND_ROWS')
        if not verified: reasons.append('COMPLETE_BAND_EFFECTIVE_DATE_NOT_PROVEN_FOR_THIS_ROW')
        reasons.extend(['MASTER_TARGET_DATE_APPLICABILITY_REQUIRES_DATED_CONFIRMATION',
                        'SUBSEQUENT_SECURITY_NOTICES_AND_LIVE_STATUS_NOT_RECONCILED'])
        constraints = reg.get('session_constraints') or {}
        reasons.extend(constraints.get('unknown_inputs', []))
        unknown_indicators = [k for k,v in reg.get('indicators', {}).items()
                              if v.get('meaning') == 'Unknown']
        reasons.extend('UNMAPPED_REG1_FIELD:' + k for k in unknown_indicators)
        # REG1's dated prohibition remains enforceable independent of master ambiguity.
        access = 'Blocked' if scope_current and constraints.get('blockers') else 'Unknown'
        output.append(dict(symbol=key[0],series=key[1],target_date=target_date,
                           reg1_effective_date=reg.get('effective_trading_date'),
                           gsm_esm_constraints=constraints,master_snapshot=master,
                           band_percent_raw=band,band_effective_date=target_date if verified else None,
                           band_snapshot_status=band_status(band),
                           regulatory_snapshot_status=reg.get('snapshot_status','Unknown'),
                           band_effective_status='ROW_MATCH_VERIFIED' if verified else 'UNKNOWN',
                           trading_access=access,pending_checks=reasons))
    return output
