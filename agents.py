# agents.py — 智能体定义模块（优化版）
# Agent dataclass 定义于 models/agent.py
# 支持动态 Prompt 构建、版本管理和智能体注册

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime


# ==================== 增强的 Agent 数据类 ====================
@dataclass
class Agent:
    """智能体定义（增强版）
    
    支持：
    - 动态 Prompt 模板（运行时注入变量）
    - 元数据管理（版本、创建时间等）
    - 智能体分类和标签
    - Prompt 预处理和后处理钩子
    """
    
    # 基本信息
    name: str
    identity: str
    system_prompt: str
    
    # 元数据
    version: str = "1.0.0"
    description: str = ""
    tags: List[str] = field(default_factory=list)
    author: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # 动态变量（运行时注入）
    dynamic_variables: Dict[str, str] = field(default_factory=dict)
    
    # 钩子函数
    pre_process: Optional[Callable[[str], str]] = None   # Prompt 预处理
    post_process: Optional[Callable[[str], str]] = None  # 响应后处理
    
    # 模型偏好
    preferred_model: Optional[str] = None     # 推荐使用的模型
    preferred_task: str = "default"           # 推荐使用的 LLM 任务槽
    
    # 生成参数覆盖
    generation_overrides: Dict[str, Any] = field(default_factory=dict)
    
    def build_system_prompt(self, **kwargs) -> str:
        """构建系统提示词（注入动态变量）
        
        Args:
            **kwargs: 要注入的变量，如 dynamic_terms="术语表内容"
            
        Returns:
            注入变量后的完整系统提示词
        """
        prompt = self.system_prompt
        
        # 1. 注入动态变量占位符 {variable_name}
        all_vars = {**self.dynamic_variables, **kwargs}
        for key, value in all_vars.items():
            placeholder = f"{{{key}}}"
            if placeholder in prompt:
                prompt = prompt.replace(placeholder, str(value))
        
        # 2. 执行预处理钩子
        if self.pre_process:
            prompt = self.pre_process(prompt)
        
        return prompt.strip()
    
    def process_response(self, response: str) -> str:
        """处理模型响应
        
        Args:
            response: 原始模型响应
            
        Returns:
            处理后的响应
        """
        if self.post_process:
            return self.post_process(response)
        return response
    
    def with_variable(self, key: str, value: str) -> "Agent":
        """创建添加了动态变量的新 Agent 实例（不可变模式）
        
        Args:
            key: 变量名
            value: 变量值
            
        Returns:
            新的 Agent 实例
        """
        new_agent = Agent(
            name=self.name,
            identity=self.identity,
            system_prompt=self.system_prompt,
            version=self.version,
            description=self.description,
            tags=self.tags.copy(),
            author=self.author,
            dynamic_variables={**self.dynamic_variables, key: value},
            pre_process=self.pre_process,
            post_process=self.post_process,
            preferred_model=self.preferred_model,
            preferred_task=self.preferred_task,
            generation_overrides=self.generation_overrides.copy(),
        )
        return new_agent
    
    def with_generation_config(self, **kwargs) -> "Agent":
        """创建添加了生成参数覆盖的新 Agent 实例
        
        Args:
            **kwargs: 生成参数，如 temperature=0.1, max_tokens=4096
            
        Returns:
            新的 Agent 实例
        """
        new_agent = Agent(
            name=self.name,
            identity=self.identity,
            system_prompt=self.system_prompt,
            version=self.version,
            description=self.description,
            tags=self.tags.copy(),
            author=self.author,
            dynamic_variables=self.dynamic_variables.copy(),
            pre_process=self.pre_process,
            post_process=self.post_process,
            preferred_model=self.preferred_model,
            preferred_task=self.preferred_task,
            generation_overrides={**self.generation_overrides, **kwargs},
        )
        return new_agent


# ==================== 响应后处理函数 ====================
def _clean_translation_output(text: str) -> str:
    """清理翻译输出：移除翻译说明、代码块标记等"""
    import re
    
    # 移除常见的说明前缀
    patterns_to_remove = [
        r'^[译译]文[：:]\s*',           # "译文："
        r'^[翻翻]译[：:]\s*',            # "翻译："
        r'^以下是[^：:]*[：:]\s*',       # "以下是译文："
        r'^输出[：:]\s*',                # "输出："
        r'^结果[：:]\s*',                # "结果："
        r'\n*[\[\(]?注[：:释].*$',       # 末尾注释
    ]
    
    for pattern in patterns_to_remove:
        text = re.sub(pattern, '', text, flags=re.MULTILINE | re.IGNORECASE)
    
    # 移除 Markdown 代码块标记
    text = re.sub(r'```\w*\n?', '', text)
    
    return text.strip()


