"""Normal browser BSE UDiFF acquisition; never bypass access controls."""
import argparse
import csv
import hashlib
import io
import json
import re
import sys
import zipfile
from datetime import date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import urlparse, unquote
from zoneinfo import ZoneInfo

IST = ZoneInfo('Asia/Kolkata')
MAX_BYTES = 50_000_000
REQUIRED = {'TradDt', 'Src', 'Sgmt', 'FinInstrmId', 'ISIN', 'OpnPric', 'HghPric',
            'LwPric', 'ClsPric', 'TtlTradgVol'}

class Blocked(RuntimeError):
    pass

class Unavailable(RuntimeError):
    pass


def targets(now, explicit=None, holidays=None, calendar_years=None, special_sessions=()):
    """Before 19:00 IST use previous session; after 19:00 use latest session."""
    if now.tzinfo is None:
        raise ValueError('An aware execution timestamp is required')
    now = now.astimezone(IST)
    if explicit:
        day = date.fromisoformat(explicit)
        if day > now.date():
            raise ValueError('Future report date')
        return [day]
    if holidays is None or calendar_years is None:
        raise Unavailable('Verified exchange holiday calendar required')
    day = now.date() if now.time() >= time(19) else now.date() - timedelta(days=1)
    for _ in range(370):
        if day.year not in calendar_years:
            raise Unavailable(f'Calendar unavailable for {day.year}; do not guess across year boundary')
        if day in special_sessions or (day.weekday() < 5 and day not in holidays):
            return [day]
        day -= timedelta(days=1)
    raise Unavailable('No eligible session in verified calendar')


def date_controls(controls, target):
    """Identify date dropdowns by their complete options, not DOM position."""
    choices = {}
    for index, control in enumerate(controls):
        if not control.get('visible', True):
            continue
        options = control['options']
        numbers = {int(o['text'].strip()) for o in options if o['text'].strip().isdigit()}
        month_names = {datetime(2000,m,1).strftime('%b').lower(): m for m in range(1,13)}
        labels = {o['text'].strip().lower()[:3] for o in options}
        role = ('year' if target.year in numbers and any(n >= 2000 for n in numbers)
                else 'day' if set(range(1,29)).issubset(numbers)
                else 'month' if set(month_names).issubset(labels) or numbers == set(range(1,13)) else None)
        if not role:
            continue
        wanted = getattr(target, role)
        matches=[]
        for option in options:
            label=option['text'].strip()
            value=int(label) if label.isdigit() else month_names.get(label.lower()[:3]) if role=='month' else None
            if value==wanted:matches.append(option['value'])
        if len(matches)!=1 or role in choices:
            raise ValueError(f'Ambiguous {role} dropdown/options')
        choices[role]=(index,matches[0])
    if set(choices)!={'day','month','year'}:
        raise ValueError('Cannot identify unique date controls; inspect date_controls.json')
    return choices


def csv_bytes(payload):
    if len(payload) > MAX_BYTES:
        raise ValueError('Oversized download')
    if payload.startswith(b'PK'):
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = [i for i in archive.infolist() if not i.is_dir()]
            if len(members) != 1 or not members[0].filename.lower().endswith('.csv'):
                raise ValueError('Expected exactly one CSV in ZIP')
            if members[0].file_size > MAX_BYTES:
                raise ValueError('Oversized uncompressed CSV')
            payload = archive.read(members[0])  # CRC verified; no filesystem extraction
    return payload


