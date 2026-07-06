import os
import requests
import hashlib
from executor import GraphExecutor

def run_tests():
    print("=== STARTING INTEGRATION TESTS ===")
    
    # 1. Prepare dummy file
    dummy_content = b"searchui_test_data_" + os.urandom(8)
    dummy_filename = "test_image.png"
    with open(dummy_filename, "wb") as f:
        f.write(dummy_content)
    
    # Calculate expected hashes
    expected_md5 = hashlib.md5(dummy_content).hexdigest()
    expected_sha256 = hashlib.sha256(dummy_content).hexdigest()
    print(f"Dummy file MD5: {expected_md5}")
    print(f"Dummy file SHA-256: {expected_sha256}")
    
    # 2. Test File Upload Endpoint
    upload_url = "http://127.0.0.1:8000/upload"
    print(f"Uploading file to {upload_url}...")
    try:
        with open(dummy_filename, "rb") as f:
            r = requests.post(upload_url, files={"file": (dummy_filename, f, "image/png")})
        
        assert r.status_code == 200, f"Upload failed with status {r.status_code}"
        res = r.json()
        assert res.get("status") == "success", f"Upload API error: {res.get('message')}"
        
        uploaded_url = res.get("url")
        uploaded_local_path = res.get("local_path")
        print(f"Upload successful. URL: {uploaded_url}, Local Path: {uploaded_local_path}")
        assert os.path.exists(uploaded_local_path), "Uploaded file does not exist on disk"
    except Exception as e:
        print(f"[-] Upload Test FAILED: {e}")
        if os.path.exists(dummy_filename):
            os.remove(dummy_filename)
        return
        
    # 3. Test Graph Executor with MD5 Hashing
    print("\nTesting GraphExecutor with MD5 algorithm...")
    graph_md5 = {
        "nodes": [
            {
                "id": 1,
                "type": "input/image",
                "properties": {"url": uploaded_url, "local_path": uploaded_local_path},
                "outputs": [{"name": "Image", "type": "image", "links": [10]}]
            },
            {
                "id": 2,
                "type": "process/hash",
                "properties": {"algorithm": "md5"},
                "inputs": [{"name": "Media", "type": 0, "link": 10}],
                "outputs": [{"name": "Hash", "type": "hash", "links": [11]}]
            },
            {
                "id": 3,
                "type": "search/mock",
                "inputs": [{"name": "Query", "type": 0, "link": 11}],
                "outputs": [{"name": "Results", "type": "search_results", "links": [12]}]
            },
            {
                "id": 4,
                "type": "output/display",
                "inputs": [{"name": "Data", "type": 0, "link": 12}]
            }
        ],
        "links": [
            [10, 1, 0, 2, 0, "image"],
            [11, 2, 0, 3, 0, "hash"],
            [12, 3, 0, 4, 0, "search_results"]
        ]
    }
    
    try:
        executor_md5 = GraphExecutor(graph_md5)
        result_md5 = executor_md5.execute()
        
        print("MD5 Graph execution output:", result_md5)
        assert result_md5 is not None, "Execution returned None"
        assert result_md5.get("query_hash") == expected_md5, f"Expected MD5 {expected_md5}, got {result_md5.get('query_hash')}"
        print("[+] MD5 Execution Test PASSED")
    except Exception as e:
        print(f"[-] MD5 Execution Test FAILED: {e}")
        if os.path.exists(dummy_filename):
            os.remove(dummy_filename)
        return

    # 4. Test Graph Executor with SHA-256 Hashing
    print("\nTesting GraphExecutor with SHA-256 algorithm...")
    graph_sha = {
        "nodes": [
            {
                "id": 1,
                "type": "input/image",
                "properties": {"url": uploaded_url, "local_path": uploaded_local_path},
                "outputs": [{"name": "Image", "type": "image", "links": [10]}]
            },
            {
                "id": 2,
                "type": "process/hash",
                "properties": {"algorithm": "sha256"},
                "inputs": [{"name": "Media", "type": 0, "link": 10}],
                "outputs": [{"name": "Hash", "type": "hash", "links": [11]}]
            },
            {
                "id": 3,
                "type": "search/mock",
                "inputs": [{"name": "Query", "type": 0, "link": 11}],
                "outputs": [{"name": "Results", "type": "search_results", "links": [12]}]
            },
            {
                "id": 4,
                "type": "output/display",
                "inputs": [{"name": "Data", "type": 0, "link": 12}]
            }
        ],
        "links": [
            [10, 1, 0, 2, 0, "image"],
            [11, 2, 0, 3, 0, "hash"],
            [12, 3, 0, 4, 0, "search_results"]
        ]
    }
    
    try:
        executor_sha = GraphExecutor(graph_sha)
        result_sha = executor_sha.execute()
        
        print("SHA-256 Graph execution output:", result_sha)
        assert result_sha is not None, "Execution returned None"
        assert result_sha.get("query_hash") == expected_sha256, f"Expected SHA-256 {expected_sha256}, got {result_sha.get('query_hash')}"
        print("[+] SHA-256 Execution Test PASSED")
    except Exception as e:
        print(f"[-] SHA-256 Execution Test FAILED: {e}")
        if os.path.exists(dummy_filename):
            os.remove(dummy_filename)
        return

    # Cleanup
    if os.path.exists(dummy_filename):
        os.remove(dummy_filename)
    print("\n=== ALL INTEGRATION TESTS PASSED ===")

if __name__ == "__main__":
    run_tests()
