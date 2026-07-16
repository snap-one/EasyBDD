"""Easy BDD · Floci Browser — S3-console-style web UI for the local Floci emulator.

Browse buckets and folder trees, inspect object metadata, preview/download
files, upload new objects, and delete objects or whole prefixes — all against
the Floci endpoint (default http://localhost:4566) resolved exactly the same
way FlociService resolves it (FLOCI_ENDPOINT_URL et al.).

Started via frontend/start_floci_browser.py (port 8092 by default).
"""

from __future__ import annotations

import mimetypes
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from easybdd.services.floci_service import FlociService

app = FastAPI(
    title="Easy BDD Floci Browser",
    description="Web UI for browsing the local Floci S3 emulator",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"

# --- S3 client -------------------------------------------------------------
# FlociService only builds clients through _get_s3_clients(bucket), which
# auto-creates the bucket as a side effect — wrong for a read-mostly browser.
# Reuse its endpoint/credential resolution but build one bucket-agnostic
# client with no side effects.

_service = FlociService(logger=print)
_s3_client = None

# Looser than real S3 rules — Floci happily serves mixed-case bucket names
# (e.g. "Wattbox"), and this project already has such buckets.
_BUCKET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]{1,61}[A-Za-z0-9]$")


def _s3():
    global _s3_client
    if _s3_client is None:
        import boto3

        key, secret, region = _service._resolve_credentials()
        _s3_client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=_service._resolve_endpoint(),
            aws_access_key_id=key,
            aws_secret_access_key=secret,
        )
    return _s3_client


def _check_bucket(bucket: str) -> str:
    if not _BUCKET_RE.match(bucket):
        raise HTTPException(status_code=400, detail=f"Invalid bucket name: {bucket!r}")
    return bucket


def _check_key(key: str) -> str:
    if not key or key.endswith("/"):
        raise HTTPException(status_code=400, detail=f"Invalid object key: {key!r}")
    return key


def _s3_error(exc: Exception) -> HTTPException:
    code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
    if code in ("404", "NoSuchKey", "NoSuchBucket", "NotFound"):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=502, detail=f"Floci request failed: {exc}")


# --- Routes ----------------------------------------------------------------


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "floci_browser.html")


@app.get("/api/status")
async def status() -> Dict[str, Any]:
    endpoint = _service._resolve_endpoint()
    try:
        buckets = _s3().list_buckets().get("Buckets", [])
        return {"ok": True, "endpoint": endpoint, "bucket_count": len(buckets)}
    except Exception as e:
        return {"ok": False, "endpoint": endpoint, "error": str(e)}


@app.get("/api/buckets")
async def list_buckets() -> List[Dict[str, Any]]:
    try:
        resp = _s3().list_buckets()
    except Exception as e:
        raise _s3_error(e)
    return [
        {
            "name": b["Name"],
            "creation_date": b["CreationDate"].isoformat() if b.get("CreationDate") else None,
        }
        for b in resp.get("Buckets", [])
    ]


@app.get("/api/objects")
async def list_objects(
    bucket: str = Query(...),
    prefix: str = Query(""),
    token: Optional[str] = Query(None),
    max_keys: int = Query(500, ge=1, le=1000),
) -> Dict[str, Any]:
    """One level of the bucket tree: folders (common prefixes) + objects."""
    _check_bucket(bucket)
    kwargs: Dict[str, Any] = {
        "Bucket": bucket,
        "Prefix": prefix,
        "Delimiter": "/",
        "MaxKeys": max_keys,
    }
    if token:
        kwargs["ContinuationToken"] = token
    try:
        resp = _s3().list_objects_v2(**kwargs)
    except Exception as e:
        raise _s3_error(e)

    folders = [p["Prefix"] for p in resp.get("CommonPrefixes", [])]
    objects = [
        {
            "key": o["Key"],
            "name": o["Key"].rsplit("/", 1)[-1],
            "size": o["Size"],
            "last_modified": o["LastModified"].isoformat() if o.get("LastModified") else None,
        }
        for o in resp.get("Contents", [])
        if o["Key"] != prefix  # skip the zero-byte "folder marker" for the prefix itself
    ]
    return {
        "folders": folders,
        "objects": objects,
        "next_token": resp.get("NextContinuationToken"),
        "is_truncated": resp.get("IsTruncated", False),
    }