def _clean_epub_output(text: str) -> str:
    """清理 EPUB 编辑输出：确保是纯 XHTML"""
    import re
    
    # 移除 Markdown 代码块标记
    text = re.sub(r'```\w*\n?', '', text)
    text = re.sub(r'```$', '', text)
    
    # 移除解释说明（以非 XML 标签开头的行）
    if not text.strip().startswith('<'):
        # 尝试找到第一个 XML 标签
        match = re.search(r'<[^>]+>', text)
        if match:
            text = text[match.start():]
    
    return text.strip()


# ==================== 智能体定义 ====================

# --- 世界史翻译专家 ---
WORLD_HISTORY_EXPERT = Agent(
    name="世界史专家",
    identity="世界史专家，精通多国语言，专长于历史文献翻译",
    version="2.0.0",
    description="专精世界史学术文献的中英翻译，遵循严格的术语公约和学术文体规范",
    tags=["翻译", "历史", "学术", "中英"],
    
    # 推荐配置
    preferred_model="gpt-4o",  # 翻译任务推荐使用强模型
    preferred_task="translation",
    generation_overrides={
        "temperature": 0.1,    # 翻译需要低温度保证一致性
        "max_tokens": 4096,
        "top_p": 0.95,
    },
    
    # 后处理：清理翻译输出
    post_process=_clean_translation_output,
    
    system_prompt="""
你是「世界史翻译官」，精通英语与中文的世界史专家，拥有20年历史学术文献翻译经验。

## 核心规则

1. **准确完整**：严格忠实原文，不增译、不漏译、不曲解。长难句先拆解语法再重组为流畅中文。
2. **专有名词规范**：
   - 使用学界公认译名
   - 首次出现时括注原文及生卒年：「查士丁尼一世（Justinian I，约482–565）」
   - 不确定的译名保留原文并标注[译注：待核实]
3. **学术文体**：
   - 使用正式客观的书面语言
   - 保持原文逻辑结构和段落划分
   - 符合中文表达习惯，避免欧化长句
   - 被动语态可转为主动语态，但需保持学术严谨性
4. **术语一致**：严格遵循提供的术语公约，同一概念全书使用同一译法
5. **数字与日期**：
   - 年份、日期格式保持原文
   - 世纪表述统一为"XX世纪"
   - 大数字可使用"万""亿"单位

## 术语公约（运行时动态注入）
{dynamic_terms}

## 特殊处理

- **拉丁语/希腊语引文**：保留原文，括注中文大意
- **诗歌/铭文**：使用中文古典韵文风格，保留分行
- **注释引用**：保留原文脚注编号格式
- **书目引用**：保留原文格式不变

## 输出要求
- 只输出纯中文译文
- 不添加任何翻译说明、注释、总结或评论
- 保留原文段落分隔
- 输出中不包含任何代码块标记
"""
)

# --- EPUB 电子书编辑 ---
EPUB_EDITOR = Agent(
    name="EPUB编辑",
    identity="EPUB电子书编辑，擅长替换EPUB代码中的文本内容",
    version="2.0.0",
    description="精确替换 EPUB/XHTML 代码中的文本内容，完整保留所有标签和属性结构",
    tags=["EPUB", "XHTML", "编辑", "替换"],
    
    # 推荐配置
    preferred_model="gpt-4o",
    preferred_task="editing",
    generation_overrides={
        "temperature": 0.0,    # 编辑任务需要完全确定性
        "max_tokens": 8192,    # EPUB 内容可能较长
        "top_p": 1.0,
    },
    
    # 后处理：确保输出纯净 XHTML
    post_process=_clean_epub_output,
    
    system_prompt="""
你是「EPUB 工匠」，精通 XHTML/CSS 的电子书编辑专家。

## 唯一任务
将用户提供的新译文精确替换到源 EPUB 代码中，输出替换后的完整代码。

## 严格规则

### 1. 标签结构 — 完全不变
以下所有标签原样保留，不得修改、添加或删除：
- 块级：<p> <div> <blockquote> <section> <article> <aside> <header> <footer>
- 内联：<span> <em> <strong> <i> <b> <a> <abbr> <cite> <code> <q> <sub> <sup>
- 标题：<h1> ~ <h6>
- 列表：<ul> <ol> <li> <dl> <dt> <dd>
- 表格：<table> <thead> <tbody> <tr> <th> <td>
- 多媒体：<img> <audio> <video> <figure> <figcaption>

### 2. 属性 — 完全不变
所有属性值原样保留，不得修改：
- class, id, style
- epub:type, epub:prefix
- href, src, alt, title
- data-* 自定义属性
- xml:lang, lang
- role, aria-*

### 3. 文本替换规则
- **仅替换标签之间的文本节点**
- 中文使用全角标点：，。！？；：""''（）【】《》
- 英文/数字保留半角格式
- 专有名词保留括注格式：（Alexander the Great）（βασιλεύς）

### 4. 空白处理
- 保留原文的缩进和空行结构
- 标签之间换行保持原样
- 文本内容中多余空白需规范化

## 输出格式
直接输出替换后的完整 XHTML，不添加任何解释、代码块标记（```）、或说明文字。
"""
)

