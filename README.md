# CADDE File Wrapper — Submodel Server

A lightweight FastAPI microservice that serves as the **Submodel Server** within the JP-EDC (Japan Bridge Ecosystem) of the EDC-CADDE Interoperability Architecture. It fetches raw CSV files from CADDE data sources, transforms them into standard JSON, and exposes them as a clean REST API consumable by the Eclipse Dataspace Connector (EDC) data plane.

---

## Architecture Overview

This service sits inside the **Data Transformation & Management Layer** of the JP-EDC connector bridge, which enables EU-based data consumers to access CADDE-native assets using standard EDC protocols.

```
EU Ecosystem (EDC-based)                   Japan Bridge Ecosystem (CADDE-based)
─────────────────────────    ──────────────────────────────────────────────────────
                             Interoperability Bridge (JP-EDC)
EU Data Consumer             ┌────────────────────────────────────────────────────┐
    │                        │  Control Plane                                     │
    │ 1. Control Plane       │  ┌──────────────────────────────────┐              │
    │    Negotiation ──────► │  │ EDC Consumer Bridge (JP-EDC)     │              │
    │                        │  └──────────────────────────────────┘              │
    │ 2. Data Plane          │                                                    │
    │    Transfer ─────────► │  Data Transformation & Management Layer            │
    │                        │  ┌──────────────────────────────────────────────┐  │
    │                        │  │  ** Submodel Server (THIS REPO) **           │  │
    │                        │  │  - Authenticates with CADDE                  │  │
    │                        │  │  - Fetches raw CSV from Japan Connector      │  │
    │                        │  │  - Transforms CSV → JSON                     │  │
    │                        │  └──────────────────────────────────────────────┘  │
    │                        └────────────────────────────────────────────────────┘
    │                                        │
    │                                        ▼
    │                         Japan Connector (CADDE-native)
    │                         ┌────────────────────────────┐
    │                         │  CADDE Assets / Databases  │
    │                         │  (CSV / XML files)         │
    │                         └────────────────────────────┘
    │
    ◄── 6. Direct JSON Response (transformed, EDC-compatible)
```

### Where This Service Fits

| Step | Actor | Action |
|------|-------|--------|
| 1 | EU-EDC ↔ JP-EDC | Control Plane negotiation & token exchange |
| 2 | EU-EDC Data Plane | Consumer direct pull via JP-EDC endpoint |
| 3 | JP-EDC | Forwards data transfer request to Submodel Server |
| 4 | **Submodel Server** | **Authenticates with CADDE, fetches raw CSV data** |
| 5 | **Submodel Server** | **Transforms raw CSV/XML → standard JSON** |
| 6 | JP-EDC → EU Consumer | Returns clean JSON response to EU Data Plane |

---

## Business Flow

1. **EU Data Consumer** initiates a data request through its EDC (Eclipse Dataspace Connector).
2. **JP-EDC** (the bridge) completes control-plane negotiation and provides the EU side with a data endpoint URL and access token.
3. The EU consumer's **Data Plane** makes a direct pull request to the JP-EDC data endpoint.
4. JP-EDC routes the request to this **Submodel Server**, which:
   - Obtains a CADDE authentication token using pre-configured service credentials.
   - Calls the CADDE file endpoint with the appropriate resource URL and CADDE-specific headers.
   - Receives the raw CSV file from the **Japan Connector** (CADDE-native backend).
5. The Submodel Server **transforms the CSV into a JSON array** of structured records.
6. The resulting JSON is returned through JP-EDC back to the EU consumer's Data Lake or application — no CADDE-specific tooling required on the EU side.

This design enables CADDE-native data assets to be accessed as standard EDC-compatible JSON without any modification to existing CADDE infrastructure.

---

## Technical Details

### Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11 |
| Web Framework | FastAPI 0.111.0 |
| ASGI Server | Uvicorn 0.29.0 |
| HTTP Client | Requests 2.31.0 |
| Containerization | Docker (python:3.11-slim) |
| Orchestration | Kubernetes + Helm |
| Ingress | NGINX Ingress Controller |

### Project Structure

```
cadde-file-wrapper/
├── main.py                          # Core FastAPI application
├── requirements.txt                 # Python dependencies
├── Dockerfile                       # Container image definition
└── helm/
    └── cadde-file-wrapper/
        ├── Chart.yaml               # Helm chart metadata
        ├── values.yaml              # Deployment configuration & defaults
        └── templates/
            ├── _helpers.tpl         # Helm template helpers
            ├── deployment.yaml      # Kubernetes Deployment
            ├── service.yaml         # Kubernetes ClusterIP Service
            ├── ingress.yaml         # NGINX Ingress with optional TLS/HAProxy
            ├── configmap.yaml       # Non-sensitive environment config
            └── secret.yaml          # Sensitive credentials (auth, password)
```

---

## API Reference

### `GET /file-as-json/{filename}`

Fetches a CADDE CSV file and returns it as a JSON array.

**Path Parameter**

| Parameter | Type | Description |
|-----------|------|-------------|
| `filename` | string | Name of the CSV file to retrieve (must end with `.csv`) |

**Response — 200 OK**

```json
[
  { "column1": "value1", "column2": "value2" },
  { "column1": "value3", "column2": "value4" }
]
```

**Error Responses**

| Status | Condition |
|--------|-----------|
| 400 | Filename does not end with `.csv` |
| 502 | CADDE upstream service returned an error |
| 500 | Internal server error during processing |

**Example**

```bash
curl http://cadde-wrapper.tx.the-sense.io/file-as-json/sensor_data.csv
```

