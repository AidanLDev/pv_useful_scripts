import json
import math
import os
import subprocess
import tempfile
import urllib.request
import time
from pathlib import Path
from urllib.parse import urlparse

import boto3
from botocore.config import Config

LOCATION_ID = "98d2ca8c-73c2-4110-99cf-c6d2b24ec9bb"
URL_TIMEOUT = 14400
FILE_TYPE = "real-time"
PART_SIZE_BYTES = 8 * 1024 * 1024  # 8 MB — AWS minimum for non-final parts is 5 MB

video_path = Path(__file__).parent / "2026-04-11T04_40_00_TILL_2026-04-11T04_44_00.mkv"
ps_script = Path(__file__).parent / "upload_to_s3.ps1"
root_env = Path(__file__).parent.parent / "root.env"

if not video_path.exists():
    raise FileNotFoundError(f"Video file not found: {video_path}")


def load_env(path):
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def parse_presigned_url(url):
    p = urlparse(url)
    parts = p.netloc.split(".")
    bucket = parts[0]
    s3_key = p.path.lstrip("/")
    use_accelerate = "s3-accelerate" in p.netloc
    # Standard format: {bucket}.s3.{region}.amazonaws.com has 5+ parts
    region = ".".join(parts[2:-2]) if parts[1] == "s3" and len(parts) >= 5 else None
    return bucket, region, s3_key, use_accelerate


def build_multipart_config(s3_client, bucket, s3_key, file_path):
    file_size = file_path.stat().st_size
    part_count = math.ceil(file_size / PART_SIZE_BYTES)
    print(f"File size: {file_size / (1024**2):.1f} MB — {part_count} parts of {PART_SIZE_BYTES // (1024**2)} MB each")

    resp = s3_client.create_multipart_upload(Bucket=bucket, Key=s3_key)
    upload_id = resp["UploadId"]
    print(f"Multipart upload initiated. UploadId: {upload_id}")

    part_urls = [
        s3_client.generate_presigned_url(
            "upload_part",
            Params={"Bucket": bucket, "Key": s3_key, "UploadId": upload_id, "PartNumber": n},
            ExpiresIn=URL_TIMEOUT,
        )
        for n in range(1, part_count + 1)
    ]
    complete_url = s3_client.generate_presigned_url(
        "complete_multipart_upload",
        Params={"Bucket": bucket, "Key": s3_key, "UploadId": upload_id},
        ExpiresIn=URL_TIMEOUT,
    )
    abort_url = s3_client.generate_presigned_url(
        "abort_multipart_upload",
        Params={"Bucket": bucket, "Key": s3_key, "UploadId": upload_id},
        ExpiresIn=URL_TIMEOUT,
    )
    return {
        "partUrls": part_urls,
        "completeUrl": complete_url,
        "abortUrl": abort_url,
        "partSizeBytes": PART_SIZE_BYTES,
    }


env = load_env(root_env)
GRAPHQL_ENDPOINT = env["dev_api_endpoint"]
GRAPHQL_API_KEY = env["dev_api_key"]

file_name = "2026-04-11T04_40_00_TILL_2026-04-11T04_44_00.mkv"

mutation = """
    mutation CREATE_PRE_SIGNED_URL($file_type: String!, $filename: String!, $locationID: String!, $timeout: Int!) {
        createPreSignedURL(
            file_type: $file_type
            filename: $filename
            locationID: $locationID
            timeout: $timeout
        )
    }
"""

payload = json.dumps(
    {
        "query": mutation,
        "variables": {
            "file_type": FILE_TYPE,
            "filename": file_name,
            "locationID": LOCATION_ID,
            "timeout": URL_TIMEOUT,
        },
    }
).encode("utf-8")

req = urllib.request.Request(
    GRAPHQL_ENDPOINT,
    data=payload,
    headers={
        "Content-Type": "application/json",
        "x-api-key": GRAPHQL_API_KEY,
    },
    method="POST",
)

print(f"Requesting presigned URL via GraphQL for: {file_name}")
with urllib.request.urlopen(req) as resp:
    raw = resp.read().decode("utf-8")

print("Raw GraphQL response:", raw)
body = json.loads(raw)

if "errors" in body:
    raise RuntimeError("GraphQL errors: " + json.dumps(body["errors"], indent=2))

raw_result = body["data"]["createPreSignedURL"]
if not raw_result:
    raise RuntimeError("No presigned URL in GraphQL response: " + raw)

# AppSync serializes the Lambda response object as a Groovy-style string:
# "{statusCode=200, body=https://...}" — extract just the URL after "body="
if raw_result.startswith("{") and "body=" in raw_result:
    idx = raw_result.index("body=") + len("body=")
    url = raw_result[idx:].rstrip("}")
else:
    url = raw_result

print("Presigned URL obtained.")

bucket, region, s3_key, use_accelerate = parse_presigned_url(url)
effective_region = region or env.get("aws_region", "eu-west-2")
print(f"Bucket: {bucket}, region: {effective_region}, key: {s3_key}, accelerate: {use_accelerate}")

aws_profile = os.getenv("AWS_PROFILE")
session = (
    boto3.Session(profile_name=aws_profile, region_name=effective_region)
    if aws_profile
    else boto3.Session(region_name=effective_region)
)
s3_config = Config(s3={"use_accelerate_endpoint": True}) if use_accelerate else None
s3_client = session.client("s3", config=s3_config)

print("\nPre-generating multipart presigned URLs...")
mp_config = build_multipart_config(s3_client, bucket, s3_key, video_path)

# --- Standard PUT ---
# print("\n--- Standard PUT Upload ---")
# start_put = time.monotonic()
# result = subprocess.run(
#     ["pwsh", "-File", str(ps_script), "-PresignedUrl", url, "-FilePath", str(video_path)],
#     capture_output=False,
# )
# put_ms = (time.monotonic() - start_put) * 1000
# print(f"Standard PUT took {put_ms:.2f} ms")

# if result.returncode != 0:
#     raise RuntimeError(f"PowerShell script failed with exit code {result.returncode}")

# --- Multi-Part Upload ---
print("\n--- Multi-Part Upload ---")
with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
    json.dump(mp_config, tmp)
    tmp_path = tmp.name

try:
    start_mp = time.monotonic()
    result_mp = subprocess.run(
        ["pwsh", "-File", str(ps_script), "-MultipartConfigPath", tmp_path, "-FilePath", str(video_path)],
        capture_output=False,
    )
finally:
    os.unlink(tmp_path)

mp_ms = (time.monotonic() - start_mp) * 1000
print(f"Multi-part upload took {mp_ms:.2f} ms")

if result_mp.returncode != 0:
    raise RuntimeError(f"Multi-part PowerShell script failed with exit code {result_mp.returncode}")

# --- Comparison ---
print("\n" + "=" * 50)
print("UPLOAD TIMING COMPARISON")
print("=" * 50)
# print(f"  Standard PUT:       {put_ms:>10.2f} ms  ({put_ms/1000:.2f} s)")
print(f"  Multi-part upload:  {mp_ms:>10.2f} ms  ({mp_ms/1000:.2f} s)")
# diff = put_ms - mp_ms
# if diff > 0:
    # print(f"  Multi-part FASTER by {diff:.2f} ms ({put_ms/mp_ms:.2f}x)")
# else:
    # print(f"  Standard PUT FASTER by {abs(diff):.2f} ms ({mp_ms/put_ms:.2f}x slower for multi-part)")
# print("=" * 50)
print("Done.")