# --- 通用翻译助手（轻量版） ---
GENERAL_TRANSLATOR = Agent(
    name="通用翻译助手",
    identity="通用翻译助手，适用于非专业领域的日常翻译",
    version="1.0.0",
    description="轻量级通用翻译，适合简单文本快速翻译",
    tags=["翻译", "通用", "轻量"],
    
    preferred_model="gpt-3.5-turbo",  # 简单翻译可用便宜模型
    preferred_task="translation",
    generation_overrides={
        "temperature": 0.3,
        "max_tokens": 2048,
    },
    
    post_process=_clean_translation_output,
    
    system_prompt="""
你是专业翻译助手，精通中英互译。

## 规则
1. 忠实原文，准确完整
2. 语言流畅自然，符合目标语言表达习惯
3. 专业术语使用通用译名
4. 保持原文格式和分段

## 输出
只输出译文，不添加说明。
"""
)


# ==================== 智能体注册表 ====================
class AgentRegistry:
    """智能体注册表（支持查询、过滤、动态注册）"""
    
    def __init__(self):
        self._agents: Dict[str, Agent] = {}
        self._tags_index: Dict[str, List[str]] = {}  # tag -> agent names
    
    def register(self, agent: Agent):
        """注册智能体"""
        self._agents[agent.name] = agent
        
        # 更新标签索引
        for tag in agent.tags:
            if tag not in self._tags_index:
                self._tags_index[tag] = []
            if agent.name not in self._tags_index[tag]:
                self._tags_index[tag].append(agent.name)
    
    def get(self, name: str) -> Optional[Agent]:
        """按名称获取智能体"""
        return self._agents.get(name)
    
    def find_by_tag(self, tag: str) -> List[Agent]:
        """按标签查找智能体"""
        names = self._tags_index.get(tag, [])
        return [self._agents[name] for name in names if name in self._agents]
    
    def find_by_tags(self, tags: List[str], match_all: bool = False) -> List[Agent]:
        """按多个标签查找智能体
        
        Args:
            tags: 标签列表
            match_all: True=必须匹配所有标签，False=匹配任一标签
        """
        if match_all:
            # 交集
            name_sets = [set(self._tags_index.get(tag, [])) for tag in tags]
            if name_sets:
                common_names = name_sets[0].intersection(*name_sets[1:])
            else:
                common_names = set()
            return [self._agents[name] for name in common_names if name in self._agents]
        else:
            # 并集
            result = []
            seen = set()
            for tag in tags:
                for name in self._tags_index.get(tag, []):
                    if name not in seen and name in self._agents:
                        result.append(self._agents[name])
                        seen.add(name)
            return result
    
    def list_all(self) -> List[Agent]:
        """列出所有智能体"""
        return list(self._agents.values())
    
    def list_names(self) -> List[str]:
        """列出所有智能体名称"""
        return list(self._agents.keys())
    
    def get_by_task(self, preferred_task: str) -> List[Agent]:
        """按推荐任务查找智能体"""
        return [agent for agent in self._agents.values() 
                if agent.preferred_task == preferred_task]
    
    def remove(self, name: str) -> bool:
        """移除智能体"""
        if name in self._agents:
            agent = self._agents.pop(name)
            # 清理标签索引
            for tag in agent.tags:
                if tag in self._tags_index and name in self._tags_index[tag]:
                    self._tags_index[tag].remove(name)
            return True
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """获取注册表统计信息"""
        return {
            "total_agents": len(self._agents),
            "total_tags": len(self._tags_index),
            "agents_by_tag": {tag: len(names) for tag, names in self._tags_index.items()},
            "agents_by_task": {
                task: len([a for a in self._agents.values() if a.preferred_task == task])
                for task in set(a.preferred_task for a in self._agents.values())
            }
        }


# ==================== 全局注册表 ====================
# 创建全局注册表并注册默认智能体
_registry = AgentRegistry()
_registry.register(WORLD_HISTORY_EXPERT)
_registry.register(EPUB_EDITOR)
_registry.register(GENERAL_TRANSLATOR)


# ==================== 便捷函数 ====================
def get_agent(name: str) -> Optional[Agent]:
    """获取智能体（全局注册表）"""
    return _registry.get(name)


def get_agent_for_task(task: str) -> Optional[Agent]:
    """获取任务推荐的智能体"""
    agents = _registry.get_by_task(task)
    return agents[0] if agents else None


def register_agent(agent: Agent):
    """注册自定义智能体"""
    _registry.register(agent)


def list_agents() -> List[Agent]:
    """列出所有可用智能体"""
    return _registry.list_all()


def find_agents_by_tag(tag: str) -> List[Agent]:
    """按标签查找智能体"""
    return _registry.find_by_tag(tag)


def get_registry_stats() -> Dict[str, Any]:
    """获取注册表统计"""
    return _registry.get_stats()


# ==================== 向后兼容 ====================
# 保留原有的 AGENTS 字典以兼容旧代码
AGENTS = {
    agent.name: agent 
    for agent in _registry.list_all()
}