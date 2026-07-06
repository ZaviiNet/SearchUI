import os
import shutil
from vault import SecretsVault
from cache import SearchCache
from executor import GraphExecutor

def run_tests():
    # Write mock files for testing document inputs
    with open("a.txt", "w") as f:
        f.write("Antigravity OSINT SearchUI")
    with open("b.txt", "w") as f:
        f.write("Welcome to Antigravity SearchUI node graph editor")
    with open("err.txt", "w") as f:
        f.write("")

    # 1. Test Secrets Vault
    print("\n--- Testing Secrets Vault ---")
    try:
        vault = SecretsVault()
        vault.set_key("SerpApi", "super-secret-key-123")
        val = vault.get_key("SerpApi")
        print("Vault Value:", val)
        assert val == "super-secret-key-123"
        
        # Test listing services
        keys = vault.list_keys()
        print("Keys List:", keys)
        assert "SerpApi" in keys
        print("[+] Secrets Vault Test PASSED")
    except Exception as e:
        print("[-] Secrets Vault Test FAILED:", e)

    # 2. Test Search Cache
    print("\n--- Testing Search Cache ---")
    try:
        cache = SearchCache()
        cache.set_cached_result("search/ddg", "google query", {"results": ["http://google.com"]})
        cached = cache.get_cached_result("search/ddg", "google query")
        print("Cached Value:", cached)
        assert cached and cached["results"][0] == "http://google.com"
        print("[+] Search Cache Test PASSED")
    except Exception as e:
        print("[-] Search Cache Test FAILED:", e)

    # 3. Test Fallback Logic Node
    print("\n--- Testing Fallback Logic Node ---")
    try:
        # A is valid (a.txt), B is fallback (b.txt)
        graph = {
            "nodes": [
                {
                    "id": 1,
                    "type": "logic/fallback",
                    "inputs": [{"link": 10}, {"link": 11}]
                },
                {
                    "id": 2,
                    "type": "input/document",
                    "properties": {"local_path": "a.txt"}
                },
                {
                    "id": 3,
                    "type": "input/document",
                    "properties": {"local_path": "b.txt"}
                }
            ],
            "links": [
                [10, 2, 0, 1, 0, "document"],
                [11, 3, 0, 1, 1, "document"]
            ]
        }
        executor = GraphExecutor(graph)
        executor.execute()
        res = executor.node_outputs[1][0]
        print("Fallback output (A valid):", res["text"])
        assert res["text"] == "Antigravity OSINT SearchUI"
        
        # A is invalid (err.txt is empty, so evaluated as falsy in logic/fallback)
        graph["nodes"][1] = {
            "id": 2,
            "type": "input/document",
            "properties": {"local_path": "err.txt"}
        }
        executor = GraphExecutor(graph)
        executor.execute()
        res = executor.node_outputs[1][0]
        print("Fallback output (A is empty):", res["text"])
        assert res["text"] == "Welcome to Antigravity SearchUI node graph editor"
        print("[+] Fallback Logic Node Test PASSED")
    except Exception as e:
        print("[-] Fallback Logic Node Test FAILED:", e)

    # 4. Test Web Scraper Node (BeautifulSoup)
    print("\n--- Testing Web Scraper Node ---")
    try:
        # Test scraper with a fallback or cached value
        graph = {
            "nodes": [
                {
                    "id": 1,
                    "type": "search/scraper",
                    "properties": {"url": "http://example.com"}
                }
            ],
            "links": []
        }
        executor = GraphExecutor(graph)
        executor.execute()
        res = executor.node_outputs[1][0]
        print("Scraper output:", res[:60])
        assert len(res) > 0
        print("[+] Web Scraper Node Test PASSED")
    except Exception as e:
        print("[-] Web Scraper Node Test FAILED:", e)

    # 5. Test Match Confidence Node
    print("\n--- Testing Match Confidence Node ---")
    try:
        graph = {
            "nodes": [
                {
                    "id": 1,
                    "type": "process/confidence",
                    "inputs": [{"link": 10}, {"link": 11}]
                },
                {
                    "id": 2,
                    "type": "input/document",
                    "properties": {"local_path": "a.txt"}
                },
                {
                    "id": 3,
                    "type": "input/document",
                    "properties": {"local_path": "b.txt"}
                }
            ],
            "links": [
                [10, 2, 0, 1, 0, "document"],
                [11, 3, 0, 1, 1, "document"]
            ]
        }
        executor = GraphExecutor(graph)
        executor.execute()
        res = executor.node_outputs[1][0]
        print("Confidence Result:", res)
        # Query "Antigravity OSINT SearchUI" (words: antigravity, osint, searchui)
        # Matches against text. Match count: 2 ("antigravity", "searchui"). Score = 66%
        assert "66%" in res["score"]
        print("[+] Match Confidence Node Test PASSED")
    except Exception as e:
        print("[-] Match Confidence Node Test FAILED:", e)

    # 6. Test Export Node
    print("\n--- Testing Export Node ---")
    try:
        graph = {
            "nodes": [
                {
                    "id": 1,
                    "type": "output/export",
                    "properties": {"filename": "test_output.md"},
                    "inputs": [{"link": 10}]
                },
                {
                    "id": 2,
                    "type": "input/document",
                    "properties": {"local_path": "a.txt"}
                }
            ],
            "links": [
                [10, 2, 0, 1, 0, "document"]
            ]
        }
        executor = GraphExecutor(graph)
        executor.execute()
        res = executor.node_outputs[1][0]
        print("Export output:", res)
        assert res["status"] == "exported"
        assert os.path.exists(res["local_path"])
        
        if os.path.exists(res["local_path"]):
            os.remove(res["local_path"])
            
        print("[+] Export Node Test PASSED")
    except Exception as e:
        print("[-] Export Node Test FAILED:", e)

    # Cleanup files and databases
    for db in ["secrets.db", "cache.db", "vault.key"]:
        if os.path.exists(db):
            try:
                os.remove(db)
            except Exception:
                pass
    for txt in ["a.txt", "b.txt", "err.txt"]:
        if os.path.exists(txt):
            os.remove(txt)

if __name__ == "__main__":
    run_tests()
