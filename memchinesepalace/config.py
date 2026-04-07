"""配置管理"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


DEFAULT_PALACE_PATH = Path.home() / ".memchinesepalace" / "palace"
DEFAULT_CONFIG_PATH = Path.home() / ".memchinesepalace" / "config.json"


@dataclass
class Config:
    palace_path: str = str(DEFAULT_PALACE_PATH)
    chroma_collection: str = "memchinesepalace_du"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    default_dian: str = "通用"
    llm_provider: str = "openai"          # openai | anthropic | local
    llm_model: str = "gpt-4o-mini"
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None    # 本地模型端点
    use_llm_compression: bool = True
    use_rule_compression: bool = True     # 规则压缩作为回退
    auto_compress: bool = True
    max_wake_up_tokens: int = 200
    identity_file: Optional[str] = None  # ~/.memchinesepalace/identity.txt

    # 人名映射：全名→简称
    person_map: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, config_path: Path | str = DEFAULT_CONFIG_PATH) -> "Config":
        config_path = Path(config_path)
        if config_path.exists():
            with open(config_path) as f:
                data = json.load(f)
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

        # 从环境变量读取
        config = cls()
        if api_key := os.environ.get("OPENAI_API_KEY"):
            config.llm_api_key = api_key
        if api_key := os.environ.get("ANTHROPIC_API_KEY"):
            config.llm_api_key = api_key
            config.llm_provider = "anthropic"
            config.llm_model = "claude-haiku-4-5"
        if base_url := os.environ.get("LLM_BASE_URL"):
            config.llm_base_url = base_url
            config.llm_provider = "local"
        if palace_path := os.environ.get("MEMPALACE_PATH"):
            config.palace_path = palace_path
        return config

    def save(self, config_path: Path | str = DEFAULT_CONFIG_PATH) -> None:
        config_path = Path(config_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)

    @property
    def palace_path_obj(self) -> Path:
        return Path(self.palace_path)

    def get_identity(self) -> str:
        """读取身份文件（L0层）"""
        if self.identity_file:
            p = Path(self.identity_file)
            if p.exists():
                return p.read_text()
        default = Path.home() / ".memchinesepalace" / "identity.txt"
        if default.exists():
            return default.read_text()
        return ""
