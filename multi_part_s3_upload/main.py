import json
import os
import time
from pathlib import Path
import boto3
import requests

LOCATION_ID = "98d2ca8c-73c2-4110-99cf-c6d2b24ec9bb"
MAC_ADDRESS = "00:1A:2B:3C:4D:5E"
DEV_S3_URL = "s3://linevuportal-storage-de92845c112918-dev/public/98d2ca8c-73c2-4110-99cf-c6d2b24ec9bb/linevu-images/"
GET_S3_PRESIGNED_LAMBDA_ARN = (
    "arn:aws:lambda:eu-west-2:705827784156:function:LineVuPortalIotGetS3Presigned-dev"
)
REGION = "eu-west-2"

image_path = Path("2025-03-06T12_06_03_00_1A_2B_3C_4D_5E.png")
key_name = image_path.name

payload = {"mac_address": MAC_ADDRESS, "key_name": key_name}

aws_profile = os.getenv("AWS_PROFILE")
if aws_profile:
    session = boto3.Session(profile_name=aws_profile, region_name=REGION)
else:
    session = boto3.Session(region_name=REGION)

lambda_client = session.client("lambda")

resp = lambda_client.invoke(
    FunctionName=GET_S3_PRESIGNED_LAMBDA_ARN,
    InvocationType="RequestResponse",
    Payload=json.dumps(payload).encode("utf-8"),
)

raw = resp["Payload"].read().decode("utf-8")
print("Raw response from Lambda: ", raw)
outer = json.loads(raw)
body = outer.get("body")

body_obj = {}
if isinstance(body, dict):
    body_obj = body
elif isinstance(body, str):
    try:
        parsed_body = json.loads(body)
        if isinstance(parsed_body, dict):
            body_obj = parsed_body
        else:
            body_obj = {"message": str(parsed_body)}
    except json.JSONDecodeError:
        body_obj = {"message": body}

url = body_obj.get("url")

if not url:
    raise RuntimeError(
        "No presigned URL found in Lambda response. "
        "Current Lambda body was: " + str(body_obj)
    )


def uploadUsingStandardPut(url):
    with image_path.open("rb") as f:
        return requests.put(
            url,
            data=f,
            headers={
                "Content-Type": "image/png",
                "x-amz-tagging": "docType=camera_image",
            },
            timeout=30,
        )


start_time = time.monotonic()
standard_put_resp = uploadUsingStandardPut(url)
elapsed_time = time.monotonic() - start_time
elapsed_ms = elapsed_time * 1000

print(f"Upload took {elapsed_ms:.2f} ms")
print("PUT status code: ", standard_put_resp.status_code)
print("PUT response: ", standard_put_resp.text[:300])
standard_put_resp.raise_for_status()
print("Upload successful!")
