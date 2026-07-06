import json
import os
import shutil
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from executor import GraphExecutor
from vault import SecretsVault
from celery_app import celery_app, execute_graph_task
import settings as provider_settings

app = FastAPI(title="SearchUI Backend")

# Allow CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup directories
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOAD_DIR = os.path.join(STATIC_DIR, "uploads")

os.makedirs(UPLOAD_DIR, exist_ok=True)

# Serve uploaded files and other static assets
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Secrets Vault Setup & Endpoints
vault = SecretsVault()

class SecretPayload(BaseModel):
    service: str
    value: str

@app.post("/vault/set")
def set_vault_secret(payload: SecretPayload):
    try:
        vault.set_key(payload.service, payload.value)
        return {"status": "success", "message": f"Saved secret for '{payload.service}'"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/vault/list")
def list_vault_secrets():
    try:
        keys = vault.list_keys()
        return {"status": "success", "keys": keys}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# --- LLM Provider Settings Endpoints ---

class ProviderPayload(BaseModel):
    name: str
    base_url: str
    api_key: str = ""
    model: str = ""
    api_style: str = "openai"
    notes: str = ""

class ActiveProviderPayload(BaseModel):
    provider_id: str

@app.get("/settings/known-providers")
def get_known_providers():
    return {"status": "success", "providers": provider_settings.get_known_providers()}

@app.get("/settings/providers")
def list_providers():
    try:
        providers = provider_settings.list_providers()
        data = provider_settings._load()
        return {
            "status": "success",
            "providers": providers,
            "active_provider": data.get("active_provider")
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/settings/providers/{provider_id}")
def save_provider(provider_id: str, payload: ProviderPayload):
    try:
        provider_settings.set_provider(provider_id, payload.dict())
        return {"status": "success", "message": f"Provider '{provider_id}' saved."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.delete("/settings/providers/{provider_id}")
def remove_provider(provider_id: str):
    try:
        provider_settings.delete_provider(provider_id)
        return {"status": "success", "message": f"Provider '{provider_id}' removed."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/settings/active")
def get_active():
    try:
        provider = provider_settings.get_active_provider()
        data = provider_settings._load()
        return {"status": "success", "active_provider": data.get("active_provider"), "config": provider}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.put("/settings/active")
def set_active(payload: ActiveProviderPayload):
    try:
        provider_settings.set_active_provider(payload.provider_id)
        return {"status": "success", "message": f"Active provider set to '{payload.provider_id}'."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/")
def read_root():
    """Serve the main index.html UI when visiting the root URL."""
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"error": "index.html not found"}

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Uploads a file to static/uploads and returns its access URL and local path."""
    try:
        # Prevent path traversal and secure filename
        filename = os.path.basename(file.filename)
        # Unique naming to avoid collisions
        unique_filename = f"{os.urandom(4).hex()}_{filename}"
        file_path = os.path.join(UPLOAD_DIR, unique_filename)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        access_url = f"/static/uploads/{unique_filename}"
        return {
            "status": "success",
            "url": access_url,
            "local_path": file_path,
            "filename": filename
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            try:
                graph_json = json.loads(data)
                
                # Check if Celery worker is active
                worker_online = False
                try:
                    inspector = celery_app.control.inspect(timeout=0.5)
                    stats = inspector.stats()
                    if stats:
                        worker_online = True
                except Exception:
                    pass
                
                # Get the origin URL of the request to map relative media URLs to absolute ones
                host = websocket.headers.get("host", "127.0.0.1:8000")
                scheme = "https" if websocket.url.scheme == "wss" else "http"
                origin = f"{scheme}://{host}"

                if worker_online:
                    # Dispatch execution to Celery background task
                    task = execute_graph_task.delay(graph_json, origin=origin)
                    
                    # Poll task progress and report status updates to frontend
                    while not task.ready():
                        await websocket.send_text(json.dumps({
                            "status": "pending",
                            "message": f"Pipeline task is running in backend worker (Celery task: {task.state})..."
                        }))
                        await asyncio.sleep(0.5)
                    response = task.result
                else:
                    # Fallback to local execution in a background thread to prevent event-loop blocking
                    await websocket.send_text(json.dumps({
                        "status": "pending",
                        "message": "No Celery worker detected. Executing workflow locally..."
                    }))
                    loop = asyncio.get_running_loop()
                    response = await loop.run_in_executor(None, execute_graph_task, graph_json, origin)
                
                if not response:
                    response = {"status": "error", "message": "No result returned from executor"}
                elif not isinstance(response, dict):
                    response = {"status": "success", "result": response}
                    
                await websocket.send_text(json.dumps(response))
                
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"status": "error", "message": "Invalid JSON"}))
            except Exception as e:
                print(f"Execution Error: {e}")
                await websocket.send_text(json.dumps({"status": "error", "message": str(e)}))

    except WebSocketDisconnect:
        print("WebSocket client disconnected")
    except Exception as e:
        print(f"WebSocket connection closed with error: {e}")

if __name__ == "__main__":
    # Use the modern websockets implementation to fix the deprecation warning
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, ws="websockets-sansio")