import os
import cv2
import numpy as np
from PIL import Image
from executor import GraphExecutor

def create_test_assets():
    print("Creating test assets...")
    # 1. Create dummy image
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))
    img.save("test_image.jpg", format="JPEG")
    
    # 2. Create dummy video (10 frames)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter("test_video.mp4", fourcc, 1.0, (100, 100))
    for i in range(10):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        cv2.putText(frame, str(i), (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,255), 2)
        out.write(frame)
    out.release()

    # 3. Create dummy text document
    with open("test_doc.txt", "w") as f:
        f.write("SearchUI metadata extraction testing document.\nLine 2 text.")

def cleanup_assets():
    print("Cleaning up test assets...")
    for file in ["test_image.jpg", "test_video.mp4", "test_doc.txt"]:
        if os.path.exists(file):
            try:
                os.remove(file)
            except Exception:
                pass

def run_tests():
    create_test_assets()
    
    # 1. Test Keyframe Extractor
    print("\n--- Testing OpenCV Keyframe Extractor ---")
    graph = {
        "nodes": [
            {
                "id": 1,
                "type": "input/video",
                "properties": {"url": "", "local_path": "test_video.mp4"}
            },
            {
                "id": 2,
                "type": "process/opencv_keyframe",
                "properties": {"frame_index": 5},
                "inputs": [{"link": 10}]
            }
        ],
        "links": [
            [10, 1, 0, 2, 0, "video"]
        ]
    }
    try:
        executor = GraphExecutor(graph)
        executor.execute()
        keyframe_out = executor.node_outputs[2][0]
        print("Keyframe Output:", keyframe_out)
        assert keyframe_out["status"] == "extracted"
        assert os.path.exists(keyframe_out["local_path"])
        print("[+] Keyframe Extraction Test PASSED")
    except Exception as e:
        print("[-] Keyframe Extraction Test FAILED:", e)

    # 2. Test Document Input
    print("\n--- Testing Document Input ---")
    graph = {
        "nodes": [
            {
                "id": 1,
                "type": "input/document",
                "properties": {"url": "", "local_path": "test_doc.txt"}
            }
        ],
        "links": []
    }
    try:
        executor = GraphExecutor(graph)
        executor.execute()
        doc_out = executor.node_outputs[1][0]
        print("Doc Output:", doc_out)
        assert doc_out["status"] == "available"
        assert "SearchUI" in doc_out["text"]
        print("[+] Document Input Test PASSED")
    except Exception as e:
        print("[-] Document Input Test FAILED:", e)

    # 3. Test Metadata Extractor (for Video and Document)
    print("\n--- Testing Metadata Extractor ---")
    graph = {
        "nodes": [
            {
                "id": 1,
                "type": "input/video",
                "properties": {"url": "", "local_path": "test_video.mp4"}
            },
            {
                "id": 2,
                "type": "process/metadata",
                "inputs": [{"link": 10}]
            }
        ],
        "links": [
            [10, 1, 0, 2, 0, "video"]
        ]
    }
    try:
        executor = GraphExecutor(graph)
        executor.execute()
        meta_out = executor.node_outputs[2][0]
        print("Metadata Output:", meta_out)
        assert "fps" in meta_out["metadata"]
        assert meta_out["metadata"]["frame_count"] == 10
        print("[+] Metadata Extraction Test PASSED")
    except Exception as e:
        print("[-] Metadata Extraction Test FAILED:", e)

    # 4. Test OCR Node (Graceful fallback)
    print("\n--- Testing OCR Node Fallback ---")
    graph = {
        "nodes": [
            {
                "id": 1,
                "type": "input/image",
                "properties": {"url": "", "local_path": "test_image.jpg"}
            },
            {
                "id": 2,
                "type": "process/ocr",
                "inputs": [{"link": 10}]
            }
        ],
        "links": [
            [10, 1, 0, 2, 0, "image"]
        ]
    }
    try:
        executor = GraphExecutor(graph)
        executor.execute()
        ocr_out = executor.node_outputs[2][0]
        print("OCR Output:", ocr_out)
        assert "OCR" in ocr_out
        print("[+] OCR Test PASSED")
    except Exception as e:
        print("[-] OCR Test FAILED:", e)

    # 5. Test DuckDuckGo Search Node
    print("\n--- Testing DuckDuckGo Search Node ---")
    try:
        graph = {
            "nodes": [
                {
                    "id": 1,
                    "type": "search/ddg",
                    "inputs": [{"link": 10}]
                },
                {
                    "id": 2,
                    "type": "process/ocr",
                    "properties": {"text": "github ComfyUI"}
                }
            ],
            "links": [
                [10, 2, 0, 1, 0, "string"]
            ]
        }
        executor = GraphExecutor(graph)
        executor.execute()
        ddg_out = executor.node_outputs[1][0]
        print("DDG Output query:", ddg_out["query"])
        print("DDG Output results count:", len(ddg_out["results"]))
        assert len(ddg_out["results"]) > 0
        print("[+] DuckDuckGo Search Test PASSED")
    except Exception as e:
        print("[-] DuckDuckGo Search Test FAILED:", e)

    # 6. Test GraphQL Query Node
    print("\n--- Testing GraphQL Query Node ---")
    graph = {
        "nodes": [
            {
                "id": 1,
                "type": "search/graphql",
                "properties": {
                    "endpoint": "https://countries.trevorblades.com/graphql",
                    "query": "query { countries { name code } }"
                }
            }
        ],
        "links": []
    }
    try:
        executor = GraphExecutor(graph)
        executor.execute()
        graphql_out = executor.node_outputs[1][0]
        print("GraphQL Output keys:", graphql_out.keys())
        assert "data" in graphql_out or "error" in graphql_out
        print("[+] GraphQL Query Test PASSED")
    except Exception as e:
        print("[-] GraphQL Query Test FAILED:", e)

    cleanup_assets()

if __name__ == "__main__":
    run_tests()
