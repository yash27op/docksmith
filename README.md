# Docksmith

**Local LLM Dockerfile generation with Python, Hugging Face GGUF models, Ollama, and Docker.**

Describe your application and paste dependency details. Docksmith returns a Dockerfile, `.dockerignore`, an explanation, advisory checks, and a downloadable ZIP. The browser interface includes a clearly labeled static demo so you can explore without downloading a model.

## What each technology does

| Component | Role in this project |
| --- | --- |
| Python | Serves the interface, sends generation requests, validates JSON, and creates ZIP downloads. |
| Hugging Face | Hosts the downloadable model weights. It does not receive your project prompt in the default setup. |
| GGUF | The model file format used by this local inference workflow. |
| Ollama | Downloads the model and runs it on your machine through an HTTP API. |
| Docker | Packages Docksmith; Compose can also run a separate Ollama service. |

Two different Dockerfiles are involved: the repository's `Dockerfile` packages **Docksmith itself**; the Dockerfile shown in the interface packages **the application you describe**.

## A generation, step by step

1. Enter your application's language, runtime version, entry point, port, and dependencies.
2. The browser sends that text to the Python endpoint `/api/generate`.
3. Python adds container-generation instructions and calls Ollama's `/api/generate` endpoint.
4. Ollama runs the installed model and returns JSON containing the three output fields.
5. Python validates those fields and applies basic Dockerfile checks.
6. The browser displays the files. Download the bundle, review it, then place the container files beside your application source.

Docksmith does not automatically read your repository, create an image, or run your generated application.

## Repository map

```text
app.py                 HTTP routes, request limits, ZIP downloads
core.py                Prompt, Ollama client, response validation, checks
static/                Browser interface: HTML, CSS, JavaScript
Dockerfile             Container image for Docksmith
compose.yaml           Docksmith and Ollama services + model volume
tests/test_app.py      Unit and HTTP integration tests
.github/workflows/     Automated tests and image build
```

Read `core.py` first to understand the LLM flow, then `app.py` for the API and `static/app.js` for the interface.

## Architecture

```text
Browser → Python HTTP server → Ollama /api/generate → local GGUF model
              ↓                     ↑
      JSON validation       model downloaded from Hugging Face
      advisory checks
      in-memory ZIP export
```

Hugging Face provides model weights; Ollama loads and runs them. Python orchestrates prompts and validates the response. Docker packages the app and, optionally, Ollama. There is no hosted inference API, API key requirement, project upload, or Docker socket mount. The server uses only Python's standard library.

## Quick start: demo without a model

Requires Python 3.11+:

```sh
git clone https://github.com/yash27op/docksmith.git
cd docksmith
python3 app.py
```

