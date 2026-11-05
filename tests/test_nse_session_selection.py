import nse_automation.download as d
from datetime import datetime
import json
cases=[('2026-11-06T08:30:00','2026-11-05','ELIGIBLE_FOR_SINGLE_ATTEMPT'),('2026-11-05T16:30:00','2026-11-05','PENDING_PUBLICATION_WINDOW'),('2026-11-05T22:00:00','2026-11-05','ELIGIBLE_FOR_SINGLE_ATTEMPT'),('2026-11-07T08:00:00','2026-11-06','ELIGIBLE_FOR_SINGLE_ATTEMPT'),('2026-11-08T08:00:00','2026-11-06','ELIGIBLE_FOR_SINGLE_ATTEMPT'),('2026-11-08T22:00:00','2026-11-08','ELIGIBLE_FOR_SINGLE_ATTEMPT'),('2026-11-09T08:30:00','2026-11-08','ELIGIBLE_FOR_SINGLE_ATTEMPT'),('2026-11-10T22:00:00','2026-11-09','ELIGIBLE_FOR_SINGLE_ATTEMPT'),('2026-02-02T08:30:00','2026-02-01','ELIGIBLE_FOR_SINGLE_ATTEMPT'),('2026-04-01T08:30:00','2026-03-30','ELIGIBLE_FOR_SINGLE_ATTEMPT'),('2026-01-16T08:30:00','2026-01-14','ELIGIBLE_FOR_SINGLE_ATTEMPT')]
results=[]
for t,want,status in cases:
 got=d.select_date(datetime.fromisoformat(t).replace(tzinfo=d.IST));assert (str(got[0]),got[1])==(want,status);results.append(dict(input=t,date=want,status=status,passed=True))
for t in ['2027-01-01T08:30:00','2026-01-01T08:30:00']:
 try:d.select_date(datetime.fromisoformat(t).replace(tzinfo=d.IST));raise AssertionError('Missing calendar accepted')
 except ValueError as e:assert 'CALENDAR_COVERAGE_MISSING' in str(e)
results.append(dict(test='Year rollover fails explicitly without adjacent-year coverage',passed=True))
assert d.REG1_MAPS['GSM'].get('99','Unknown')=='Unknown'
assert d.REG1_MAPS['GSM']['0']=='GSM identified'
assert d.REG1_MAPS['GSM']['100']=='Not applicable'
assert d.REG1_MAPS['Status']['S']=='Suspended'
results.append(dict(test='REG1 zero versus 100, suspended, unknown composite code',passed=True))
from pathlib import Path
# Optional downloaded-artifact validation when supplied.
import os
artifact = os.environ.get('NSE_ARTIFACT_DIR')
m=json.loads((Path(artifact)/'manifest.json').read_text()) if artifact else {'datasets':[]}
for f in m['datasets']:
 got=d.validate(Path(artifact,f['filename']).read_bytes(),f['filename']);assert all(got[k]==f[k] for k in ['rows','bytes','sha256'])
results.append(dict(test='All six real CSV schemas and hashes',passed=True))
print(json.dumps(results,indent=2))
print(len(results),'tests passed')
