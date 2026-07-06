from plugins_loader import PluginNode

class IPReputationPlugin(PluginNode):
    type = "custom/ip_reputation"
    
    def execute(self, inputs, properties):
        ip_in = inputs[0] if inputs else ""
        
        ip = ""
        if isinstance(ip_in, dict):
            ip = ip_in.get("text") or ip_in.get("value") or ip_in.get("ip") or str(ip_in)
        else:
            ip = str(ip_in)
            
        ip = ip.strip()
        if not ip:
            return {"error": "No IP address provided"}
            
        reputation = "Low Risk"
        if ip.startswith("192.168.") or ip.startswith("127."):
            reputation = "Clean (Private Range)"
        elif ip.startswith("8.8.8."):
            reputation = "Clean (Public DNS)"
        else:
            reputation = "Medium Risk (Potential open relay)"
            
        return {
            "ip": ip,
            "reputation": reputation,
            "source": "Custom IP Reputation Plugin"
        }