def validate(payload, target):
    payload = csv_bytes(payload)
    reader = csv.DictReader(io.StringIO(payload.decode('utf-8-sig')))
    if not REQUIRED.issubset(reader.fieldnames or []):
        raise ValueError('Missing UDiFF columns (or HTML instead of CSV)')
    count = 0
    for row in reader:
        if row['TradDt'].strip() != target.isoformat():
            raise ValueError('Wrong or mixed report dates')
        if row['Src'].strip().upper() != 'BSE' or row['Sgmt'].strip().upper() != 'CM':
            raise ValueError('Not BSE cash-market data')
        if not row['FinInstrmId'].strip():
            raise ValueError('Missing instrument ID')
        count += 1
    if count == 0:
        raise ValueError('Empty bhavcopy')
    return payload, {'report_date': target.isoformat(), 'rows': count,
                     'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}


def matching_url(href, target):
    u = urlparse(href)
    return (u.scheme == 'https' and
            (u.hostname == 'bseindia.com' or (u.hostname or '').endswith('.bseindia.com')) and
            re.fullmatch(r'BhavCopy_BSE_CM_0_0_0_' + target.strftime('%Y%m%d') +
                         r'_F_0000\.csv(?:\.zip)?', unquote(u.path).split('/')[-1], re.I) is not None)


def collect(candidates, out, now=None, explicit=None, manifest=None):
    from playwright.sync_api import sync_playwright, TimeoutError as BrowserTimeout
    blocked = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        try:
            context = browser.new_context(accept_downloads=True)
            if candidates is None:
                from titan.bse_data import collect_one
                result = collect_one(context, 'calendar', now.date().isoformat(), out)
                if result['status'] != 'VALIDATED_DATED_RECORDS':
                    raise Unavailable('Official BSE calendar retrieval/validation failed: '+str(result.get('error')))
                rows = json.loads((out/'calendar'/'equity_holidays.json').read_text())
                holidays = {date.fromisoformat(x['date']) for x in rows}
                if not holidays:
                    raise Unavailable('Empty annual holiday calendar')
                notices=result.get('special_session_notices',[])
                special=set()
                for notice in notices:
                    match=re.search(r'([A-Z][a-z]+ \d{1,2}, \d{4})',notice)
                    if 'Muhurat Trading' in notice and match:
                        special.add(datetime.strptime(match.group(1),'%B %d, %Y').date())
                manifest['calendar_evidence'] = {'source':result['source_url'], 'rows':len(rows), 'special_session_notices':notices}
                years={d.year for d in holidays}
                # Retain verified previous-year calendars for January rollover.
                for file in (Path(__file__).parent/'calendars').glob('*.json'):
                    saved=json.loads(file.read_text())
                    if saved['year'] in years:continue
                    holidays.update(date.fromisoformat(x) for x in saved['holidays'])
                    special.update(date.fromisoformat(x) for x in saved.get('special_sessions',[]))
                    years.add(saved['year'])
                candidates=targets(now,explicit,holidays,years,special)
                manifest['calendar_status']='OFFICIAL_CALENDAR; FINAL_FILE_REQUIRED; SPECIAL_SESSION_HOURS_NOT_INFERRED'
                manifest['requested_dates']=[d.isoformat() for d in candidates]
            page = context.new_page()
            page.set_default_timeout(30_000)
            def response_seen(response):
                host = urlparse(response.url).hostname or ''
                if (host == 'bseindia.com' or host.endswith('.bseindia.com')) and response.status in (401, 403, 429):
                    blocked.append(response.status)
            page.on('response', response_seen)
            def check():
                body = page.locator('body').inner_text()
                if blocked or re.search(r'access denied|verify you are human|captcha|request blocked', body, re.I):
                    raise Blocked(f'Access restriction; stop without retry. HTTP={blocked}')
            page.goto('https://www.bseindia.com', wait_until='domcontentloaded')
            check()
            page.locator("a:has-text('Markets'):visible, #menu-markets").first.click()
            page.locator("a:has-text('Equity'):visible").first.click()
            page.locator("a:has-text('Bhav Copy'):visible").first.click()
            page.locator('select').first.wait_for()
            check()
            for target in candidates:
                controls=page.locator('select').evaluate_all("ss=>ss.map(s=>({id:s.id,name:s.name,visible:!!(s.offsetWidth||s.offsetHeight||s.getClientRects().length),options:[...s.options].map(o=>({text:o.text,value:o.value}))}))")
                (out/'date_controls.json').write_text(json.dumps(controls,indent=2))
                choices=date_controls(controls,target)
                for role in ['year','month','day']:
                    index,value=choices[role]
                    page.locator('select').nth(index).select_option(value=value)
                page.locator("#Submit, input[value='Submit'], button:has-text('Submit')").first.click()
                # Wait for the requested filename or an explicit no-data response.
                # A timeout is not silently treated as a holiday.
                token = 'BhavCopy_BSE_CM_0_0_0_' + target.strftime('%Y%m%d') + '_F_0000'
                try:
                    page.wait_for_function("""token => [...document.querySelectorAll('a[href]')].some(a => a.href.toLowerCase().includes(token.toLowerCase())) || /no (?:records|data|file).*?(?:found|available)|access denied|captcha/i.test(document.body.innerText)""", arg=token)
                except BrowserTimeout:
                    check()
                    raise RuntimeError('No confirmed report/no-data response; inspect BSE page layout')
                check()
                links = page.locator('a[href]')
                matches_by_url = {}
                for i in range(links.count()):
                    link = links.nth(i)
                    href = link.evaluate('(a) => a.href')
                    if matching_url(href, target) and link.is_visible():
                        matches_by_url.setdefault(href, link)
                matches = list(matches_by_url.values())
                if not matches:
                    continue
                if len(matches) != 1:
                    raise ValueError('Ambiguous report links')
                source = matches[0].evaluate('(a) => a.href')
                with page.expect_download(timeout=60_000) as event:
                    matches[0].click()
                download = event.value
                if download.failure():
                    check()
                    raise RuntimeError('Browser download failed')
                temp = out / 'download.part'
                try:
                    download.save_as(temp)
                    if temp.stat().st_size > MAX_BYTES:
                        raise ValueError('Oversized download')
                    payload, info = validate(temp.read_bytes(), target)
                finally:
                    temp.unlink(missing_ok=True)
                filename = 'BhavCopy_BSE_CM_0_0_0_' + target.strftime('%Y%m%d') + '_F_0000.csv'
                (out / filename).write_bytes(payload)
                return dict(info, filename=filename, source_url=source)
            raise Unavailable('No published file found for the requested date range')
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', help='Explicit YYYY-MM-DD; otherwise India-time mode')
    parser.add_argument('--output', type=Path, default=Path('output'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        parser.error('Output directory must be empty; use a new run directory')
    manifest = {'started_at': datetime.now(IST).isoformat(), 'status': 'STARTED',
                'drive_status': 'NOT_TRANSFERRED', 'calendar_status': 'VERIFY_IN_SOP_TASK'}
    code = 1
    try:
        now=datetime.now(IST)
        manifest['date_policy']='Before 19:00 IST previous completed session; at/after 19:00 latest eligible session; explicit date overrides'
        manifest.update(collect(None, args.output, now=now, explicit=args.date, manifest=manifest))
        manifest['status'] = 'VALIDATED_DOWNLOAD'
        code = 0
    except Blocked as e:
        manifest.update(status='ACCESS_BLOCKED', error=str(e))
        code = 3
    except Unavailable as e:
        manifest.update(status='NOT_PUBLISHED_OR_NO_SESSION', error=str(e))
        code = 2
    except Exception as e:
        manifest.update(status='FAILED', error=f'{type(e).__name__}: {e}')
    manifest['finished_at'] = datetime.now(IST).isoformat()
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))
    return code

if __name__ == '__main__':
    sys.exit(main())

