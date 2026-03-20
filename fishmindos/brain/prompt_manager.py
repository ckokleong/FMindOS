"""
FishMindOS Agent 提示词管理器
加载和整合 Agent 定义文档，生成系统提示词
"""

from pathlib import Path
from typing import Dict, List, Optional
import json


class AgentPromptManager:
    """
    Agent提示词管理器
    管理 identity.md, agent.md, tools.md 等文档
    生成完整的系统提示词
    """
    
    def __init__(self, docs_dir: str = None):
        """
        初始化提示词管理器
        
        Args:
            docs_dir: 文档目录路径，默认使用项目根目录下的docs
        """
        if docs_dir is None:
            # 默认路径：项目根目录下的docs
            self.docs_dir = Path(__file__).parent.parent.parent / "docs"
        else:
            self.docs_dir = Path(docs_dir)
        
        self._cache: Dict[str, str] = {}
        self._load_all_docs()
    
    def _load_all_docs(self):
        """加载所有文档"""
        doc_files = {
            "identity": "identity.md",
            "agent": "agent.md",
            "tools": "tools.md",
            "prompt": "prompt.md",  # 新增：系统提示词
        }
        
        for key, filename in doc_files.items():
            filepath = self.docs_dir / filename
            if filepath.exists():
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        self._cache[key] = f.read()
                except Exception as e:
                    print(f"加载文档失败 {filepath}: {e}")
                    self._cache[key] = ""
            else:
                print(f"文档不存在: {filepath}")
                self._cache[key] = ""
    
    def get_identity(self) -> str:
        """获取身份定义"""
        return self._cache.get("identity", "")
    
    def get_agent(self) -> str:
        """获取Agent定义"""
        return self._cache.get("agent", "")
    
    def get_tools(self) -> str:
        """获取工具定义"""
        return self._cache.get("tools", "")
    
    def get_prompt(self) -> str:
        """获取系统提示词"""
        return self._cache.get("prompt", "")
    
    def generate_system_prompt(
        self,
        include_identity: bool = True,
        include_agent: bool = True,
        include_tools: bool = True,
        current_state: Optional[Dict] = None
    ) -> str:
        """
        生成完整的系统提示词
        
        Args:
            include_identity: 是否包含身份定义
            include_agent: 是否包含Agent定义
            include_tools: 是否包含工具定义
            current_state: 当前状态信息（位置、电量等）
            
        Returns:
            完整的系统提示词
        """
        sections = []
        
        # 1. 身份定义
        if include_identity:
            identity = self.get_identity()
            if identity:
                sections.append(f"# 身份定义\n\n{identity}")
        
        # 2. Agent定义
        if include_agent:
            agent = self.get_agent()
            if agent:
                sections.append(f"# Agent定义\n\n{agent}")
        
        # 3. 工具定义
        if include_tools:
            tools = self.get_tools()
            if tools:
                sections.append(f"# 工具定义\n\n{tools}")
        
        # 4. 当前状态（动态）
        if current_state:
            state_text = self._format_current_state(current_state)
            sections.append(f"# 当前状态\n\n{state_text}")
        
        # 组合所有部分
        prompt = "\n\n---\n\n".join(sections)
        
        # 添加最后的指令
        prompt += "\n\n---\n\n# 指令\n\n"
        prompt += "现在，用户将与你交互。请根据以上定义，以第一人称'我'回复用户，"
        prompt += "选择合适的工具完成任务，保持简洁友好的风格。"
        
        return prompt
    
    def _format_current_state(self, state: Dict) -> str:
        """格式化当前状态"""
        lines = []
        
        if "location" in state:
            lines.append(f"- **当前位置**: {state['location']}")
        
        if "battery" in state:
            lines.append(f"- **当前电量**: {state['battery']}%")
        
        if "carrying" in state:
            item = state['carrying']
            if item:
                lines.append(f"- **携带物品**: {item.get('name', '未知')} x{item.get('quantity', 1)}")
            else:
                lines.append(f"- **携带物品**: 无")
        
        if "nav_running" in state:
            status = "正在导航" if state['nav_running'] else "未在导航"
            lines.append(f"- **导航状态**: {status}")
        
        if "current_map" in state:
            lines.append(f"- **当前地图**: {state['current_map']}")
        
        if "charging" in state:
            status = "正在充电" if state['charging'] else "未充电"
            lines.append(f"- **充电状态**: {status}")
        
        return "\n".join(lines) if lines else "暂无状态信息"
    
    def reload_docs(self):
        """重新加载所有文档"""
        self._cache.clear()
        self._load_all_docs()
        print("OK 文档已重新加载")
    
    def get_doc_summary(self) -> Dict[str, int]:
        """
        获取文档摘要
        
        Returns:
            包含各文档字符数的字典
        """
        return {
            key: len(content) 
            for key, content in self._cache.items()
        }
    
    def validate_docs(self) -> List[str]:
        """
        验证文档完整性
        
        Returns:
            缺失的文档列表
        """
        missing = []
        
        required_docs = ["identity.md", "agent.md", "tools.md"]
        for doc in required_docs:
            filepath = self.docs_dir / doc
            if not filepath.exists():
                missing.append(str(filepath))
        
        return missing


def create_prompt_manager(docs_dir: str = None) -> AgentPromptManager:
    """工厂函数：创建提示词管理器"""
    return AgentPromptManager(docs_dir)


# 使用示例
if __name__ == "__main__":
    # 创建管理器
    manager = create_prompt_manager()
    
    # 验证文档
    missing = manager.validate_docs()
    if missing:
        print(f"WARN 缺失文档: {missing}")
    else:
        print("OK 所有文档已找到")
    
    # 生成系统提示词
    current_state = {
        "location": "26层大厅",
        "battery": 85,
        "carrying": None,
        "nav_running": False,
        "current_map": "26层"
    }
    
    prompt = manager.generate_system_prompt(current_state=current_state)
    
    # 输出生成的提示词（前500字符）
    print("\n生成的系统提示词（前500字符）:")
    print("=" * 60)
    print(prompt[:500])
    print("...")
    print("=" * 60)
    
    # 显示文档摘要
    print("\n文档摘要:")
    summary = manager.get_doc_summary()
    for doc, length in summary.items():
        print(f"  {doc}: {length} 字符")
