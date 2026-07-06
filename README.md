# SearchUI

SearchUI is a full-stack search interface application. The project features a robust Python backend built to handle asynchronous tasks, vector-based indexing, and a modular plugin architecture, paired with a lightweight HTML frontend.

## 🚀 Features

*   **Vector Search Capabilities:** Integrates vector indexing (`vector_index.py`) for advanced, semantic search functionalities.
*   **Asynchronous Processing:** Utilizes Celery (`celery_app.py`) for managing background tasks and search execution.
*   **Modular Plugin System:** Easily extend search capabilities using the built-in plugin loader (`plugins_loader.py`). Includes examples like the `anysearch_plugin`.
*   **Real-Time Communication:** Supports WebSocket connections for real-time frontend-backend interaction.
*   **Secure Vault:** Manages secrets and sensitive configurations via `vault.py`.
*   **Caching:** Built-in caching mechanisms (`cache.py`) to optimize search query performance.

## 📁 Project Structure

```text
SearchUI/
├── .gitignore
├── backend/
│   ├── cache.py                 # Caching logic
│   ├── celery_app.py            # Celery task queue configuration
│   ├── executor.py              # Search execution logic
│   ├── main.py                  # Main application entry point (e.g., FastAPI/Flask)
│   ├── plugins_loader.py        # Dynamic plugin loading system
│   ├── requirements.txt         # Backend Python dependencies
│   ├── settings.py              # Application configuration
│   ├── vault.py                 # Secrets and credentials management
│   ├── vector_index.py          # Vector database integration
│   ├── plugins/                 # Custom search plugins
│   │   ├── anysearch_plugin.py
│   │   └── example_plugin.py
│   └── test_*.py                # Integration, phase, and websocket test files
└── frontend/
    └── index.html               # Main frontend user interface

```

# 🛠️ Prerequisites
## Python 3.8+

A message broker for Celery (e.g., Redis or RabbitMQ)

(Optional) Vector database backend depending on your vector_index.py setup

# ⚙️ Installation & Setup
## Clone the repository:

```text
git clone <your-repo-url>
cd SearchUI
Set up the Python backend:
Navigate to the backend directory and install the required dependencies.
```

```text
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

# Configure the environment:
## Review settings.py and vault.py to configure your environment variables, API keys, and database connections.

## Run the Celery Worker:
In a new terminal instance, start the Celery worker to handle background tasks.

```text
cd backend
celery -A celery_app worker --loglevel=info
Start the Backend Server:
Run your main application (assuming a standard ASGI/WSGI setup in main.py).
```

```text
python main.py
```
# Launch the Frontend:
Serve the frontend/index.html file using a simple HTTP server or open it directly in your browser.

```text
cd ../frontend
python -m http.server 8000
```
Navigate to http://localhost:8000 in your web browser.

# 🧪 Testing
The project includes an extensive test suite broken down into phases. Run the tests from the backend directory:

```text
pytest test_integration.py test_phase2.py test_phase3.py test_phase4.py test_ws.py
```
 # 🧩 Creating Plugins
 To add a new search plugin, create a new Python file in the backend/plugins/ directory following the structure of example_plugin.py. The plugins_loader.py will automatically detect and integrate it into the search executor.
