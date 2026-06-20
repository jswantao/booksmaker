# models/agent.py
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel

class Agent(BaseModel):
    name: str
    identity: str
    system_prompt: str
    tools: List[Union[str, Dict[str, Any]]] = []
    input_format: str = ""
    output_format: str = ""
    error_handling: Dict[str, str] = {}
    examples: Optional[List[Dict[str, str]]] = None
    batch_config: Optional[Dict[str, str]] = None
