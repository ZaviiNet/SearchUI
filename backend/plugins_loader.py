import os
import importlib.util
import inspect

class PluginNode:
    type = None  # e.g. 'custom/ip_reputation'
    
    def execute(self, inputs, properties):
        raise NotImplementedError("Plugins must override execute().")

def load_plugins():
    plugins = {}
    plugins_dir = os.path.join(os.path.dirname(__file__), "plugins")
    if not os.path.exists(plugins_dir):
        os.makedirs(plugins_dir, exist_ok=True)
        return plugins
        
    for filename in os.listdir(plugins_dir):
        if filename.endswith(".py") and filename != "__init__.py":
            module_name = filename[:-3]
            file_path = os.path.join(plugins_dir, filename)
            try:
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Scan module for subclasses of PluginNode
                for name, obj in inspect.getmembers(module):
                    if inspect.isclass(obj) and issubclass(obj, PluginNode) and obj is not PluginNode:
                        if obj.type:
                            plugins[obj.type] = obj
                            print(f"[+] Loaded plugin node '{obj.type}' from {filename}")
            except Exception as e:
                print(f"[-] Failed to load plugin {filename}: {e}")
                
    return plugins