---

### `GET /health`

Health check endpoint used by Kubernetes liveness probes.

**Response — 200 OK**

```json
{ "status": "ok" }
```

---

## Internal Request Flow

```
Client: GET /file-as-json/sensor_data.csv
    │
    ▼
[1] Validate: filename ends with .csv
    │
    ▼
[2] Build resource URL:
    {CADDE_RESOURCE_BASE_URL}/sensor_data.csv
    │
    ▼
[3] get_cadde_token()
    POST {CADDE_TOKEN_URL}
    Headers: Authorization: Basic {CADDE_AUTH_BASIC}
    Body: { user_id, password }
    → Returns: access_token
    │
    ▼
[4] fetch_csv_from_cadde(token, resource_url)
    GET {CADDE_FILE_URL}
    Headers:
      Authorization: Bearer {access_token}
      x-cadde-resource-url: {resource_url}
      x-cadde-resource-api-type: file/http
      x-cadde-provider: {CADDE_PROVIDER}
    → Returns: raw CSV text
    │
    ▼
[5] csv_to_json(csv_text)
    Parse via csv.DictReader
    Handle BOM characters
    → Returns: list of dicts (JSON-serializable)
    │
    ▼
[6] JSONResponse → Client
```

---

## Configuration

All configuration is supplied via environment variables, managed in Kubernetes through a **ConfigMap** (non-sensitive) and a **Secret** (sensitive).

### Environment Variables

| Variable | Source | Description |
|----------|--------|-------------|
| `CADDE_TOKEN_URL` | ConfigMap | CADDE authentication endpoint URL |
| `CADDE_FILE_URL` | ConfigMap | CADDE file retrieval endpoint URL |
| `CADDE_RESOURCE_BASE_URL` | ConfigMap | Base URL for constructing resource paths |
| `CADDE_RESOURCE_API_TYPE` | ConfigMap | CADDE API type identifier (e.g. `file/http`) |
| `CADDE_PROVIDER` | ConfigMap | CADDE provider identifier |
| `CADDE_USER_ID` | ConfigMap | CADDE user/consumer identifier |
| `CADDE_AUTH_BASIC` | Secret | Base64-encoded Basic auth credentials for token endpoint |
| `CADDE_PASSWORD` | Secret | Password for CADDE user authentication |

---

## Deployment

### Prerequisites

- Kubernetes cluster with NGINX Ingress Controller
- Helm 3.x
- Access to the container registry: `public.ecr.aws/smartsensesolutions/eu-jap-hack/cadde-file-wrapper`

### Install with Helm

```bash
helm install cadde-file-wrapper ./helm/cadde-file-wrapper \
  --set env.CADDE_AUTH_BASIC=<base64-encoded-credentials> \
  --set env.CADDE_PASSWORD=<cadde-password> \
  --set replicaCount=1
```

### Upgrade

```bash
helm upgrade cadde-file-wrapper ./helm/cadde-file-wrapper
```

### Uninstall

```bash
helm uninstall cadde-file-wrapper
```

### Ingress

Once deployed, the service is externally accessible at:

```
http://cadde-wrapper.tx.the-sense.io
```

TLS can be enabled in `values.yaml` by setting `ingress.tls.enabled: true` and providing a certificate via cert-manager.

---

## Local Development

### Run with Python

```bash
pip install -r requirements.txt

export CADDE_TOKEN_URL=https://...
export CADDE_FILE_URL=https://...
export CADDE_RESOURCE_BASE_URL=http://...
export CADDE_RESOURCE_API_TYPE=file/http
export CADDE_PROVIDER=0003-koshizukalab
export CADDE_USER_ID=0001-hackathon
export CADDE_AUTH_BASIC=<base64-credentials>
export CADDE_PASSWORD=<password>

uvicorn main:app --host 0.0.0.0 --port 8000
```

### Run with Docker

```bash
docker build -t cadde-file-wrapper .

docker run -p 8000:8000 \
  -e CADDE_TOKEN_URL=https://... \
  -e CADDE_FILE_URL=https://... \
  -e CADDE_RESOURCE_BASE_URL=http://... \
  -e CADDE_RESOURCE_API_TYPE=file/http \
  -e CADDE_PROVIDER=0003-koshizukalab \
  -e CADDE_USER_ID=0001-hackathon \
  -e CADDE_AUTH_BASIC=<base64-credentials> \
  -e CADDE_PASSWORD=<password> \
  cadde-file-wrapper
```

---

## Security Notes

- SSL certificate verification is currently disabled (`verify=False`) for CADDE endpoints — acceptable in isolated internal networks but should be addressed in production by providing trusted CA certificates.
- The wrapper API itself relies on network-level access control (ClusterIP + Ingress) rather than application-level authentication. Add an API key or token layer if exposing beyond the trusted cluster.
- Sensitive credentials (`CADDE_AUTH_BASIC`, `CADDE_PASSWORD`) should be managed through an external secrets manager (e.g., HashiCorp Vault, AWS Secrets Manager) rather than stored directly in `values.yaml` for production use.

---

## Related Components

| Component | Role |
|-----------|------|
| JP-EDC (Eclipse Dataspace Connector) | Acts as the interoperability bridge; routes data plane requests to this service |
| CADDE Authentication Service | Issues access tokens for CADDE resource access |
| CADDE File Service | Delivers raw CSV/file assets |
| Japan Connector (CADDE-native) | Native CADDE connector managing access to CADDE assets and databases |
| EU-EDC | EU-side Eclipse Dataspace Connector initiating data consumption |
