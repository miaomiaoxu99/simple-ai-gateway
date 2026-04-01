from typing import Optional                                                                                                                               
                                                                                                                                                            
from .backend_interface import Backend                                                                                                                    
from .echo_backend import EchoBackend                                                                                                                    
from .modal_backend import ModalBackend                                                                                                                   
from .remote_backend import RemoteBackend
import logging                                                                                                                   

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BACKEND_LOGGER")

__all__ = [                                                                                                                                               
      "Backend",                                                                                                                                            
      "EchoBackend",                                                                                                                                        
      "ModalBackend",                                                                                                                                       
      "RemoteBackend",                                                                                                                                      
      "get_backend_instance",                                                                                                                               
  ]                                                                                                                                                         
                                                                                                                                                            
                                                                                                                                                            
def get_backend_instance(model_name: Optional[str], config: dict) -> Backend:                                                                             
    """                                                                                                                                                   
    Factory function to create the appropriate backend instance.                                                                                          
                                                                                                                                                            
    Args:                                                                                                                                                 
        model_name: The model/backend name from the request (e.g., "local", "modal")                                                                      
        config: The loaded configuration dictionary                                                                                                       
                                                                                                                                                            
    Returns:                                                                                                                                              
        A Backend instance based on the config                                                                                                            
                                                                                                                                                            
    Raises:                                                                                                                                               
        ValueError: If the backend type is unknown                                                                                                        
      """                                                                                                                                                   
    # 1. Look up the model in config, fall back to default if not found                                                                                   
    backend_cfg = config["backends"].get(model_name)                                                                                                      
    if not backend_cfg:
        logging.info("Config not found switching to default backend")                                                                                                                                   
        backend_cfg = config["backends"][config["default_backend"]]                                                                                       
                                                                                                                                                            
    b_type = backend_cfg.get("type")                                                                                                                      
    b_url = backend_cfg.get("url")                                                                                                                        
                                                                                                                                                            
    # 2. Map type string to backend class                                                                                                                 
    if b_type == "local":                                                                                                                                 
        return EchoBackend()                                                                                                                              
    elif b_type == "modal":                                                                                                                               
        return ModalBackend(url=b_url)                                                                                                                    
    elif b_type in ("vllm", "remote"):                                                                                                                    
        return RemoteBackend(url=b_url, model_name=backend_cfg.get("model_name"))                                                                                                                   
                                                                                                                                                            
    raise ValueError(f"Unknown backend type: {b_type}")