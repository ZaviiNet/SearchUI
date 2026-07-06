import requests
import json
from plugins_loader import PluginNode
from vault import SecretsVault

class AnySearchPlugin(PluginNode):
    type = "search/anysearch"
    
    def execute(self, inputs, properties):
        query_in = inputs[0] if inputs else ""
        query_str = ""
        if isinstance(query_in, dict):
            query_str = query_in.get("value") or query_in.get("text") or query_in.get("query") or str(query_in)
        else:
            query_str = str(query_in)
            
        if not query_str:
            return {"error": "No query provided"}
            
        max_results = int(properties.get("max_results", 10))
        tag = properties.get("tag", "")
        
        # Retrieve credential from secrets vault
        vault = SecretsVault()
        api_key = vault.get_key("AnySearch")
        
        headers = {
            "Content-Type": "application/json"
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            
        payload = {
            "query": query_str,
            "max_results": max_results
        }
        if tag:
            payload["tag"] = tag
            
        url = "https://api.anysearch.com/v1/search"
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=15)
            if r.status_code == 200:
                res_json = r.json()
                data_part = res_json.get("data", {})
                # Normalize for SearchUI downstream compatibility (extracting url links)
                results_list = []
                for item in data_part.get("results", []):
                    # AnySearch items typically contain a 'url' key
                    url_val = item.get("url")
                    if url_val:
                        results_list.append(url_val)
                        
                return {
                    "type": "search_results",
                    "query": query_str,
                    "results": results_list,
                    "raw_results": data_part.get("results", []),
                    "metadata": data_part.get("metadata", {}),
                    "code": res_json.get("code"),
                    "message": res_json.get("message")
                }
            else:
                return {
                    "error": f"AnySearch API returned HTTP status {r.status_code}",
                    "detail": r.text
                }
        except Exception as e:
            # Fallback simulated response in case of API offline/network issues
            return {
                "type": "search_results",
                "query": query_str,
                "results": [
                    f"https://anysearch.com/mock-result-1?q={query_str}",
                    f"https://anysearch.com/mock-result-2?q={query_str}"
                ],
                "warning": f"Network execution failed: {str(e)}. Using simulated AnySearch output."
            }
