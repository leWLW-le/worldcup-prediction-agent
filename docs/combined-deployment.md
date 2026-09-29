# Combined free deployment

The existing Streamlit service can host the API in the same Python process.
Set `COMBINED_SERVICE=true`. On the first dashboard API call, a process-wide
cached resource starts Uvicorn on `127.0.0.1:8765` and waits for application
startup. Browser sessions share the backend, model registry, job limits and
provider caches. Only Streamlit's public port is exposed.

In this mode, `BACKEND_URL` is ignored, and loopback requests do not use proxy
environment variables. No request from the dashboard to the API crosses the
public Render/Cloudflare boundary. Authentication remains enabled: configure
the same private value in `ADMIN_API_KEY` and `BACKEND_API_KEY` on the Streamlit
service. Also configure the existing LLM and football-provider credentials on
that service. Secrets must not be committed to the repository.

Use the existing full `requirements.txt` build and Streamlit start command.
Set `MODEL_BUNDLE_DIR=models/production-v2`, `SEED_RELEASE=true`,
`AUTO_REFRESH_DATA=true`, and `COMPUTE_TIMEOUT_SECONDS=600`. Limit numerical
library threads with `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, and
`MKL_NUM_THREADS=1` for the shared free CPU.

The free service uses local SQLite. Its writable filesystem is ephemeral;
redeploying restores the published pre-tournament snapshot and re-fetches
provider results, but does not migrate the old backend's historical user runs.
The original separate backend is retained, and is no longer the website's
data store in combined mode. Switch `COMBINED_SERVICE=false` to restore the
separate-service path. This does not provide durable storage or avoid Render
free-service sleep limits.
