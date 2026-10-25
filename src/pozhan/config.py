"""运行配置，全部来自环境变量。"""

import json
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    cases_dir: str = "cases"  # 案件库目录（#53）
    case_path: str = ""  # 只玩这一个案子（调试或评测用）；设置了就不加载案件库
    api_key: str = ""  # 灵矽「我的模型」里填的 API 密钥；为空则不校验（仅限本地开发）
    screen_token: str = ""  # 陪玩屏的只读令牌；为空则不校验（仅限本地开发）
    linx_device: str = ""  # 网页开玩用的灵矽设备身份文件（#43）；为空则不开放网页开玩
    llm_base_url: str = ""
    llm_api_key: str = ""
    # 默认模型依据 #22 的评测：意图分类要快且准，嫌疑人要演得好
    intent_model: str = "doubao-seed-2.0-mini"
    suspect_model: str = "deepseek/deepseek-v4.1-flash"
    # 附加到每次模型请求里的参数。默认关闭思考：思考过程不出现在 content 里，会让首字延迟增加 2–3 秒（#22）
    llm_extra_body: dict = field(default_factory=lambda: {"thinking": {"type": "disabled"}})
    log_dir: str = "logs"
    log_requests: bool = False  # 记录平台发来的原始请求，用于核对请求格式

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        return cls(
            cases_dir=env.get("POZHAN_CASES", cls.cases_dir),
            case_path=env.get("POZHAN_CASE", ""),
            api_key=env.get("POZHAN_API_KEY", ""),
            screen_token=env.get("POZHAN_SCREEN_TOKEN", ""),
            linx_device=env.get("POZHAN_LINX_DEVICE", ""),
            llm_base_url=env.get("LLM_BASE_URL", ""),
            llm_api_key=env.get("LLM_API_KEY", ""),
            intent_model=env.get("INTENT_MODEL", cls.intent_model),
            suspect_model=env.get("SUSPECT_MODEL", cls.suspect_model),
            log_dir=env.get("POZHAN_LOG_DIR", cls.log_dir),
            log_requests=env.get("POZHAN_LOG_REQUESTS", "") in ("1", "true", "yes"),
            llm_extra_body=json.loads(env["LLM_EXTRA_BODY"])
            if env.get("LLM_EXTRA_BODY")
            else {"thinking": {"type": "disabled"}},
        )

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_base_url and self.llm_api_key)
