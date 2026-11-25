"""One-pass Drive delivery with streamed uploads and independent media readback."""
import argparse
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from titan.drive_sync import inventory

FILES = "https://www.googleapis.com/drive/v3/files"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(stream):
    h = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        h.update(chunk)
    return h.hexdigest()


def quote(value):
    return value.replace("\\", "\\\\").replace("'", "\\'")


class Drive:
    def __init__(self):
        form = {key: os.environ["GDRIVE_" + key.upper()] for key in
                ("client_id", "client_secret", "refresh_token")}
        form["grant_type"] = "refresh_token"
        with urlopen("https://oauth2.googleapis.com/token", urlencode(form).encode(), timeout=60) as response:
            self.token = json.load(response)["access_token"]

    def request(self, method, url, **kwargs):
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = "Bearer " + self.token
        return urlopen(Request(url, method=method, headers=headers, **kwargs), timeout=300)

    def candidates(self, folder, name):
        # Reuse a previous dated revision on subsequent deliveries of those bytes.
        q = (f"'{quote(folder)}' in parents and trashed=false and "
             f"(name='{quote(name)}' or appProperties has {{ key='sourceNameHash' and "
             f"value='{hashlib.sha256(name.encode()).hexdigest()}' }})")
        params = dict(q=q, fields="nextPageToken,incompleteSearch,files(id,name,sha256Checksum)",
                      pageSize=1000, supportsAllDrives="true", includeItemsFromAllDrives="true")
        while True:
            with self.request("GET", FILES + "?" + urlencode(params)) as response:
                page = json.load(response)
            if page.get("incompleteSearch"):
                raise ValueError("Incomplete Drive file listing")
            yield from page["files"]
            if "nextPageToken" not in page:
                return
            params["pageToken"] = page["nextPageToken"]

    def upload(self, path, name, folder):
        metadata = dict(name=name, parents=[folder], appProperties={
            "sourceNameHash": hashlib.sha256(path.name.encode()).hexdigest()})
        with self.request("POST", UPLOAD + "?uploadType=resumable&supportsAllDrives=true",
                          data=json.dumps(metadata).encode(), headers={"Content-Type": "application/json"}) as r:
            location = r.headers["Location"]
        dest = urlsplit(location)
        if dest.scheme != "https" or dest.hostname != "www.googleapis.com":
            raise ValueError("Unexpected Drive upload destination")
        with path.open("rb") as body, self.request("PUT", location, data=body, headers={
                "Content-Length": str(path.stat().st_size), "Content-Type": "application/octet-stream"}) as r:
            return json.load(r)["id"]

    def verify(self, file_id, folder, expected):
        url = FILES + "/" + file_id + "?supportsAllDrives=true"
        with self.request("GET", url + "&fields=parents") as r:
            parents = json.load(r).get("parents", [])
        with self.request("GET", url + "&alt=media") as r:
            actual = digest(r)
        if parents != [folder] or actual != expected:
            raise ValueError("Drive readback SHA-256 or parent mismatch")


def deliver(drive, path, receipt):
    folder = receipt["folder_id"]
    candidates = list(drive.candidates(folder, path.name))
    for candidate in candidates:
        if candidate.get("sha256Checksum") == receipt["sha256"]:
            receipt.update(file_id=candidate["id"], file_name=candidate["name"], action="REUSED_DUPLICATE")
            break
    else:
        name = path.name
        action = "UPLOADED_NEW"
        if candidates:
            date = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            name = f"{path.stem}_{date}_{uuid.uuid4().hex}{path.suffix}"
            action = "UPLOADED_REVISION"
        receipt.update(file_name=name, action=action)
        receipt["file_id"] = drive.upload(path, name, folder)
    receipt["upload_time"] = stamp()
    drive.verify(receipt["file_id"], folder, receipt["sha256"])
    receipt["readback_status"] = "VERIFIED"


def run(root, single):
    dest = root / "oauth" / "drive_sync_receipt.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise FileExistsError("Receipt already exists")
    records, errors = [], []
    try:
        if single:
            paths = [single]
        else:
            manifest = root / "manifest.json"
            files, errors = inventory(root, json.loads(manifest.read_text()))
            paths = list(dict.fromkeys(Path(f["path"]) for f in files))
            paths.extend(p for p in (manifest, root / "sop_v3_manifest_summary.json",
                                      root / "drive_sync_receipt.json") if p.is_file())
        drive = Drive()
        for path in paths:
            record = dict(file_id=None, file_name=path.name, sha256=None, bytes=path.stat().st_size,
                          folder_id=os.environ["GDRIVE_INCOMING_FOLDER_ID"], action=None,
                          upload_time=None, readback_status="FAILED")
            records.append(record)
            with path.open("rb") as stream:
                record["sha256"] = digest(stream)
            deliver(drive, path, record)
    except Exception as exc:
        # Keep request URLs, session URIs and OAuth responses out of artifacts.
        errors.append(dict(error=type(exc).__name__, http_status=getattr(exc, "code", None)))
    result = records[0].copy() if single and records else {"files": records}
    result.update(errors=errors, readback_status="FAILED" if errors else "VERIFIED")
    with dest.open("x") as stream:
        json.dump(result, stream, indent=2)
    return bool(errors)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--file", type=Path)
    args = parser.parse_args()
    raise SystemExit(run(args.root, args.file))