@app.get("/api/object/meta")
async def object_meta(bucket: str = Query(...), key: str = Query(...)) -> Dict[str, Any]:
    _check_bucket(bucket)
    _check_key(key)
    try:
        head = _s3().head_object(Bucket=bucket, Key=key)
    except Exception as e:
        raise _s3_error(e)
    return {
        "key": key,
        "size": head.get("ContentLength"),
        "last_modified": head["LastModified"].isoformat() if head.get("LastModified") else None,
        "content_type": head.get("ContentType"),
        "etag": (head.get("ETag") or "").strip('"'),
        "url": _service._build_object_url(bucket, key),
    }


def _stream_object(bucket: str, key: str, as_attachment: bool) -> StreamingResponse:
    try:
        obj = _s3().get_object(Bucket=bucket, Key=key)
    except Exception as e:
        raise _s3_error(e)
    content_type = (
        obj.get("ContentType")
        or mimetypes.guess_type(key)[0]
        or "application/octet-stream"
    )
    filename = key.rsplit("/", 1)[-1]
    disposition = "attachment" if as_attachment else "inline"
    headers = {
        "Content-Disposition": f'{disposition}; filename="{filename}"',
    }
    if obj.get("ContentLength") is not None:
        headers["Content-Length"] = str(obj["ContentLength"])
    return StreamingResponse(obj["Body"].iter_chunks(), media_type=content_type, headers=headers)


@app.get("/api/object/download")
async def download_object(bucket: str = Query(...), key: str = Query(...)):
    _check_bucket(bucket)
    _check_key(key)
    return _stream_object(bucket, key, as_attachment=True)


@app.get("/api/object/content")
async def object_content(bucket: str = Query(...), key: str = Query(...)):
    """Inline content for previews (images, text) — same bytes, no attachment."""
    _check_bucket(bucket)
    _check_key(key)
    return _stream_object(bucket, key, as_attachment=False)


@app.delete("/api/object")
async def delete_object(bucket: str = Query(...), key: str = Query(...)) -> Dict[str, Any]:
    _check_bucket(bucket)
    _check_key(key)
    try:
        _s3().delete_object(Bucket=bucket, Key=key)
    except Exception as e:
        raise _s3_error(e)
    return {"ok": True, "deleted": key}


@app.delete("/api/folder")
async def delete_folder(bucket: str = Query(...), prefix: str = Query(...)) -> Dict[str, Any]:
    _check_bucket(bucket)
    if not prefix or not prefix.endswith("/"):
        raise HTTPException(status_code=400, detail="Folder prefix must be non-empty and end with '/'")
    deleted = 0
    try:
        paginator = _s3().get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            keys = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if not keys:
                continue
            _s3().delete_objects(Bucket=bucket, Delete={"Objects": keys, "Quiet": True})
            deleted += len(keys)
    except Exception as e:
        raise _s3_error(e)
    return {"ok": True, "deleted_count": deleted, "prefix": prefix}


@app.post("/api/upload")
async def upload_objects(
    bucket: str = Form(...),
    prefix: str = Form(""),
    files: List[UploadFile] = File(...),
) -> Dict[str, Any]:
    _check_bucket(bucket)
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    uploaded: List[str] = []
    for f in files:
        name = Path(f.filename or "").name
        if not name:
            continue
        key = f"{prefix}{name}"
        content_type = f.content_type or mimetypes.guess_type(name)[0] or "application/octet-stream"
        body = await f.read()
        try:
            _s3().put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)
        except Exception as e:
            raise _s3_error(e)
        uploaded.append(key)
    return {"ok": True, "uploaded": uploaded}


if __name__ == "__main__":
    import os

    import uvicorn

    port = int(os.getenv("FLOCI_BROWSER_PORT", "8092"))
    uvicorn.run(app, host="0.0.0.0", port=port)
