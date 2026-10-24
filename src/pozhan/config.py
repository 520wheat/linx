"""运行配置，全部来自环境变量。"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    case_path: str = "cases/golden-watch.yaml"
    api_key: str = ""  # 灵矽「我的模型」里填的 API 密钥；为空则不校验（仅限本地开发）
    llm_base_url: str = ""
    llm_api_key: str = ""
    intent_model: str = "deepseek/deepseek-v4-flash"
    suspect_model: str = "deepseek/deepseek-v4-flash"
    log_dir: str = "logs"

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        return cls(
            case_path=env.get("POZHAN_CASE", cls.case_path),
            api_key=env.get("POZHAN_API_KEY", ""),
            llm_base_url=env.get("LLM_BASE_URL", ""),
            llm_api_key=env.get("LLM_API_KEY", ""),
            intent_model=env.get("INTENT_MODEL", cls.intent_model),
            suspect_model=env.get("SUSPECT_MODEL", cls.suspect_model),
            log_dir=env.get("POZHAN_LOG_DIR", cls.log_dir),
        )

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_base_url and self.llm_api_key)
