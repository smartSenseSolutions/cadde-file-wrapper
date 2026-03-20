import csv
import io
import os
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI(title="CADDE File Wrapper")

# Config from environment variables (populated via Helm values → ConfigMap)
CADDE_TOKEN_URL = os.environ["CADDE_TOKEN_URL"]
CADDE_FILE_URL = os.environ["CADDE_FILE_URL"]
CADDE_RESOURCE_BASE_URL = os.environ["CADDE_RESOURCE_BASE_URL"]  # e.g. http://data-management.koshizukalab.internal:8080
CADDE_RESOURCE_API_TYPE = os.environ["CADDE_RESOURCE_API_TYPE"]
CADDE_PROVIDER = os.environ["CADDE_PROVIDER"]
CADDE_AUTH_BASIC = os.environ["CADDE_AUTH_BASIC"]
CADDE_USER_ID = os.environ["CADDE_USER_ID"]
CADDE_PASSWORD = os.environ["CADDE_PASSWORD"]


def get_cadde_token() -> str:
    response = requests.post(
        CADDE_TOKEN_URL,
        headers={
            "Authorization": CADDE_AUTH_BASIC,
            "Content-Type": "application/json",
        },
        json={"user_id": CADDE_USER_ID, "password": CADDE_PASSWORD},
        verify=False,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def fetch_csv_from_cadde(token: str, resource_url: str) -> str:
    response = requests.get(
        CADDE_FILE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "x-cadde-resource-url": resource_url,
            "x-cadde-resource-api-type": CADDE_RESOURCE_API_TYPE,
            "x-cadde-provider": CADDE_PROVIDER,
        },
        verify=False,
    )
    response.raise_for_status()
    return response.text


def csv_to_json(csv_text: str) -> list:
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    return [row for row in reader]


@app.get("/file-as-json/{filename}")
def file_as_json(filename: str):
    if not filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported")
    resource_url = f"{CADDE_RESOURCE_BASE_URL.rstrip('/')}/{filename}"
    try:
        token = get_cadde_token()
        csv_text = fetch_csv_from_cadde(token, resource_url)
        data = csv_to_json(csv_text)
        return JSONResponse(content=data)
    except requests.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"CADDE error: {e.response.status_code} {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok"}