Open [localhost:8000](http://localhost:8000) and select **Explore a fixed FastAPI demo**. The demo is a fixed example and does not adapt to your input.

## Local inference

Install Ollama from [ollama.com](https://ollama.com/download), then start its app/service. If running the CLI manually, use `ollama serve` in a separate terminal.

```sh
ollama pull hf.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF:Q4_K_M
python3 app.py
```

The default is a compact coding model intended for experimentation. Quality depends on the model and prompt; stronger coding models can improve results but need more memory. The initial model download requires internet and disk space. Once downloaded, inference uses your local Ollama service. Check the model card for license and hardware requirements.

To use another installed Ollama-compatible GGUF model:

```sh
OLLAMA_MODEL='your-installed-model' python3 app.py
```

The manifest field should include its filename, for example:

```text
requirements.txt:
fastapi==0.115.0
uvicorn==0.30.6
```

Describe the runtime version, source entry point, exported app, port, dependency command, and any build step. For Node projects mention whether a lockfile exists. Docksmith does not inspect your filesystem, so missing details become model assumptions.

## Docker Compose: app + local model service

```sh
docker compose up -d --build
docker compose exec ollama ollama pull hf.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF:Q4_K_M
```

Then open [localhost:8000](http://localhost:8000). Model weights persist in the `models` named volume. The Ollama port is only available inside the Compose network. Containerized Ollama runs on CPU with this configuration; on Apple Silicon, native Ollama generally offers a better route to GPU acceleration.

```sh
docker compose logs -f web
docker compose down
```

The Ollama image uses `latest` for a straightforward learning setup; pin a tested release or image digest for reproducibility. The app base image has a Python version tag but is not digest-pinned either.

### Docker app with native Ollama

```sh
docker build -t docksmith .
docker run --rm -p 127.0.0.1:8000:8000 \
  --add-host=host.docker.internal:host-gateway \
  -e OLLAMA_URL=http://host.docker.internal:11434 docksmith
```

Native Ollama must be reachable from the container. A loopback-only Ollama binding may reject that connection; use the Compose setup if you do not want to configure host networking. Do not expose an unauthenticated Ollama service to an untrusted network.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Demo works, generation fails | Start Ollama and pull the exact configured model. The demo never calls Ollama. |
| Ollama HTTP 404 | The model name may not match an installed model; check `ollama list`. |
| Connection refused | For native Python use localhost; inside Compose use `http://ollama:11434`. |
| Generation takes too long | CPU inference can be slow. Use a smaller model or native hardware acceleration. |
| Invalid model JSON | Retry with more explicit context or a stronger coding model. |
| Port 8000 is busy | Stop the other service, or set `PORT=8001` for native Python. Compose port changes require editing its port mapping. |

## Configuration

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Inference endpoint; Compose overrides it |
| `OLLAMA_MODEL` | `hf.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF:Q4_K_M` | Already-downloaded model |
| `APP_HOST` | `127.0.0.1` | Server binding; image uses `0.0.0.0` |
| `PORT` | `8000` | Web server port |

Python does not load `.env` automatically. Export variables in your shell. Compose reads `.env` for model interpolation; copy `.env.example` if needed.

## API

```sh
curl http://localhost:8000/api/generate \
  -H 'Content-Type: application/json' \
  -d '{"description":"Python 3.13 FastAPI app in main.py, port 8000, requirements.txt includes uvicorn", "manifest":"requirements.txt: fastapi, uvicorn"}'
```

- `POST /api/generate`: returns `dockerfile`, `dockerignore`, `explanation`, `warnings`, `model`, and `demo: false`.
- `POST /api/demo` with `{}`: fixed sample, `demo: true`.
- `POST /api/download`: accepts the three output text fields and returns a ZIP with fixed filenames.
- `GET /api/health`: application liveness only; does not verify model availability.

One generation runs at a time. Additional generation requests receive 429. Model requests time out after 180 seconds. Invalid input receives 400, oversized bodies 413, and inference failures 502. A failed model call never silently returns a demo.

## Tests

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q app.py core.py tests
docker compose config --quiet
```

Tests cover validation, malformed model output, final-stage lint checks, an actual HTTP call to a fake Ollama server, connection failure, ZIP contents, and static-file isolation. The fake server checks the integration contract; it does not evaluate model quality. GitHub Actions runs Python tests and builds the application image.

## Design boundaries

Generated Dockerfiles are untrusted drafts. Nothing is built or executed automatically. Review commands, dependencies, base images, file paths, and application behavior before using the output. Linting is deliberately heuristic, not a full Dockerfile parser or vulnerability scan; a clean result is not proof of safety or a successful build. The app does not train or fine-tune a model.

This is a localhost portfolio/learning service using Python's development-oriented HTTP server, without authentication or production traffic controls. Do not expose it publicly. Inputs and outputs are not saved by the app; Ollama handles inference context according to its configuration. Do not paste secrets. Changing `OLLAMA_URL` to a remote endpoint sends the entered context there. Initial image/model pulls contact their registries.

## Make it a stronger portfolio project

1. Add a CLI that scans an allowlist of manifests while excluding secrets and large files.
2. Build a fixture set for Python, Go, and Node; measure valid Dockerfile rate across models.
3. Add optional Hadolint checks in an isolated tool container and distinguish parser failures from warnings.
4. Add a reviewer-approved build workflow with ephemeral isolation, resource limits, and no host Docker socket exposed to generated code.
5. Add model comparison metrics: time, token count, memory use, and human review scores.

## References

- [Ollama generate API](https://docs.ollama.com/api/generate)
- [Run Hugging Face GGUF models with Ollama](https://huggingface.co/docs/hub/ollama)
- [Default model card](https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF)

Source code is provided under the MIT license. Model weights and container images retain their own licenses.
