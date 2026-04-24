import json
import subprocess
import urllib.request
from pathlib import Path

LOCATION_ID = "98d2ca8c-73c2-4110-99cf-c6d2b24ec9bb"
URL_TIMEOUT = 14400
FILE_TYPE = "real-time"

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
print(f"Invoking PowerShell upload script...")

result = subprocess.run(
    [
        "pwsh",
        "-File",
        str(ps_script),
        "-PresignedUrl",
        url,
        "-FilePath",
        str(video_path),
    ],
    capture_output=False,
)

if result.returncode != 0:
    raise RuntimeError(f"PowerShell script failed with exit code {result.returncode}")

print("Done.")
