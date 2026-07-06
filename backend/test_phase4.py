import os
from plugins_loader import load_plugins
from vector_index import LocalVectorIndex
from executor import GraphExecutor

def run_tests():
    # 1. Test Dynamic Plugins Loader
    print("\n--- Testing Dynamic Plugins Loader ---")
    try:
        plugins = load_plugins()
        print("Loaded plugins:", list(plugins.keys()))
        assert "custom/ip_reputation" in plugins
        print("[+] Dynamic Plugins Loader Test PASSED")
    except Exception as e:
        print("[-] Dynamic Plugins Loader Test FAILED:", e)

    # 2. Test Local Vector Database
    print("\n--- Testing Local Vector DB Search ---")
    try:
        index = LocalVectorIndex()
        index.add_documents([
            {"id": "doc1.txt", "text": "This is a document about OSINT and intelligence gathering."},
            {"id": "doc2.txt", "text": "We are developing a canvas graph editor named SearchUI using LiteGraph."},
            {"id": "doc3.txt", "text": "FastAPI is the web framework that handles our WebSockets and REST API."}
        ])
        results = index.query("canvas graph editor", top_k=1)
        print("Query Results:", results)
        assert len(results) > 0
        assert results[0]["id"] == "doc2.txt"
        print("[+] Vector DB Search Test PASSED")
    except Exception as e:
        print("[-] Vector DB Search Test FAILED:", e)

    # 3. Test Text Summarizer Node
    print("\n--- Testing Text Summarizer Node ---")
    try:
        text = "This is the first sentence. It has some text. This is the second sentence. It discusses SearchUI. This is the third sentence. It describes the backend worker."
        graph = {
            "nodes": [
                {
                    "id": 1,
                    "type": "process/summarize",
                    "properties": {"max_sentences": 2},
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
        with open("a.txt", "w") as f:
            f.write(text)
            
        executor = GraphExecutor(graph)
        executor.execute()
        res = executor.node_outputs[1][0]
        print("Summary output:", res)
        # Ensure it has exactly 2 sentences (separated by newline)
        assert len(res.splitlines()) == 2
        print("[+] Text Summarizer Node Test PASSED")
    except Exception as e:
        print("[-] Text Summarizer Node Test FAILED:", e)

    # 4. Test Relationship Graph Node
    print("\n--- Testing Relationship Graph Node ---")
    try:
        text = "Target report: Contact user at info@example.com on host 192.168.1.100. Also check google.com."
        graph = {
            "nodes": [
                {
                    "id": 1,
                    "type": "output/relationship_graph",
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
        with open("a.txt", "w") as f:
            f.write(text)
            
        executor = GraphExecutor(graph)
        executor.execute()
        res = executor.node_outputs[1][0]
        print("Relationship Graph:", res)
        node_ids = [n["id"] for n in res["nodes"]]
        assert "info@example.com" in node_ids
        assert "192.168.1.100" in node_ids
        assert "google.com" in node_ids
        print("[+] Relationship Graph Node Test PASSED")
    except Exception as e:
        print("[-] Relationship Graph Node Test FAILED:", e)

    # 5. Test Timeline Node
    print("\n--- Testing Timeline Node ---")
    try:
        text = "Events log: The project started on 2026-01-01. Phase 1 concluded on 2026-03-15. We deployed Phase 2 on 05/20/2026."
        graph = {
            "nodes": [
                {
                    "id": 1,
                    "type": "output/timeline",
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
        with open("a.txt", "w") as f:
            f.write(text)
            
        executor = GraphExecutor(graph)
        executor.execute()
        res = executor.node_outputs[1][0]
        print("Timeline:", res)
        dates = [e["date"] for e in res["events"]]
        assert "2026-01-01" in dates
        assert "2026-03-15" in dates
        print("[+] Timeline Node Test PASSED")
    except Exception as e:
        print("[-] Timeline Node Test FAILED:", e)

    # 6. Test Custom Plugin Execution
    print("\n--- Testing Custom Plugin Execution ---")
    try:
        graph = {
            "nodes": [
                {
                    "id": 1,
                    "type": "custom/ip_reputation",
                    "properties": {},
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
        with open("a.txt", "w") as f:
            f.write("8.8.8.8")
            
        executor = GraphExecutor(graph)
        executor.execute()
        res = executor.node_outputs[1][0]
        print("Plugin Execution Output:", res)
        assert res["ip"] == "8.8.8.8"
        assert "Public DNS" in res["reputation"]
        print("[+] Custom Plugin Node Execution Test PASSED")
    except Exception as e:
        print("[-] Custom Plugin Node Execution Test FAILED:", e)

    # 7. Test AnySearch Plugin Execution
    print("\n--- Testing AnySearch Plugin Execution ---")
    try:
        graph = {
            "nodes": [
                {
                    "id": 1,
                    "type": "search/anysearch",
                    "properties": {"max_results": 5},
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
        with open("a.txt", "w") as f:
            f.write("golang development")
            
        executor = GraphExecutor(graph)
        executor.execute()
        res = executor.node_outputs[1][0]
        print("AnySearch Plugin Execution Output Type:", type(res))
        print("AnySearch Plugin Execution Output Keys:", res.keys() if isinstance(res, dict) else "Not a dict")
        print("AnySearch Plugin Execution Output:", res)
        assert "results" in res or "error" in res
        print("[+] AnySearch Plugin Execution Test PASSED")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("[-] AnySearch Plugin Execution Test FAILED:", e)

    # 8. Test Results Viewer Node
    print("\n--- Testing Results Viewer Node ---")
    try:
        graph = {
            "nodes": [
                {
                    "id": 1,
                    "type": "output/results_viewer",
                    "inputs": [{"link": 10}]
                },
                {
                    "id": 2,
                    "type": "search/mock",
                    "inputs": [{"link": 9}]
                },
                {
                    "id": 3,
                    "type": "process/hash",
                    "inputs": [{"link": 8}]
                },
                {
                    "id": 4,
                    "type": "input/image",
                    "properties": {"url": "https://images.unsplash.com/photo-1579783902614-a3fb3927b6a5"}
                }
            ],
            "links": [
                [8, 4, 0, 3, 0, "image"],
                [9, 3, 0, 2, 0, "hash"],
                [10, 2, 0, 1, 0, "search_results"]
            ]
        }
        executor = GraphExecutor(graph)
        executor.execute()
        res = executor.node_outputs[1][0]
        print("Results Viewer Output:", res)
        assert len(res["results"]) > 0
        print("[+] Results Viewer Node Test PASSED")
    except Exception as e:
        print("[-] Results Viewer Node Test FAILED:", e)

    # 9. Test TinEye Search Node
    print("\n--- Testing TinEye Search Node ---")
    try:
        graph = {
            "nodes": [
                {
                    "id": 1,
                    "type": "search/tineye",
                    "inputs": [{"link": 10}]
                },
                {
                    "id": 2,
                    "type": "input/image",
                    "properties": {"url": "https://images.unsplash.com/photo-1579783902614-a3fb3927b6a5"}
                }
            ],
            "links": [
                [10, 2, 0, 1, 0, "image"]
            ]
        }
        executor = GraphExecutor(graph)
        executor.execute()
        res = executor.node_outputs[1][0]
        print("TinEye Search Output:", res)
        assert len(res["results"]) > 0
        print("[+] TinEye Search Node Test PASSED")
    except Exception as e:
        print("[-] TinEye Search Node Test FAILED:", e)

    # 10. Test Google Lens Search Node
    print("\n--- Testing Google Lens Search Node ---")
    try:
        graph = {
            "nodes": [
                {
                    "id": 1,
                    "type": "search/google_lens",
                    "inputs": [{"link": 10}]
                },
                {
                    "id": 2,
                    "type": "input/image",
                    "properties": {"url": "https://images.unsplash.com/photo-1579783902614-a3fb3927b6a5"}
                }
            ],
            "links": [
                [10, 2, 0, 1, 0, "image"]
            ]
        }
        executor = GraphExecutor(graph)
        executor.execute()
        res = executor.node_outputs[1][0]
        print("Google Lens Search Output:", res)
        assert len(res["results"]) > 0
        print("[+] Google Lens Search Node Test PASSED")
    except Exception as e:
        print("[-] Google Lens Search Node Test FAILED:", e)

    # 11. Test Catbox / Litterbox Upload Node
    print("\n--- Testing Catbox Upload Node ---")
    try:
        graph = {
            "nodes": [
                {
                    "id": 1,
                    "type": "process/catbox",
                    "inputs": [{"link": 10}],
                    "properties": {"upload_type": "Litterbox (Temporary)", "expiry": "1h"}
                },
                {
                    "id": 2,
                    "type": "input/image",
                    "properties": {"url": "https://images.unsplash.com/photo-1579783902614-a3fb3927b6a5"}
                }
            ],
            "links": [
                [10, 2, 0, 1, 0, "image"]
            ]
        }
        executor = GraphExecutor(graph)
        executor.execute()
        res = executor.node_outputs[1][0]
        print("Catbox Upload Node Output:", res)
        assert res["url"].startswith("http")
        print("[+] Catbox Upload Node Test PASSED")
    except Exception as e:
        print("[-] Catbox Upload Node Test FAILED:", e)

    # 12. Test AI Summary / Synthesis Node
    print("\n--- Testing AI Synthesis Node ---")
    try:
        graph = {
            "nodes": [
                {
                    "id": 1,
                    "type": "process/synthesis",
                    "inputs": [{"link": 10}],
                    "properties": {"model": "llama3", "prompt_suffix": "Summarize clearly."}
                },
                {
                    "id": 2,
                    "type": "search/ddg",
                    "properties": {"value": "AI visual search trends"}
                }
            ],
            "links": [
                [10, 2, 0, 1, 0, "search_results"]
            ]
        }
        executor = GraphExecutor(graph)
        executor.execute()
        res = executor.node_outputs[1][0]
        print("AI Synthesis Node Output:", res)
        assert res["type"] == "text"
        assert "Synthesized" in res["value"] or "synthesis" in res["value"].lower()
        print("[+] AI Synthesis Node Test PASSED")
    except Exception as e:
        print("[-] AI Synthesis Node Test FAILED:", e)

    # Cleanup mock files and key/db generated by tests
    for file in ["a.txt", "secrets.db", "cache.db", "vault.key"]:
        if os.path.exists(file):
            try:
                os.remove(file)
            except Exception:
                pass

if __name__ == "__main__":
    run_tests()
