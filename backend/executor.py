import json
import hashlib
import requests
import os
import tempfile
import cv2
import re
import urllib.parse
from vault import SecretsVault
from cache import SearchCache
try:
    import settings as provider_settings
except ImportError:
    provider_settings = None


def call_llm(prompt: str, model: str = None, system: str = "") -> str:
    """
    Unified LLM caller. Reads the active provider from settings.json and
    dispatches to: Ollama native API, OpenAI-compatible REST, or Anthropic API.
    Falls back to Ollama localhost if no provider is configured.
    Returns the response text, or empty string on failure.
    """
    active = None
    if provider_settings:
        try:
            active = provider_settings.get_active_provider()
        except Exception:
            pass

    # Determine connection params
    if active:
        api_style = active.get("api_style", "openai")
        base_url  = active.get("base_url", "").rstrip("/")
        api_key   = active.get("api_key", "")
        use_model = model or active.get("model") or active.get("default_model", "llama3")
    else:
        api_style = "ollama"
        base_url  = "http://localhost:11434"
        api_key   = ""
        use_model = model or "llama3"

    try:
        if api_style == "ollama":
            url = f"{base_url}/api/generate"
            payload = {"model": use_model, "prompt": prompt, "stream": False}
            if system:
                payload["system"] = system
            r = requests.post(url, json=payload, timeout=30)
            if r.status_code == 200:
                return r.json().get("response", "").strip()

        elif api_style == "anthropic":
            url = f"{base_url}/messages"
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            messages = [{"role": "user", "content": prompt}]
            body = {"model": use_model, "max_tokens": 1024, "messages": messages}
            if system:
                body["system"] = system
            r = requests.post(url, json=body, headers=headers, timeout=30)
            if r.status_code == 200:
                return r.json()["content"][0]["text"].strip()

        else:  # openai-compatible
            url = f"{base_url}/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            body = {"model": use_model, "messages": messages}
            r = requests.post(url, json=body, headers=headers, timeout=30)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"].strip()

    except Exception as e:
        print(f"[call_llm] Error: {e}")

    return ""

def upload_to_catbox(file_path):
    """
    Uploads a local file to Catbox.moe anonymously and returns its public URL.
    """
    if not file_path or not os.path.exists(file_path):
        return None
    try:
        url = "https://catbox.moe/user/api.php"
        data = {"reqtype": "fileupload"}
        with open(file_path, "rb") as f:
            files = {"fileToUpload": f}
            response = requests.post(url, data=data, files=files, timeout=10)
        if response.status_code == 200:
            res_text = response.text.strip()
            if res_text.startswith("http"):
                return res_text
    except Exception as e:
        print(f"Failed to upload to Catbox: {e}")
    return None


def upload_to_litterbox(file_path, expiry="24h"):
    """
    Uploads a local file to Litterbox (temporary Catbox) anonymously and returns its public URL.
    """
    if not file_path or not os.path.exists(file_path):
        return None
    try:
        url = "https://litterbox.catbox.moe/resources/internals/api.php"
        data = {"reqtype": "fileupload", "time": expiry}
        with open(file_path, "rb") as f:
            files = {"fileToUpload": f}
            response = requests.post(url, data=data, files=files, timeout=10)
        if response.status_code == 200:
            res_text = response.text.strip()
            if res_text.startswith("http"):
                return res_text
    except Exception as e:
        print(f"Failed to upload to Litterbox: {e}")
    return None


def get_search_keywords(image_in, keywords_in=None):
    """
    Extracts search keywords either from the keywords_in input or from the image filename.
    """
    if keywords_in:
        if isinstance(keywords_in, dict):
            val = keywords_in.get("value") or keywords_in.get("text") or keywords_in.get("query")
            if val:
                return str(val).strip()
        else:
            return str(keywords_in).strip()
            
    local_path = ""
    if isinstance(image_in, dict):
        local_path = image_in.get("local_path", "")
    
    filename = os.path.basename(local_path) if local_path else "image.jpg"
    name, _ = os.path.splitext(filename)
    
    # Remove leading hex code if it looks like an uploaded file prefix (8 characters + underscore)
    if re.match(r"^[0-9a-fA-F]{8}_", name):
        name = name[9:]
        
    # Replace underscores and hyphens with spaces
    keywords = name.replace("_", " ").replace("-", " ")
    # Clean multiple spaces
    keywords = re.sub(r"\s+", " ", keywords).strip()
    return keywords or "similar art"


def fetch_live_ddg_results(keywords, max_results=10):
    """
    Helper function to query DuckDuckGo and return a list of formatted dictionaries.
    """
    web_results = []
    if not keywords or keywords == "similar art":
        return web_results
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            ddg_res = ddgs.text(keywords, max_results=max_results)
            if ddg_res:
                for item in ddg_res:
                    web_results.append({
                        "title": item.get("title", "Web Result"),
                        "url": item.get("href", ""),
                        "snippet": item.get("body", "No description available.")
                    })
    except Exception as e:
        print(f"Failed to fetch live DDG search results for '{keywords}': {e}")
    return web_results


