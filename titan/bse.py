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


def targets(now, explicit=None):
    """Morning: search published history, not a fabricated holiday calendar."""
    if now.tzinfo is None:
        raise ValueError('An aware execution timestamp is required')
    now = now.astimezone(IST)
    if explicit:
        day = date.fromisoformat(explicit)
        if day > now.date():
            raise ValueError('Future report date')
        return [day]
    if now.time() >= time(16, 30):
        return [now.date()]
    # Include weekends: exchanges can hold special sessions.
    return [now.date() - timedelta(days=i) for i in range(1, 15)]


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


def collect(candidates, out):
    from playwright.sync_api import sync_playwright, TimeoutError as BrowserTimeout
    blocked = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        try:
            context = browser.new_context(accept_downloads=True)
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
                selects = page.locator('select')
                selects.nth(0).select_option(label=str(target.day))
                selects.nth(1).select_option(label=target.strftime('%b'))
                selects.nth(2).select_option(label=str(target.year))
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
        candidates = targets(datetime.now(IST), args.date)
        manifest['requested_dates'] = [d.isoformat() for d in candidates]
        manifest.update(collect(candidates, args.output))
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
