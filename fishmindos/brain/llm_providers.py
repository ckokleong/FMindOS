"""
FishMindOS LLM 提供商适配器
支持智谱、OpenAI、Claude、Qwen、Gemini等多个AI提供商
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import json
import urllib.request
import urllib.error
from dataclasses import dataclass


@dataclass
class LLMMessage:
    """LLM消息"""
    role: str  # system, user, assistant, tool
    content: str
    tool_calls: Optional[List[Dict]] = None
    tool_call_id: Optional[str] = None


@dataclass
class LLMResponse:
    """LLM响应"""
    content: str
    tool_calls: Optional[List[Dict]] = None
    usage: Optional[Dict[str, int]] = None
    raw_response: Optional[Dict] = None


class LLMProvider(ABC):
    """LLM提供商基类"""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None, **kwargs):
        self.api_key = api_key
        self.base_url = base_url
        self.config = kwargs
    
    @abstractmethod
    def chat(self, messages: List[LLMMessage], tools: Optional[List[Dict]] = None, 
             temperature: float = 0.7, max_tokens: int = 2000) -> LLMResponse:
        """对话接口"""
        pass
    
    @abstractmethod
    def get_tool_definitions(self, skills: List[Dict]) -> List[Dict]:
        """获取工具定义格式"""
        pass


def _serialize_messages(messages: List[LLMMessage]) -> List[Dict[str, Any]]:
    """保留 multi-turn tool calling 所需的额外字段。"""
    serialized: List[Dict[str, Any]] = []
    for message in messages:
        payload: Dict[str, Any] = {
            "role": message.role,
            "content": message.content,
        }
        if message.tool_calls is not None:
            payload["tool_calls"] = message.tool_calls
        if message.tool_call_id:
            payload["tool_call_id"] = message.tool_call_id
        serialized.append(payload)
    return serialized


class ZhipuProvider(LLMProvider):
    """智谱AI提供商"""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None, model: str = "glm-4", **kwargs):
        super().__init__(api_key, base_url or "https://open.bigmodel.cn/api/paas/v4", **kwargs)
        self.model = model
    
    def chat(self, messages: List[LLMMessage], tools: Optional[List[Dict]] = None,
             temperature: float = 0.7, max_tokens: int = 2000) -> LLMResponse:
        """调用智谱API"""
        url = f"{self.base_url}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": _serialize_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        
        # 重试机制
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                with urllib.request.urlopen(req, timeout=self.config.get('timeout', 30)) as response:
                    result = json.loads(response.read().decode('utf-8'))
                    
                    choice = result['choices'][0]
                    message = choice['message']
                    
                    # 处理tool_calls - 确保格式正确
                    tool_calls = message.get('tool_calls')
                    if tool_calls:
                        # 转换为标准格式
                        formatted_tool_calls = []
                        for tc in tool_calls:
                            if isinstance(tc, dict):
                                func = tc.get('function', {})
                                # 确保arguments是字符串
                                arguments = func.get('arguments', '{}')
                                if isinstance(arguments, dict):
                                    arguments = json.dumps(arguments)
                                
                                formatted_tool_calls.append({
                                    'id': tc.get('id', ''),
                                    'type': 'function',
                                    'function': {
                                        'name': func.get('name', ''),
                                        'arguments': arguments
                                    }
                                })
                        tool_calls = formatted_tool_calls
                    
                    return LLMResponse(
                        content=message.get('content', ''),
                        tool_calls=tool_calls,
                        usage=result.get('usage'),
                        raw_response=result
                    )
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"[WARN] API调用失败，{retry_delay}秒后重试... ({attempt + 1}/{max_retries})")
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 指数退避
                else:
                    raise LLMError(f"智谱API调用失败: {e}")
    
    def get_tool_definitions(self, skills: List[Dict]) -> List[Dict]:
        """转换为智谱工具格式
        
        注意: skills 已经是标准格式 {"type": "function", "function": {...}}
        智谱AI支持OpenAI兼容的工具格式，直接返回即可
        """
        # 确保所有工具都有正确的格式
        tools = []
        for skill in skills:
            if "type" in skill and "function" in skill:
                # 已经是标准格式
                tools.append(skill)
            elif "name" in skill:
                # 简单格式，需要包装
                tools.append({
                    "type": "function",
                    "function": {
                        "name": skill["name"],
                        "description": skill.get("description", ""),
                        "parameters": skill.get("parameters", {})
                    }
                })
        return tools


class OpenAIProvider(LLMProvider):
    """OpenAI提供商"""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None, model: str = "gpt-4", **kwargs):
        super().__init__(api_key, base_url or "https://api.openai.com/v1", **kwargs)
        self.model = model
    
    def chat(self, messages: List[LLMMessage], tools: Optional[List[Dict]] = None,
             temperature: float = 0.7, max_tokens: int = 2000) -> LLMResponse:
        """调用OpenAI API"""
        url = f"{self.base_url}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": _serialize_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        
        try:
            with urllib.request.urlopen(req, timeout=self.config.get('timeout', 30)) as response:
                result = json.loads(response.read().decode('utf-8'))
                
                choice = result['choices'][0]
                message = choice['message']
                
                return LLMResponse(
                    content=message.get('content', ''),
                    tool_calls=message.get('tool_calls'),
                    usage=result.get('usage'),
                    raw_response=result
                )
        except Exception as e:
            raise LLMError(f"OpenAI API调用失败: {e}")
    
    def get_tool_definitions(self, skills: List[Dict]) -> List[Dict]:
        """转换为OpenAI工具格式（与智谱相同）"""
        # 确保所有工具都有正确的格式
        tools = []
        for skill in skills:
            if "type" in skill and "function" in skill:
                # 已经是标准格式
                tools.append(skill)
            elif "name" in skill:
                # 简单格式，需要包装
                tools.append({
                    "type": "function",
                    "function": {
                        "name": skill["name"],
                        "description": skill.get("description", ""),
                        "parameters": skill.get("parameters", {})
                    }
                })
        return tools


class ClaudeProvider(LLMProvider):
    """Claude (Anthropic) 提供商"""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None, model: str = "claude-3-opus-20240229", **kwargs):
        super().__init__(api_key, base_url or "https://api.anthropic.com/v1", **kwargs)
        self.model = model
    
    def chat(self, messages: List[LLMMessage], tools: Optional[List[Dict]] = None,
             temperature: float = 0.7, max_tokens: int = 2000) -> LLMResponse:
        """调用Claude API"""
        url = f"{self.base_url}/messages"
        
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        
        # 转换消息格式
        system_msg = None
        claude_messages = []
        for m in messages:
            if m.role == "system":
                system_msg = m.content
            else:
                claude_messages.append({
                    "role": m.role,
                    "content": m.content
                })
        
        payload = {
            "model": self.model,
            "messages": claude_messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }
        
        if system_msg:
            payload["system"] = system_msg
        
        if tools:
            payload["tools"] = tools
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        
        try:
            with urllib.request.urlopen(req, timeout=self.config.get('timeout', 30)) as response:
                result = json.loads(response.read().decode('utf-8'))
                
                content_blocks = result.get('content', [])
                text_content = ""
                tool_calls = []
                
                for block in content_blocks:
                    if block.get('type') == 'text':
                        text_content += block.get('text', '')
                    elif block.get('type') == 'tool_use':
                        tool_calls.append({
                            'id': block.get('id'),
                            'type': 'function',
                            'function': {
                                'name': block.get('name'),
                                'arguments': json.dumps(block.get('input', {}))
                            }
                        })
                
                return LLMResponse(
                    content=text_content,
                    tool_calls=tool_calls if tool_calls else None,
                    usage={
                        'prompt_tokens': result.get('usage', {}).get('input_tokens', 0),
                        'completion_tokens': result.get('usage', {}).get('output_tokens', 0)
                    },
                    raw_response=result
                )
        except Exception as e:
            raise LLMError(f"Claude API调用失败: {e}")
    
    def get_tool_definitions(self, skills: List[Dict]) -> List[Dict]:
        """转换为Claude工具格式"""
        tools = []
        for skill in skills:
            # 提取function定义
            if "function" in skill:
                func = skill["function"]
                tools.append({
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {})
                })
            elif "name" in skill:
                # 简单格式
                tools.append({
                    "name": skill["name"],
                    "description": skill.get("description", ""),
                    "input_schema": skill.get("parameters", {})
                })
        return tools


class QwenProvider(LLMProvider):
    """通义千问提供商"""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None, model: str = "qwen-turbo", **kwargs):
        super().__init__(api_key, base_url or "https://dashscope.aliyuncs.com/api/v1", **kwargs)
        self.model = model
    
    def chat(self, messages: List[LLMMessage], tools: Optional[List[Dict]] = None,
             temperature: float = 0.7, max_tokens: int = 2000) -> LLMResponse:
        """调用通义千问API"""
        url = f"{self.base_url}/services/aigc/text-generation/generation"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "input": {
                "messages": [{"role": m.role, "content": m.content} for m in messages]
            },
            "parameters": {
                "temperature": temperature,
                "max_tokens": max_tokens,
                "result_format": "message"
            }
        }
        
        if tools:
            payload["tools"] = tools
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        
        try:
            with urllib.request.urlopen(req, timeout=self.config.get('timeout', 30)) as response:
                result = json.loads(response.read().decode('utf-8'))
                
                output = result.get('output', {})
                message = output.get('choices', [{}])[0].get('message', {})
                
                tool_calls = message.get('tool_calls')
                if tool_calls:
                    # 转换为标准格式
                    tool_calls = [{
                        'id': tc.get('function', {}).get('name', ''),
                        'type': 'function',
                        'function': {
                            'name': tc.get('function', {}).get('name', ''),
                            'arguments': tc.get('function', {}).get('arguments', '{}')
                        }
                    } for tc in tool_calls]
                
                return LLMResponse(
                    content=message.get('content', ''),
                    tool_calls=tool_calls if tool_calls else None,
                    usage=result.get('usage'),
                    raw_response=result
                )
        except Exception as e:
            raise LLMError(f"通义千问API调用失败: {e}")
    
    def get_tool_definitions(self, skills: List[Dict]) -> List[Dict]:
        """转换为千问工具格式"""
        tools = []
        for skill in skills:
            if "type" in skill and "function" in skill:
                # 已经是标准格式
                tools.append(skill)
            elif "name" in skill:
                # 简单格式，需要包装
                tools.append({
                    "type": "function",
                    "function": {
                        "name": skill["name"],
                        "description": skill.get("description", ""),
                        "parameters": skill.get("parameters", {})
                    }
                })
        return tools


class GeminiProvider(LLMProvider):
    """Google Gemini提供商"""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None, model: str = "gemini-pro", **kwargs):
        super().__init__(api_key, base_url or "https://generativelanguage.googleapis.com/v1", **kwargs)
        self.model = model
    
    def chat(self, messages: List[LLMMessage], tools: Optional[List[Dict]] = None,
             temperature: float = 0.7, max_tokens: int = 2000) -> LLMResponse:
        """调用Gemini API"""
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        
        # 转换消息格式
        contents = []
        for m in messages:
            if m.role == "system":
                # Gemini使用systemInstruction字段
                continue
            contents.append({
                "role": "user" if m.role == "user" else "model",
                "parts": [{"text": m.content}]
            })
        
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens
            }
        }
        
        if tools:
            # Gemini的工具声明方式不同
            payload["tools"] = [{"function_declarations": [t["function"] for t in tools]}]
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={"Content-Type": "application/json"},
            method='POST'
        )
        
        try:
            with urllib.request.urlopen(req, timeout=self.config.get('timeout', 30)) as response:
                result = json.loads(response.read().decode('utf-8'))
                
                candidates = result.get('candidates', [])
                if not candidates:
                    return LLMResponse(content="")
                
                content = candidates[0].get('content', {})
                parts = content.get('parts', [])
                
                text_content = ""
                tool_calls = []
                
                for part in parts:
                    if 'text' in part:
                        text_content += part['text']
                    if 'functionCall' in part:
                        fc = part['functionCall']
                        tool_calls.append({
                            'id': fc.get('name', ''),
                            'type': 'function',
                            'function': {
                                'name': fc.get('name', ''),
                                'arguments': json.dumps(fc.get('args', {}))
                            }
                        })
                
                return LLMResponse(
                    content=text_content,
                    tool_calls=tool_calls if tool_calls else None,
                    usage=result.get('usageMetadata'),
                    raw_response=result
                )
        except Exception as e:
            raise LLMError(f"Gemini API调用失败: {e}")
    
    def get_tool_definitions(self, skills: List[Dict]) -> List[Dict]:
        """转换为Gemini工具格式"""
        tools = []
        for skill in skills:
            # 提取function定义
            if "function" in skill:
                func = skill["function"]
                tools.append({
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "parameters": func.get("parameters", {})
                })
            elif "name" in skill:
                # 简单格式
                tools.append({
                    "name": skill["name"],
                    "description": skill.get("description", ""),
                    "parameters": skill.get("parameters", {})
                })
        return tools


class LLMError(Exception):
    """LLM错误"""
    pass


class LLMFactory:
    """LLM工厂 - 根据配置创建对应的提供商"""
    
    PROVIDERS = {
        "zhipu": ZhipuProvider,
        "openai": OpenAIProvider,
        "claude": ClaudeProvider,
        "qwen": QwenProvider,
        "gemini": GeminiProvider,
    }
    
    @classmethod
    def create(cls, provider: str, api_key: str, **kwargs) -> LLMProvider:
        """
        创建LLM提供商实例
        
        Args:
            provider: 提供商名称
            api_key: API密钥
            **kwargs: 其他配置参数
            
        Returns:
            LLMProvider实例
        """
        provider_class = cls.PROVIDERS.get(provider.lower())
        if not provider_class:
            raise ValueError(f"不支持的LLM提供商: {provider}。支持的提供商: {list(cls.PROVIDERS.keys())}")
        
        return provider_class(api_key=api_key, **kwargs)
    
    @classmethod
    def list_providers(cls) -> List[str]:
        """列出所有支持的提供商"""
        return list(cls.PROVIDERS.keys())


def create_llm_provider(config) -> LLMProvider:
    """
    从配置创建LLM提供商
    
    Args:
        config: LLMConfig配置对象
        
    Returns:
        LLMProvider实例
    """
    return LLMFactory.create(
        provider=config.provider,
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
        timeout=config.timeout
    )
