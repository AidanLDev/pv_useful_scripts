import json
import os
import subprocess
from pathlib import Path
import boto3

LOCATION_ID = "98d2ca8c-73c2-4110-99cf-c6d2b24ec9bb"
MAC_ADDRESS = "00:1A:2B:3C:4D:5E"
GET_S3_PRESIGNED_LAMBDA_ARN = (
    "arn:aws:lambda:eu-west-2:705827784156:function:LineVuPortalIotGetS3Presigned-dev"
)
REGION = "eu-west-2"

video_path = Path(__file__).parent / "2026-04-11T04_40_00_TILL_2026-04-11T04_44_00.mkv"
ps_script = Path(__file__).parent / "upload_to_s3.ps1"

if not video_path.exists():
    raise FileNotFoundError(f"Video file not found: {video_path}")

key_name = video_path.name
payload = {"mac_address": MAC_ADDRESS, "key_name": key_name}

aws_profile = os.getenv("AWS_PROFILE")
if aws_profile:
    session = boto3.Session(profile_name=aws_profile, region_name=REGION)
else:
    session = boto3.Session(region_name=REGION)

lambda_client = session.client("lambda")

print(f"Invoking Lambda for key: {key_name}")
resp = lambda_client.invoke(
    FunctionName=GET_S3_PRESIGNED_LAMBDA_ARN,
    InvocationType="RequestResponse",
    Payload=json.dumps(payload).encode("utf-8"),
)

raw = resp["Payload"].read().decode("utf-8")
print("Raw Lambda response:", raw)
outer = json.loads(raw)
body = outer.get("body")

body_obj = {}
if isinstance(body, dict):
    body_obj = body
elif isinstance(body, str):
    try:
        parsed_body = json.loads(body)
        body_obj = parsed_body if isinstance(parsed_body, dict) else {"message": str(parsed_body)}
    except json.JSONDecodeError:
        body_obj = {"message": body}

url = body_obj.get("url")
if not url:
    raise RuntimeError("No presigned URL in Lambda response. Body was: " + str(body_obj))

print(f"\nPresigned URL obtained.")
print(f"Invoking PowerShell upload script...")

result = subprocess.run(
    ["pwsh", "-File", str(ps_script), "-PresignedUrl", url, "-FilePath", str(video_path)],
    capture_output=False,
)

if result.returncode != 0:
    raise RuntimeError(f"PowerShell script failed with exit code {result.returncode}")

print("Done.")