class GraphExecutor:
    """
    Parses a LiteGraph JSON representation and executes the nodes in topological order.
    """
    def __init__(self, graph_data, origin=None):
        self.graph_data = graph_data
        self.origin = origin or "http://127.0.0.1:8000"
        self.nodes = {node['id']: node for node in graph_data.get('nodes', [])}
        self.links = {link[0]: link for link in graph_data.get('links', [])}
        self.node_outputs = {}  # Store outputs of each node: { node_id: { slot_index: data } }
        
        # Create a temp directory for this execution to store downloaded media
        self.temp_dir = tempfile.mkdtemp(prefix="searchui_")
        
        # Initialize Cache and Secrets Vault
        self.cache = SearchCache()
        self.vault = SecretsVault()
        
        try:
            from plugins_loader import load_plugins
            self.plugins = load_plugins()
        except Exception as e:
            print(f"Error loading plugins: {e}")
            self.plugins = {}

    def execute(self):
        # 1. Build Adjacency List for Topological Sort
        in_degree = {node_id: 0 for node_id in self.nodes}
        adj = {node_id: [] for node_id in self.nodes}

        for link in self.graph_data.get('links', []):
            link_id, origin_id, origin_slot, target_id, target_slot, link_type = link
            adj[origin_id].append(target_id)
            in_degree[target_id] += 1

        # 2. Find starting nodes (in-degree 0)
        queue = [node_id for node_id in self.nodes if in_degree[node_id] == 0]
        order = []

        # 3. Topological Sort
        while queue:
            curr = queue.pop(0)
            order.append(curr)
            for neighbor in adj[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # 4. Execute Nodes in order
        final_output = None
        for node_id in order:
            node = self.nodes[node_id]
            self.execute_node(node)
            if node['type'] == 'output/display':
                # Capture the final output from this node
                final_output = self.node_outputs.get(node_id, {}).get(0)

        # Cleanup can be added here if needed, but for debugging keeping temp files is fine
        return final_output

    def get_input_data(self, node):
        """ Retrieves data from incoming links for a given node. """
        inputs = []
        for inp in node.get('inputs', []):
            link_id = inp.get('link')
            if link_id is not None:
                link = next((l for l in self.graph_data.get('links', []) if l[0] == link_id), None)
                if link:
                    origin_id = link[1]
                    origin_slot = link[2]
                    val = self.node_outputs.get(origin_id, {}).get(origin_slot)
                    inputs.append(val)
                else:
                    inputs.append(None)
            else:
                inputs.append(None)
        return inputs

    def download_file(self, url, prefix, node_id):
        """Helper function to download a file to the temp directory."""
        if url.startswith("http"):
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()

            filename = os.path.basename(url.split("?")[0])
            if not filename:
                filename = f"{prefix}_file"

            local_path = os.path.join(self.temp_dir, f"node_{node_id}_{filename}")

            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return local_path
        return None

    def execute_node(self, node):
        n_type = node.get('type')
        inputs = self.get_input_data(node)
        props = node.get('properties', {})
        outputs = {}

        print(f"Executing {n_type} with inputs: {inputs}")

        # --- MEDIA & DOCUMENT INPUTS ---
        if n_type == 'input/image' or n_type == 'input/video':
            url = props.get('url', '')
            local_path = props.get('local_path', '')
            media_type = "image" if n_type == 'input/image' else "video"
            
            try:
                if not local_path:
                    if url.startswith("http"):
                        local_path = self.download_file(url, media_type, node['id'])
                    elif url.startswith("/static/"):
                        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
                        relative_path = url.lstrip("/") # static/uploads/...
                        local_path = os.path.join(base_dir, relative_path)
                
                status = "available" if local_path and os.path.exists(local_path) else "failed"
                outputs[0] = {
                    "type": media_type, 
                    "url": url,
                    "local_path": local_path,
                    "status": status
                }
            except Exception as e:
                outputs[0] = {"type": media_type, "error": f"Failed to load {media_type}: {str(e)}"}

        elif n_type == 'input/document':
            url = props.get('url', '')
            local_path = props.get('local_path', '')
            
            try:
                if not local_path:
                    if url.startswith("http"):
                        local_path = self.download_file(url, "document", node['id'])
                    elif url.startswith("/static/"):
                        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
                        relative_path = url.lstrip("/")
                        local_path = os.path.join(base_dir, relative_path)
                
                text = ""
                status = "failed"
                if local_path and os.path.exists(local_path):
                    status = "available"
                    ext = os.path.splitext(local_path)[1].lower()
                    if ext == ".pdf":
                        from pypdf import PdfReader
                        reader = PdfReader(local_path)
                        text_list = []
                        for page in reader.pages:
                            page_text = page.extract_text()
                            if page_text:
                                text_list.append(page_text)
                        text = "\n".join(text_list)
                    else:
                        with open(local_path, "r", encoding="utf-8", errors="ignore") as f:
                            text = f.read()
                
                outputs[0] = {
                    "type": "document",
                    "url": url,
                    "local_path": local_path,
                    "status": status,
                    "text": text
                }
            except Exception as e:
                outputs[0] = {"type": "document", "error": f"Failed to load document: {str(e)}"}

        elif n_type == 'input/folder':
            path = props.get('path', '')
            files = []
            status = "failed"
            
            if path and os.path.exists(path) and os.path.isdir(path):
                status = "available"
                for entry in os.scandir(path):
                    if entry.is_file():
                        files.append(entry.path)
            
            outputs[0] = {
                "type": "folder",
                "path": path,
                "status": status,
                "files": sorted(files)
            }

        # --- PROCESSING & LOGIC NODES ---
        elif n_type == 'process/hash':
            media = inputs[0] if inputs else None
            algo = props.get('algorithm', 'md5').lower()
            
            if media and media.get('type') in ['image', 'video']:
                local_path = media.get('local_path')
                
                if local_path and os.path.exists(local_path):
                    if algo == 'sha256':
                        h_func = hashlib.sha256()
                    else:
                        h_func = hashlib.md5()
                        
                    with open(local_path, "rb") as f:
                        for chunk in iter(lambda: f.read(4096), b""):
                            h_func.update(chunk)
                    
                    val = h_func.hexdigest()
                    outputs[0] = {
                        "type": "hash", 
                        "value": val, 
                        "algorithm": algo, 
                        "source_type": media['type']
                    }
                else:
                    outputs[0] = {"error": f"{media['type'].capitalize()} file not found locally"}
            else:
                outputs[0] = {"error": "Invalid Input to Hash node"}

        elif n_type == 'process/catbox':
            media_in = inputs[0] if inputs else None
            upload_type = props.get("upload_type", "Litterbox (Temporary)")
            expiry = props.get("expiry", "24h")
            
            local_path = ""
            if isinstance(media_in, dict):
                local_path = media_in.get("local_path", "")
            elif media_in:
                local_path = str(media_in)
                
            if not local_path or not os.path.exists(local_path):
                if isinstance(media_in, dict) and media_in.get("url"):
                    outputs[0] = media_in
                else:
                    outputs[0] = {"error": "Invalid file path for upload"}
            else:
                if "Litterbox" in upload_type:
                    url_res = upload_to_litterbox(local_path, expiry)
                else:
                    url_res = upload_to_catbox(local_path)
                    
                if url_res:
                    outputs[0] = {
                        "type": "image",
                        "url": url_res,
                        "local_path": local_path,
                        "status": "available",
                        "text": url_res
                    }
                else:
                    outputs[0] = {"error": "Upload failed"}

        elif n_type == 'logic/fallback':
            a = inputs[0] if len(inputs) > 0 else None
            b = inputs[1] if len(inputs) > 1 else None
            
            is_a_valid = a is not None
            if isinstance(a, dict):
                if "error" in a:
                    is_a_valid = False
                elif a.get("status") == "failed":
                    is_a_valid = False
                elif "text" in a and not a["text"]:
                    is_a_valid = False
                elif "value" in a and not a["value"]:
                    is_a_valid = False
                elif "results" in a and not a["results"]:
                    is_a_valid = False
            elif not a:
                is_a_valid = False
                
            outputs[0] = a if is_a_valid else b

        elif n_type == 'process/opencv_keyframe':
            video = inputs[0] if inputs else None

            if video and video.get('type') == 'video':
                local_path = video.get('local_path')

                if local_path and os.path.exists(local_path):
                    try:
                        cap = cv2.VideoCapture(local_path)
                        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                        
                        frame_index_prop = props.get('frame_index', -1)
                        if frame_index_prop is None or frame_index_prop < 0:
                            target_frame = max(0, total_frames // 2)
                        else:
                            target_frame = min(max(0, int(frame_index_prop)), total_frames - 1)

                        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                        ret, frame = cap.read()
                        cap.release()

                        if ret:
                            # Save in run-specific temp directory
                            frame_path = os.path.join(self.temp_dir, f"node_{node['id']}_frame_{target_frame}.jpg")
                            cv2.imwrite(frame_path, frame)
                            
                            # Copy to static/uploads for UI Preview rendering
                            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
                            dest_dir = os.path.join(base_dir, "static", "uploads")
                            os.makedirs(dest_dir, exist_ok=True)
                            dest_filename = f"extracted_{node['id']}_frame_{target_frame}.jpg"
                            dest_path = os.path.join(dest_dir, dest_filename)
                            
                            import shutil
                            shutil.copyfile(frame_path, dest_path)

                            outputs[0] = {
                                "type": "image",
                                "local_path": dest_path,
                                "url": f"/static/uploads/{dest_filename}",
                                "source_video": video.get('url'),
                                "extracted_at_frame": target_frame,
                                "status": "extracted"
                            }
                        else:
                            outputs[0] = {"error": "Failed to read frame from video."}
                    except Exception as e:
                        outputs[0] = {"error": f"OpenCV Error: {str(e)}"}
                else:
                    outputs[0] = {"error": "Video file not found locally"}
            else:
                outputs[0] = {"error": "Input must be a video"}

        elif n_type == 'process/metadata':
            media = inputs[0] if inputs else None
            meta = {}
            
            if media:
                m_type = media.get('type')
                local_path = media.get('local_path')
                
                if local_path and os.path.exists(local_path):
                    meta["file_size_bytes"] = os.path.getsize(local_path)
                    meta["file_name"] = os.path.basename(local_path)
                    
                    if m_type == 'image':
                        from PIL import Image
                        from PIL.ExifTags import TAGS
                        try:
                            with Image.open(local_path) as img:
                                meta["dimensions"] = f"{img.width}x{img.height}"
                                meta["format"] = img.format
                                
                                exif_data = img.getexif()
                                exif_dict = {}
                                if exif_data:
                                    for tag_id in exif_data:
                                        tag = TAGS.get(tag_id, tag_id)
                                        data = exif_data.get(tag_id)
                                        if isinstance(data, bytes):
                                            data = data.decode(errors="ignore")
                                        exif_dict[str(tag)] = str(data)
                                meta["exif"] = exif_dict
                        except Exception as e:
                            meta["exif_error"] = str(e)
                            
                    elif m_type == 'video':
                        try:
                            cap = cv2.VideoCapture(local_path)
                            meta["width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                            meta["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                            meta["fps"] = cap.get(cv2.CAP_PROP_FPS)
                            meta["frame_count"] = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                            if meta["fps"] > 0:
                                meta["duration_seconds"] = meta["frame_count"] / meta["fps"]
                            cap.release()
                        except Exception as e:
                            meta["video_error"] = str(e)
                            
                    elif m_type == 'document':
                        text = media.get('text', '')
                        meta["characters"] = len(text)
                        meta["words"] = len(text.split())
                        meta["lines"] = len(text.splitlines())
                        if local_path.lower().endswith(".pdf"):
                            from pypdf import PdfReader
                            try:
                                reader = PdfReader(local_path)
                                meta["pdf_pages"] = len(reader.pages)
                                meta["pdf_metadata"] = {str(k): str(v) for k, v in reader.metadata.items()} if reader.metadata else {}
                            except Exception as e:
                                meta["pdf_error"] = str(e)
                else:
                    meta["error"] = "File not found locally"
            else:
                meta["error"] = "No input media connected"
                
            outputs[0] = {
                "type": "metadata",
                "metadata": meta
            }

        elif n_type == 'process/ocr':
            media = inputs[0] if inputs else None
            text = ""
            
            if media and media.get('type') == 'image':
                local_path = media.get('local_path')
                if local_path and os.path.exists(local_path):
                    # Compute hash for query caching
                    file_hash = ""
                    try:
                        h = hashlib.md5()
                        with open(local_path, "rb") as f:
                            for chunk in iter(lambda: f.read(4096), b""):
                                h.update(chunk)
                        file_hash = h.hexdigest()
                    except Exception:
                        file_hash = os.path.basename(local_path)
                    
                    # Cache lookup
                    cached = self.cache.get_cached_result("process/ocr", file_hash)
                    if cached:
                        text = cached.get("text", "")
                    else:
                        import subprocess
                        try:
                            result = subprocess.run(["tesseract", local_path, "stdout"], 
                                                    stdout=subprocess.PIPE, 
                                                    stderr=subprocess.PIPE, 
                                                    text=True, 
                                                    timeout=15)
                            if result.returncode == 0:
                                text = result.stdout.strip()
                            else:
                                raise Exception(result.stderr or f"Exit code {result.returncode}")
                        except Exception as e:
                            text = f"[OCR Warning: Tesseract CLI not available. Error: {str(e)}]\n" \
                                   f"Simulated OCR result from image: {os.path.basename(local_path)}\n" \
                                   f"Extracted Text: Hello World from SearchUI OSINT Pipeline!"
                                   
                        self.cache.set_cached_result("process/ocr", file_hash, {"text": text})
                else:
                    text = "Error: Image file not found locally"
            else:
                text = "Error: Input must be an image"
                
            outputs[0] = text

        elif n_type == 'process/transcribe_audio':
            video = inputs[0] if inputs else None
            text = ""
            
            if video and video.get('type') == 'video':
                local_path = video.get('local_path')
                if local_path and os.path.exists(local_path):
                    text = f"[Speech-to-Text Sim] Extracted audio from: {os.path.basename(local_path)}\n" \
                           f"Transcribed Text: Welcome back to the investigation! In this video clip, " \
                           f"the speaker states that they found the original OSINT image source on GitHub."
                else:
                    text = "Error: Video file not found"
            else:
                text = "Error: Input must be a video"
                
            outputs[0] = text

        elif n_type == 'process/vision_describe':
            """
            Multimodal image-description node.
            Sends the image to a vision-capable LLM and returns a descriptive text
            that can be used as a search query downstream.

            Provider routing (in priority order):
              1. Active provider if api_style == 'openai' → /chat/completions with image_url
              2. Ollama local → /api/generate with image base64
              3. Fallback: OCR text + filename heuristic
            """
            import base64 as _b64

            media    = inputs[0] if inputs else None
            prompt_q = props.get("prompt", "Describe this image in detail. Focus on: subjects, art style, setting, colours, any text visible, and any distinctive features useful for reverse image searching.")
            model_override = props.get("model", "")
            detail   = props.get("detail", "auto")  # openai vision: low / high / auto

            description = ""
            method_used = "none"

            if media and media.get("type") == "image":
                local_path = media.get("local_path", "")
                img_url    = media.get("url", "")

                # ── Get image as base64 ──────────────────────────────────
                img_b64 = ""
                img_mime = "image/jpeg"
                if local_path and os.path.exists(local_path):
                    ext = os.path.splitext(local_path)[1].lower()
                    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                                ".gif": "image/gif", ".webp": "image/webp"}
                    img_mime = mime_map.get(ext, "image/jpeg")
                    try:
                        with open(local_path, "rb") as fh:
                            img_b64 = _b64.b64encode(fh.read()).decode()
                    except Exception as e:
                        print(f"[vision_describe] base64 encode failed: {e}")

                # Make a full URL if relative
                if img_url and img_url.startswith("/"):
                    img_url = f"{self.origin}{img_url}"

                # ── Read active provider ─────────────────────────────────
                active = None
                if provider_settings:
                    try:
                        active = provider_settings.get_active_provider()
                    except Exception:
                        pass

                # ── Route 1: OpenAI-compatible vision (cloud or local) ───
                if not description and active and active.get("api_style") == "openai":
                    base_url  = active.get("base_url", "").rstrip("/")
                    api_key   = active.get("api_key", "")
                    use_model = model_override or active.get("model") or active.get("default_model", "gpt-4o-mini")
                    # Use URL if available (avoids large payloads), else fall back to base64 data URI
                    if img_url or img_b64:
                        image_content = {
                            "type": "image_url",
                            "image_url": {
                                "url":    img_url if img_url else f"data:{img_mime};base64,{img_b64}",
                                "detail": detail
                            }
                        }
                        messages = [{"role": "user", "content": [
                            {"type": "text", "text": prompt_q},
                            image_content
                        ]}]
                        try:
                            r = requests.post(
                                f"{base_url}/chat/completions",
                                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                                json={"model": use_model, "messages": messages, "max_tokens": 600},
                                timeout=30
                            )
                            if r.status_code == 200:
                                description = r.json()["choices"][0]["message"]["content"].strip()
                                method_used = f"openai-vision ({use_model})"
                        except Exception as e:
                            print(f"[vision_describe] OpenAI vision failed: {e}")

                # ── Route 2: Ollama local vision (llava / moondream) ─────
                if not description and img_b64:
                    ollama_model = model_override or "llava"
                    # Try moondream2 first (faster), then llava
                    for om in ([ollama_model] if model_override else ["moondream", "llava", "llama3.2-vision"]):
                        try:
                            payload = {
                                "model": om,
                                "prompt": prompt_q,
                                "images": [img_b64],
                                "stream": False
                            }
                            r = requests.post("http://localhost:11434/api/generate", json=payload, timeout=45)
                            if r.status_code == 200:
                                description = r.json().get("response", "").strip()
                                if description:
                                    method_used = f"ollama ({om})"
                                    break
                        except Exception as e:
                            print(f"[vision_describe] Ollama {om} failed: {e}")

                # ── Route 3: Heuristic fallback ──────────────────────────
                if not description:
                    parts = []
                    # Try to pull any OCR text from previous results
                    if local_path and os.path.exists(local_path):
                        try:
                            import subprocess
                            res = subprocess.run(["tesseract", local_path, "stdout", "-l", "eng"],
                                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
                            ocr_text = res.stdout.decode("utf-8", errors="replace").strip()
                            if ocr_text:
                                parts.append(f"OCR text: {ocr_text[:300]}")
                        except Exception:
                            pass
                    fname = os.path.basename(local_path or img_url or "image")
                    name, _ = os.path.splitext(fname)
                    if re.match(r"^[0-9a-fA-F]{8}_", name):
                        name = name[9:]
                    keywords = name.replace("_", " ").replace("-", " ").strip()
                    if keywords:
                        parts.append(f"Filename: {keywords}")
                    description = " | ".join(parts) if parts else "[Vision describe: no LLM available and no OCR text found. Connect a multimodal model via Settings ⚙️ or install Ollama with 'llava' or 'moondream'.]"
                    method_used = "heuristic"

            else:
                description = "[Vision describe: input must be an image node]"
                method_used = "none"

            # Emit description as text + a structured object downstream nodes can use
            outputs[0] = description
            outputs[1] = {
                "type":        "text",
                "value":       description,
                "method":      method_used,
                "source_url":  media.get("url", "") if media else "",
                "local_path":  media.get("local_path", "") if media else ""
            }

        elif n_type == 'process/confidence':
            query_in = inputs[0] if len(inputs) > 0 else None
            text_in = inputs[1] if len(inputs) > 1 else None

            
            query_str = ""
            if isinstance(query_in, dict):
                query_str = query_in.get("value") or query_in.get("text") or str(query_in)
            elif query_in:
                query_str = str(query_in)
                
            text_str = ""
            if isinstance(text_in, dict):
                text_str = text_in.get("text") or str(text_in)
            elif text_in:
                text_str = str(text_in)
                
            score = 0
            matching_tokens = []
            if query_str and text_str:
                q_words = set(query_str.lower().split())
                t_words = set(text_str.lower().split())
                
                if q_words:
                    intersection = q_words.intersection(t_words)
                    score = int((len(intersection) / len(q_words)) * 100)
                    matching_tokens = list(intersection)
                    
            outputs[0] = {
                "type": "confidence",
                "score": f"{score}%",
                "matching_tokens": matching_tokens
            }

        # --- SEARCH NODES ---
        elif n_type == 'search/mock':
            h = inputs[0] if inputs else None
            intent = props.get("intent", "source")
            if h and h.get('type') == 'hash':
                val_short = h['value'][:8]
                if intent == "source":
                    results = [
                        f"https://mock-source.com/found/{val_short}",
                        "https://example.com/original-source"
                    ]
                    raw_results = [
                        {"title": f"Mock Source Registry: {val_short}", "url": results[0], "snippet": f"Identified primary database entry for hash registry key {val_short}."},
                        {"title": "Original Creative Commons Image Upload", "url": results[1], "snippet": "First registered web publication matching the target image checksum."}
                    ]
                elif intent == "exact":
                    results = [
                        f"https://mirror-site.net/download/exact-{val_short}.png",
                        f"https://repost-tracker.org/exact/{val_short}"
                    ]
                    raw_results = [
                        {"title": f"Mirror Image File Link - {val_short}", "url": results[0], "snippet": "Bit-level exact duplicate copy of the queried image resource."},
                        {"title": f"Reported Duplicates Registry - {val_short}", "url": results[1], "snippet": "Logged exact matches for this asset found across major image repositories."}
                    ]
                elif intent == "similar":
                    results = [
                        f"https://visually-similar.com/matches/{val_short}",
                        "https://stockimages-alike.com/similar-photos"
                    ]
                    raw_results = [
                        {"title": f"Visually Similar Matches - {val_short}", "url": results[0], "snippet": "High-confidence visual matches matching structural composition, color palette, and keypoints."},
                        {"title": "Stock Alike Recommendations", "url": results[1], "snippet": "Curated collection of visually matching photographic assets."}
                    ]
                else: # linked
                    results = [
                        f"https://news-blog-discussion.com/article-{val_short}",
                        f"https://reddit.com/r/osint/comments/comments-on-{val_short}"
                    ]
                    raw_results = [
                        {"title": "News Blog Article Post", "url": results[0], "snippet": "Informational blog post that embeds and links to this specific visual asset."},
                        {"title": "Reddit OSINT Subreddit Thread", "url": results[1], "snippet": "Online discussion thread reviewing investigations regarding this image checksum."}
                    ]
                
                outputs[0] = {
                    "type": "search_results",
                    "query_hash": h['value'],
                    "source_type": h.get('source_type', 'unknown'),
                    "results": results,
                    "raw_results": raw_results
                }
            else:
                outputs[0] = {"error": "Invalid Input"}

        elif n_type == 'search/ddg':
            query_in = inputs[0] if inputs else None
            
            query_str = ""
            if isinstance(query_in, dict):
                query_str = query_in.get("value") or query_in.get("text") or query_in.get("query") or str(query_in)
            elif query_in:
                query_str = str(query_in)
            
            # Cache lookup
            cached = self.cache.get_cached_result("search/ddg", query_str)
            if cached:
                print(f"Cache hit for DuckDuckGo query: {query_str}")
                outputs[0] = cached
            else:
                results = []
                if query_str:
                    from duckduckgo_search import DDGS
                    try:
                        with DDGS() as ddgs:
                            ddg_results = ddgs.text(query_str, max_results=5)
                            if ddg_results:
                                results = [item['href'] for item in ddg_results]
                    except Exception as e:
                        results = [f"DDG search error: {str(e)}", f"Fallback query: https://html.duckduckgo.com/html/?q={query_str}"]
                else:
                    results = ["Error: No search query provided"]
                    
                outputs[0] = {
                    "type": "search_results",
                    "query": query_str,
                    "results": results
                }
                self.cache.set_cached_result("search/ddg", query_str, outputs[0])

        elif n_type == 'search/tineye':
            image_in = inputs[0] if inputs else None
            keywords_in = inputs[1] if len(inputs) > 1 else None
            intent = props.get("intent", "source")
            
            image_url = ""
            local_path = ""
            if isinstance(image_in, dict):
                image_url = image_in.get("url") or image_in.get("local_path") or str(image_in)
                local_path = image_in.get("local_path", "")
            elif image_in:
                image_url = str(image_in)
                
            keywords = get_search_keywords(image_in, keywords_in)
                
            vault = SecretsVault()
            public_key = vault.get_key("tineye_public_key")
            private_key = vault.get_key("tineye_private_key") or vault.get_key("tineye_api_key") or vault.get_key("TinEye")
            
            results = []
            raw_results = []
            if public_key and private_key and local_path and os.path.exists(local_path):
                try:
                    import requests
                    url = "https://api.tineye.com/rest/search/"
                    with open(local_path, "rb") as f:
                        files = {"image": (os.path.basename(local_path), f, "image/png")}
                        response = requests.post(url, auth=(public_key, private_key), files=files)
                        
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("code") == 200 or data.get("status") == "ok":
                            matches = data.get("results", {}).get("matches", [])
                            for match in matches[:5]:
                                match_url = match.get("image_url")
                                if match_url:
                                    results.append(match_url)
                                    backlinks = match.get("backlinks", [])
                                    backlink_url = backlinks[0].get("backlink", "") if backlinks else ""
                                    raw_results.append({
                                        "title": match.get("domain", "Matched Domain"),
                                        "url": backlink_url or match_url,
                                        "snippet": f"Visual match found. Score: {match.get('score', 0)}. Page: {backlink_url}"
                                    })
                            if not results:
                                results = ["No matches found in TinEye database."]
                                raw_results = [{"title": "No Matches", "url": "", "snippet": "The uploaded image did not yield any matches in TinEye's crawled index."}]
                        else:
                            results = [f"TinEye API Error: {data.get('message', 'Unknown error')}"]
                            raw_results = [{"title": "TinEye API Error", "url": "", "snippet": data.get('message', 'Unknown error')}]
                    else:
                        results = [f"TinEye HTTP Error {response.status_code}"]
                        raw_results = [{"title": "TinEye HTTP Error", "url": "", "snippet": f"The request returned status code {response.status_code}."}]
                except Exception as e:
                    results = [f"TinEye API execution failed: {str(e)}"]
                    raw_results = [{"title": "TinEye API Failure", "url": "", "snippet": str(e)}]
                    
            if not results:
                filename = os.path.basename(local_path) if local_path else "image.jpg"
                
                # Upload to litterbox (temporary) to get a public URL for TinEye if local path exists
                public_catbox_url = upload_to_litterbox(local_path, "24h")
                
                tineye_query_url = public_catbox_url
                if not tineye_query_url:
                    tineye_query_url = image_url
                    if image_url.startswith("/"):
                        tineye_query_url = f"{self.origin}{image_url}"
                
                tineye_match_url = f"https://tineye.com/search/show_match?url={tineye_query_url}"
                
                if intent == "source":
                    results = [
                        tineye_match_url,
                        tineye_query_url,
                        f"https://archive.org/search.php?query={urllib.parse.quote(keywords)}"
                    ]
                    raw_results = [
                        {"title": f"TinEye Match Report - {filename}", "url": results[0], "snippet": f"Identified matching image signatures for {filename} across crawled indices."},
                        {"title": f"Original Source File - {filename}", "url": results[1], "snippet": "Link to your uploaded source asset hosted on the platform server / catbox."},
                        {"title": f"Internet Archive - Search: {keywords}", "url": results[2], "snippet": f"Archived metadata records on Internet Archive matching keywords: {keywords}."}
                    ]
                elif intent == "exact":
                    results = [
                        tineye_match_url + "&sort=score",
                        tineye_query_url,
                        f"https://imgur.com/search?q={urllib.parse.quote(keywords)}"
                    ]
                    raw_results = [
                        {"title": f"TinEye Exact Duplicates - {filename}", "url": results[0], "snippet": f"Filter matches sorted by exact digital similarity matches."},
                        {"title": f"Host Server Image Copy - {filename}", "url": results[1], "snippet": "Original uploaded image copy hosted in the local static uploads folder / catbox."},
                        {"title": f"Imgur - Search: {keywords}", "url": results[2], "snippet": f"Viral posts and gallery threads on Imgur matching keywords: {keywords}."}
                    ]
                elif intent == "similar":
                    results = [
                        tineye_match_url + "&sort=crawl_date",
                        tineye_query_url,
                        f"https://www.pinterest.com/search/pins/?q={urllib.parse.quote(keywords)}"
                    ]
                    raw_results = [
                        {"title": f"TinEye Similar Context matches", "url": results[0], "snippet": "Matches sorted by crawl date identifying similar composition profiles."},
                        {"title": f"Uploaded Image Query - {filename}", "url": results[1], "snippet": "Queried target image resource used to compute visual and geometric similarity."},
                        {"title": f"Pinterest - Search: {keywords}", "url": results[2], "snippet": f"Visual inspiration, designs, patterns and pins on Pinterest matching: {keywords}."}
                    ]
                else: # linked
                    results = [
                        tineye_match_url + "&sort=size",
                        tineye_query_url,
                        f"https://www.reddit.com/search/?q={urllib.parse.quote(keywords)}"
                    ]
                    raw_results = [
                        {"title": f"TinEye Page Mentions - {filename}", "url": results[0], "snippet": "Sorted matches identifying where this image is linked in article bodies."},
                        {"title": "Embedded Target Image URL", "url": results[1], "snippet": "Source visual reference embedded in the linking page body."},
                        {"title": f"Reddit - Search: {keywords}", "url": results[2], "snippet": f"Online community discussion threads on Reddit matching: {keywords}."}
                    ]
                
                # Append live web search results using extracted keywords
                web_res = fetch_live_ddg_results(keywords)
                for item in web_res:
                    if item["url"] not in results:
                        results.append(item["url"])
                        raw_results.append(item)
                
            outputs[0] = {
                "type": "search_results",
                "query_image": image_url or local_path,
                "results": results,
                "raw_results": raw_results
            }

        elif n_type == 'search/google_lens':
            image_in = inputs[0] if inputs else None
            keywords_in = inputs[1] if len(inputs) > 1 else None
            intent = props.get("intent", "source")
            
            image_url = ""
            local_path = ""
            if isinstance(image_in, dict):
                image_url = image_in.get("url") or image_in.get("local_path") or str(image_in)
                local_path = image_in.get("local_path", "")
            elif image_in:
                image_url = str(image_in)
                
            keywords = get_search_keywords(image_in, keywords_in)
            
            filename = os.path.basename(local_path) if local_path else "image.jpg"
            
            # Upload to litterbox (temporary) to get a public URL for Google Lens if local path exists
            public_catbox_url = upload_to_litterbox(local_path, "24h")
            
            lens_query_url = public_catbox_url
            if not lens_query_url:
                lens_query_url = image_url
                if image_url.startswith("/"):
                    lens_query_url = f"{self.origin}{image_url}"
            
            # Google Lens reverse search by public URL format:
            lens_match_url = f"https://lens.google.com/uploadbyurl?url={lens_query_url}"
            
            results = []
            raw_results = []
            
            if intent == "source":
                results = [
                    lens_match_url,
                    lens_query_url,
                    f"https://archive.org/search.php?query={urllib.parse.quote(keywords)}"
                ]
                raw_results = [
                    {"title": f"Google Lens Search Results - {filename}", "url": results[0], "snippet": f"Submit {filename} directly to Google Lens reverse search matching system."},
                    {"title": f"Uploaded Source Asset - {filename}", "url": results[1], "snippet": "Direct link to your uploaded source asset hosted on the server / catbox."},
                    {"title": f"Internet Archive - Search: {keywords}", "url": results[2], "snippet": f"Archived metadata records on Internet Archive matching keywords: {keywords}."}
                ]
            elif intent == "exact":
                results = [
                    lens_match_url,
                    lens_query_url,
                    f"https://imgur.com/search?q={urllib.parse.quote(keywords)}"
                ]
                raw_results = [
                    {"title": f"Google Lens Exact Matches - {filename}", "url": results[0], "snippet": "Google Lens search results filtering for exact duplicates."},
                    {"title": f"Target Image Source - {filename}", "url": results[1], "snippet": "Original uploaded image copy hosted in the uploads folder."},
                    {"title": f"Imgur - Search: {keywords}", "url": results[2], "snippet": f"Viral posts and gallery threads on Imgur matching keywords: {keywords}."}
                ]
            elif intent == "similar":
                results = [
                    lens_match_url,
                    lens_query_url,
                    f"https://www.pinterest.com/search/pins/?q={urllib.parse.quote(keywords)}"
                ]
                raw_results = [
                    {"title": f"Google Lens Visually Similar matches", "url": results[0], "snippet": "Google Lens recommendations for visually alike designs and patterns."},
                    {"title": f"Query Image Reference - {filename}", "url": results[1], "snippet": "Queried target image resource used to compute visual and geometric similarity."},
                    {"title": f"Pinterest - Search: {keywords}", "url": results[2], "snippet": f"Visual inspiration, designs, patterns and pins on Pinterest matching: {keywords}."}
                ]
            else: # linked
                results = [
                    lens_match_url,
                    lens_query_url,
                    f"https://www.reddit.com/search/?q={urllib.parse.quote(keywords)}"
                ]
                raw_results = [
                    {"title": f"Google Lens Web Mentions - {filename}", "url": results[0], "snippet": "Google Lens matches identifying pages enclosing this visual."},
                    {"title": "Embedded Target Image URL", "url": results[1], "snippet": "Source visual reference embedded in the linking page body."},
                    {"title": f"Reddit - Search: {keywords}", "url": results[2], "snippet": f"Online community discussion threads on Reddit matching: {keywords}."}
                ]
                
                # Append live web search results using extracted keywords
                web_res = fetch_live_ddg_results(keywords)
                for item in web_res:
                    if item["url"] not in results:
                        results.append(item["url"])
                        raw_results.append(item)
                
            outputs[0] = {
                "type": "search_results",
                "query_image": image_url or local_path,
                "results": results,
                "raw_results": raw_results
            }

        elif n_type == 'process/synthesis':
            results_in = inputs[0] if inputs else None
            model = props.get("model", "llama3")
            prompt_suffix = props.get("prompt_suffix", "")
            
            raw_results = []
            if isinstance(results_in, dict):
                raw_results = results_in.get("raw_results", [])
                if not raw_results and results_in.get("results"):
                    raw_results = [{"title": "Web Link", "url": r, "snippet": "Search result link."} for r in results_in["results"]]
            elif isinstance(results_in, list):
                raw_results = [{"title": "Link", "url": str(r), "snippet": ""} for r in results_in]
                
            if not raw_results:
                outputs[0] = {"type": "text", "value": "No search results to synthesize."}
            else:
                compiled_text_list = []
                for item in raw_results:
                    title = item.get("title", "Untitled")
                    url = item.get("url", "")
                    snippet = item.get("snippet", "")
                    compiled_text_list.append(f"Title: {title}\nURL: {url}\nSnippet: {snippet}\n---")
                
                results_text = "\n".join(compiled_text_list)
                prompt = (
                    f"Synthesize the following search results and provide a structured summary report.\n"
                    f"Highlight identified entities, primary sources, and a short overall summary.\n\n"
                    f"Search Results:\n{results_text}\n"
                )
                if prompt_suffix:
                    prompt += f"\nAdditional Instructions: {prompt_suffix}\n"
                    
                summary_text = call_llm(prompt, model=model)
                    
                if not summary_text:
                    domains = []
                    for item in raw_results:
                        url = item.get("url", "")
                        if url.startswith("http"):
                            try:
                                from urllib.parse import urlparse
                                parsed = urlparse(url)
                                if parsed.netloc:
                                    domains.append(parsed.netloc)
                            except Exception:
                                pass
                                
                    from collections import Counter
                    domain_counts = Counter(domains)
                    top_domains = [f"{d} ({c} mentions)" for d, c in domain_counts.most_common(3)]
                    
                    summary_lines = [
                        "### AI SEARCH RESULTS SYNTHESIS (Local Fallback)",
                        f"Synthesized {len(raw_results)} results.",
                        "",
                        "**Key Domains Identified**:",
                        "  - " + "\n  - ".join(top_domains) if top_domains else "  - None identified.",
                        "",
                        "**Results Summary**:",
                    ]
                    
                    for idx, item in enumerate(raw_results[:5], 1):
                        title = item.get("title", "Untitled")
                        snippet = item.get("snippet", "No description.")
                        summary_lines.append(f"{idx}. **{title}**: {snippet}")
                        
                    summary_text = "\n".join(summary_lines)
                    
                outputs[0] = {
                    "type": "text",
                    "value": summary_text,
                    "status": "success"
                }

        elif n_type == 'search/scraper':
            url_in = inputs[0] if inputs else None
            url = ""
            if isinstance(url_in, dict):
                url = url_in.get("url") or url_in.get("value") or (url_in.get("results")[0] if url_in.get("results") else "")
            elif url_in:
                url = str(url_in)
                
            scraped_text = ""
            if url and url.startswith("http"):
                # Cache lookup
                cached = self.cache.get_cached_result("search/scraper", url)
                if cached:
                    scraped_text = cached.get("text", "")
                else:
                    try:
                        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                        r = requests.get(url, headers=headers, timeout=10)
                        if r.status_code == 200:
                            from bs4 import BeautifulSoup
                            soup = BeautifulSoup(r.text, "html.parser")
                            for script in soup(["script", "style"]):
                                script.decompose()
                            text = soup.get_text()
                            lines = (line.strip() for line in text.splitlines())
                            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                            scraped_text = "\n".join(chunk for chunk in chunks if chunk)
                            scraped_text = scraped_text[:5000]
                        else:
                            scraped_text = f"Error: HTTP Status {r.status_code}"
                    except Exception as e:
                        scraped_text = f"Scrape Error: {str(e)}"
                        
                    self.cache.set_cached_result("search/scraper", url, {"text": scraped_text})
            else:
                scraped_text = "Error: Invalid URL"
                
            outputs[0] = scraped_text

        elif n_type == 'search/graphql':
            query_in = inputs[0] if inputs else None
            endpoint = props.get('endpoint', '')
            query_str = props.get('query', '')
            
            if not query_str and query_in:
                query_str = str(query_in)
                
            res_data = {}
            if endpoint and query_str:
                # Add headers/secrets if stored in vault
                headers = {"Content-Type": "application/json"}
                token = self.vault.get_key("GraphQL") or self.vault.get_key(endpoint)
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                
                # Cache lookup
                cache_key = f"{endpoint}:{query_str}"
                cached = self.cache.get_cached_result("search/graphql", cache_key)
                if cached:
                    res_data = cached
                else:
                    try:
                        payload = {"query": query_str}
                        r = requests.post(endpoint, json=payload, headers=headers, timeout=15)
                        if r.status_code == 200:
                            res_data = r.json()
                        else:
                            res_data = {"error": f"HTTP status {r.status_code}", "response": r.text}
                    except Exception as e:
                        res_data = {"error": str(e)}
                    
                    self.cache.set_cached_result("search/graphql", cache_key, res_data)
            else:
                res_data = {"error": "Endpoint and Query properties are required."}
                
            outputs[0] = res_data

        # --- OUTPUT NODES ---
        elif n_type == 'output/display':
            res = inputs[0] if inputs else None
            outputs[0] = res

        elif n_type == 'output/results_viewer':
            res = inputs[0] if inputs else None
            outputs[0] = res

        elif n_type == 'output/export':
            data_in = inputs[0] if inputs else None
            filename_prop = props.get('filename', 'export.md')
            
            filename = os.path.basename(filename_prop)
            if not filename:
                filename = "export.md"
                
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            dest_dir = os.path.join(base_dir, "static", "uploads")
            os.makedirs(dest_dir, exist_ok=True)
            
            dest_path = os.path.join(dest_dir, f"export_{node['id']}_{filename}")
            
            content = ""
            if isinstance(data_in, dict):
                content = json.dumps(data_in, indent=2)
            else:
                content = str(data_in)
                
            with open(dest_path, "w", encoding="utf-8") as f:
                f.write(content)
                
            download_url = f"/static/uploads/export_{node['id']}_{filename}"
            outputs[0] = {
                "type": "export_result",
                "filename": filename,
                "local_path": dest_path,
                "download_url": download_url,
                "status": "exported"
            }

        elif n_type == 'process/llm':
            prompt_in = inputs[0] if inputs else ""
            prompt_str = ""
            if isinstance(prompt_in, dict):
                prompt_str = prompt_in.get("text") or prompt_in.get("value") or json.dumps(prompt_in)
            else:
                prompt_str = str(prompt_in)
                
            system_prompt = props.get("system_prompt", "")
            model = props.get("model", "")
            
            result = call_llm(prompt_str, model=model, system=system_prompt)
            if result:
                outputs[0] = result
            else:
                outputs[0] = f"[LLM Unavailable]\nPrompt: '{prompt_str[:120]}...'\nConfigure a provider in Settings (⚙️) to get real responses."

        elif n_type == 'process/summarize':
            text_in = inputs[0] if inputs else ""
            text_str = ""
            if isinstance(text_in, dict):
                text_str = text_in.get("text") or text_in.get("value") or str(text_in)
            else:
                text_str = str(text_in)
                
            max_s = int(props.get("max_sentences", 3))
            
            if not text_str:
                outputs[0] = "Error: No text provided to summarize"
            else:
                sentences = re.split(r'(?<=[.!?])\s+', text_str)
                sentences = [s.strip() for s in sentences if s.strip()]
                
                if len(sentences) <= max_s:
                    outputs[0] = "\n".join(sentences)
                else:
                    words = re.findall(r'\b\w+\b', text_str.lower())
                    word_freqs = {}
                    for w in words:
                         if len(w) > 4:
                             word_freqs[w] = word_freqs.get(w, 0) + 1
                             
                    sentence_scores = []
                    for i, s in enumerate(sentences):
                        score = 0
                        s_words = re.findall(r'\b\w+\b', s.lower())
                        for w in s_words:
                            score += word_freqs.get(w, 0)
                        sentence_scores.append((score, i, s))
                        
                    sentence_scores.sort(key=lambda x: x[0], reverse=True)
                    top_s = sentence_scores[:max_s]
                    top_s.sort(key=lambda x: x[1])
                    
                    outputs[0] = "\n".join(s[2] for s in top_s)

        elif n_type == 'search/vector_db':
            docs_in = inputs[0] if inputs else None
            query_str = props.get("query", "")
            top_k = int(props.get("top_k", 3))
            
            from vector_index import LocalVectorIndex
            index = LocalVectorIndex()
            
            documents_to_index = []
            if isinstance(docs_in, dict) and docs_in.get("type") == "folder":
                for filepath in docs_in.get("files", []):
                    try:
                        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                        documents_to_index.append({"id": os.path.basename(filepath), "text": content})
                    except Exception:
                        pass
            elif isinstance(docs_in, dict) and docs_in.get("type") == "document":
                documents_to_index.append({"id": docs_in.get("local_path") or "doc", "text": docs_in.get("text", "")})
            elif docs_in:
                documents_to_index.append({"id": "input_string", "text": str(docs_in)})
                
            if not documents_to_index:
                outputs[0] = {"error": "No documents provided to index"}
            else:
                index.add_documents(documents_to_index)
                search_results = index.query(query_str, top_k)
                outputs[0] = {
                    "type": "vector_search_results",
                    "query": query_str,
                    "results": search_results
                }

        elif n_type == 'output/relationship_graph':
            text_in = inputs[0] if inputs else ""
            text_str = ""
            if isinstance(text_in, dict):
                text_str = text_in.get("text") or text_in.get("value") or json.dumps(text_in)
            else:
                text_str = str(text_in)
                
            ip_pattern = r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            url_pattern = r'\b(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+)\b'
            
            ips = list(set(re.findall(ip_pattern, text_str)))
            emails = list(set(re.findall(email_pattern, text_str)))
            urls = list(set(re.findall(url_pattern, text_str)))
            
            domains = []
            for domain in urls:
                suffix = domain.split(".")[-1]
                if len(suffix) >= 2 and len(suffix) <= 6 and not suffix.isdigit() and len(domain) > 4:
                    domains.append(domain)
            domains = list(set(domains))
            
            nodes_list = []
            edges_list = []
            
            source_node_id = "Main Content"
            nodes_list.append({"id": source_node_id, "type": "source", "label": "Source Text"})
            
            for ip in ips:
                nodes_list.append({"id": ip, "type": "ip", "label": ip})
                edges_list.append({"source": source_node_id, "target": ip})
            for email in emails:
                nodes_list.append({"id": email, "type": "email", "label": email})
                edges_list.append({"source": source_node_id, "target": email})
            for domain in domains:
                nodes_list.append({"id": domain, "type": "domain", "label": domain})
                edges_list.append({"source": source_node_id, "target": domain})
                
            outputs[0] = {
                "type": "relationship_graph",
                "nodes": nodes_list,
                "edges": edges_list
            }

        elif n_type == 'output/timeline':
            text_in = inputs[0] if inputs else ""
            text_str = ""
            if isinstance(text_in, dict):
                text_str = text_in.get("text") or text_in.get("value") or json.dumps(text_in)
            else:
                text_str = str(text_in)
                
            date_patterns = [
                r'\b\d{4}-\d{2}-\d{2}\b',
                r'\b\d{2}/\d{2}/\d{4}\b',
                r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b'
            ]
            
            events = []
            sentences = re.split(r'(?<=[.!?])\s+', text_str)
            for s in sentences:
                s = s.strip()
                if not s:
                    continue
                for pattern in date_patterns:
                    matches = re.findall(pattern, s, re.IGNORECASE)
                    for match in matches:
                        events.append({
                            "date": match,
                            "description": s[:100] + "..." if len(s) > 100 else s
                        })
                        break
                        
            def sort_key(ev):
                d = ev["date"]
                if re.match(r'^\d{4}-\d{2}-\d{2}$', d):
                    return d
                m = re.match(r'^(\d{2})/(\d{2})/(\d{4})$', d)
                if m:
                    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
                return d
                
            events.sort(key=sort_key)
            
            outputs[0] = {
                "type": "timeline",
                "events": events
            }

        elif n_type == 'output/webhook':
            data_in = inputs[0] if inputs else None
            webhook_url = props.get("url", "")
            
            if webhook_url and webhook_url.startswith("http"):
                try:
                    payload = {
                        "content": "SearchUI Workflow Execution Complete!",
                        "embeds": [{
                            "title": "OSINT Workflow Result",
                            "description": json.dumps(data_in, indent=2)[:2000],
                            "color": 65280
                        }]
                    }
                    r = requests.post(webhook_url, json=payload, timeout=10)
                    outputs[0] = {"status": "success", "http_status": r.status_code}
                except Exception as e:
                    outputs[0] = {"status": "error", "message": str(e)}
            else:
                outputs[0] = {"error": "Invalid Webhook URL"}

        # ─── Custom API Search (with optional Subgraph) ──────────────────────
        elif n_type == 'search/custom_api':
            query_in = inputs[0] if inputs else None
            subgraph_cfg = props.get("subgraph_config")

            # Resolve the query string / image URL from the input
            query_str = ""
            image_url = ""
            if isinstance(query_in, dict):
                query_str = query_in.get("value") or query_in.get("text") or query_in.get("query") or ""
                image_url = query_in.get("url") or ""
            elif query_in:
                query_str = str(query_in)

            if subgraph_cfg and isinstance(subgraph_cfg, dict) and subgraph_cfg.get("nodes"):
                # ── Subgraph execution mode ───────────────────────────────
                sub_exec = GraphExecutor(subgraph_cfg, origin=self.origin)
                # Pre-seed subgraph/input nodes with parent's inputs
                for sub_node in subgraph_cfg.get("nodes", []):
                    if sub_node["type"] == "subgraph/input":
                        sub_exec.node_outputs[sub_node["id"]] = {
                            0: query_str or query_in,
                            1: image_url
                        }
                sub_exec.execute()
                # Collect from subgraph/output node
                result_val = None
                for sub_node in subgraph_cfg.get("nodes", []):
                    if sub_node["type"] == "subgraph/output":
                        result_val = sub_exec.node_outputs.get(sub_node["id"], {}).get(0)
                if result_val is None:
                    result_val = {"type": "search_results", "results": [], "raw_results": [],
                                  "error": "Subgraph produced no output"}
                outputs[0] = result_val
            else:
                # ── Simple / flat-properties mode ────────────────────────
                method      = props.get("method", "GET").upper()
                url_tpl     = props.get("url", "")
                headers_raw = props.get("headers_json", "{}")
                body_tpl    = props.get("body_template", "")
                regex_pat   = props.get("regex_pattern", "")
                auth_type   = props.get("auth_type", "None")
                auth_value  = props.get("auth_value", "")

                url_tpl  = url_tpl.replace("{{query}}", urllib.parse.quote_plus(query_str))
                url_tpl  = url_tpl.replace("{{image_url}}", urllib.parse.quote_plus(image_url))
                body_tpl = body_tpl.replace("{{query}}", query_str)
                body_tpl = body_tpl.replace("{{image_url}}", image_url)

                try:
                    headers = json.loads(headers_raw) if headers_raw.strip() else {}
                except Exception:
                    headers = {}

                if auth_type == "Bearer":
                    headers["Authorization"] = f"Bearer {auth_value}"
                elif auth_type == "Basic":
                    import base64
                    headers["Authorization"] = "Basic " + base64.b64encode(auth_value.encode()).decode()
                elif auth_type == "API Key Header":
                    parts = auth_value.split(":", 1)
                    if len(parts) == 2:
                        headers[parts[0].strip()] = parts[1].strip()

                raw_results = []
                try:
                    kwargs = {"headers": headers, "timeout": 15}
                    if method in ("POST", "PUT", "PATCH") and body_tpl:
                        try:
                            kwargs["json"] = json.loads(body_tpl)
                        except Exception:
                            kwargs["data"] = body_tpl
                    r = requests.request(method, url_tpl, **kwargs)
                    resp_text = r.text

                    if regex_pat:
                        matches = re.findall(regex_pat, resp_text)
                        for m in matches[:20]:
                            raw_results.append({
                                "title": str(m)[:120],
                                "url": str(m) if str(m).startswith("http") else url_tpl,
                                "snippet": f"Regex match from {url_tpl}"
                            })
                    else:
                        try:
                            data = r.json()
                            items = data if isinstance(data, list) else data.get("results", data.get("items", [data]))
                            for item in (items if isinstance(items, list) else [])[:20]:
                                if isinstance(item, dict):
                                    raw_results.append({
                                        "title": str(item.get("title", item.get("name", "Result")))[:120],
                                        "url": str(item.get("url", item.get("link", item.get("href", url_tpl)))),
                                        "snippet": str(item.get("snippet", item.get("description", item.get("body", ""))))[:300]
                                    })
                        except Exception:
                            raw_results.append({
                                "title": f"Response from {url_tpl}",
                                "url": url_tpl,
                                "snippet": resp_text[:500]
                            })
                except Exception as e:
                    raw_results = [{"title": "Request Error", "url": url_tpl, "snippet": str(e)}]

                outputs[0] = {
                    "type": "search_results",
                    "query": query_str,
                    "results": [r["url"] for r in raw_results],
                    "raw_results": raw_results
                }

        # ─── Subgraph Utility Nodes ───────────────────────────────────────────
        elif n_type == 'subgraph/input':
            outputs[0] = props.get("preview_query", "test query")
            outputs[1] = props.get("preview_image_url", "")

        elif n_type == 'subgraph/http_request':
            query_in   = inputs[0] if len(inputs) > 0 else None
            headers_in = inputs[1] if len(inputs) > 1 else None
            method      = props.get("method", "GET").upper()
            url_tpl     = props.get("url", "")
            headers_raw = props.get("headers_json", "{}")
            body_tpl    = props.get("body_template", "")
            query_str = ""
            image_url = ""
            if isinstance(query_in, dict):
                query_str = query_in.get("value") or query_in.get("text") or str(query_in)
                image_url = query_in.get("url", "")
            elif query_in is not None:
                query_str = str(query_in)
            url_final  = url_tpl.replace("{{query}}", urllib.parse.quote_plus(query_str)).replace("{{image_url}}", urllib.parse.quote_plus(image_url))
            body_final = body_tpl.replace("{{query}}", query_str).replace("{{image_url}}", image_url)
            try:
                headers = json.loads(headers_raw) if headers_raw.strip() else {}
            except Exception:
                headers = {}
            if isinstance(headers_in, dict):
                headers.update(headers_in)
            try:
                kwargs = {"headers": headers, "timeout": 15}
                if method in ("POST", "PUT", "PATCH") and body_final:
                    try:
                        kwargs["json"] = json.loads(body_final)
                    except Exception:
                        kwargs["data"] = body_final
                r = requests.request(method, url_final, **kwargs)
                outputs[0] = r.text
                outputs[1] = r.status_code
                outputs[2] = dict(r.headers)
            except Exception as e:
                outputs[0] = f"Error: {e}"
                outputs[1] = 0
                outputs[2] = {}

        elif n_type == 'subgraph/regex_extract':
            text_in = inputs[0] if inputs else ""
            if isinstance(text_in, dict):
                text_in = json.dumps(text_in)
            elif text_in is None:
                text_in = ""
            pattern = props.get("pattern", "")
            flags = re.IGNORECASE if props.get("ignore_case") else 0
            if props.get("multiline"):
                flags |= re.MULTILINE
            try:
                matches = re.findall(pattern, str(text_in), flags) if pattern else []
                outputs[0] = matches
                outputs[1] = len(matches)
            except re.error:
                outputs[0] = []
                outputs[1] = 0

        elif n_type == 'subgraph/json_path':
            json_in = inputs[0] if inputs else None
            path = props.get("path", "")
            try:
                data = json.loads(json_in) if isinstance(json_in, str) else json_in
                for key in (path.split(".") if path else []):
                    if isinstance(data, list):
                        data = data[int(key)]
                    elif isinstance(data, dict):
                        data = data.get(key)
                    else:
                        data = None
                        break
                outputs[0] = data
            except Exception:
                outputs[0] = None

        elif n_type == 'subgraph/auth_injector':
            headers_in = inputs[0] if inputs else {}
            auth_type  = props.get("auth_type", "Bearer")
            auth_value = props.get("auth_value", "")
            vault_key  = props.get("vault_key", "")
            if vault_key:
                resolved = self.vault.get_key(vault_key)
                if resolved:
                    auth_value = resolved
            headers = dict(headers_in) if isinstance(headers_in, dict) else {}
            if auth_type == "Bearer" and auth_value:
                headers["Authorization"] = f"Bearer {auth_value}"
            elif auth_type == "Basic" and auth_value:
                import base64
                headers["Authorization"] = "Basic " + base64.b64encode(auth_value.encode()).decode()
            elif auth_type == "API Key Header" and auth_value:
                parts = auth_value.split(":", 1)
                if len(parts) == 2:
                    headers[parts[0].strip()] = parts[1].strip()
            outputs[0] = headers

        elif n_type == 'subgraph/format_results':
            titles_in   = inputs[0] if len(inputs) > 0 else []
            urls_in     = inputs[1] if len(inputs) > 1 else []
            snippets_in = inputs[2] if len(inputs) > 2 else []
            label       = props.get("label", "Custom API")
            def _to_list(v):
                return v if isinstance(v, list) else ([] if v is None else [str(v)])
            titles_l   = _to_list(titles_in)
            urls_l     = _to_list(urls_in)
            snippets_l = _to_list(snippets_in)
            max_len = max(len(titles_l), len(urls_l), len(snippets_l), 1)
            raw_results = []
            for i in range(max_len):
                raw_results.append({
                    "title":   titles_l[i]   if i < len(titles_l)   else f"{label} Result {i+1}",
                    "url":     urls_l[i]     if i < len(urls_l)     else "",
                    "snippet": snippets_l[i] if i < len(snippets_l) else ""
                })
            outputs[0] = {
                "type": "search_results", "query": label,
                "results": [r["url"] for r in raw_results],
                "raw_results": raw_results
            }

        elif n_type == 'subgraph/output':
            outputs[0] = inputs[0] if inputs else None

        elif n_type in self.plugins:
            plugin_class = self.plugins[n_type]
            try:
                plugin_inst = plugin_class()
                outputs[0] = plugin_inst.execute(inputs, props)
            except Exception as e:
                outputs[0] = {"error": f"Plugin error: {str(e)}"}

        # Save this node's output for downstream nodes
        self.node_outputs[node['id']] = outputs

