from openai import OpenAI

from app.core.settings import settings


class LLMProvider:
    def __init__(self) -> None:
        self.provider = settings.llm_provider.lower().strip()
        if self.provider == "nvidia":
            self.base_url = settings.nvidia_base_url
            self.api_key = settings.nvidia_api_key
            self.model = settings.nvidia_model
        else:
            self.provider = "deepseek"
            self.base_url = settings.deepseek_base_url
            self.api_key = settings.deepseek_api_key
            self.model = settings.deepseek_model

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key != "replace_me" and self.model and self.model != "replace_me")

    def chat_json(self, system_prompt: str, user_prompt: str) -> str:
        if not self.is_configured():
            raise RuntimeError(f"LLM provider {self.provider} is not configured with a usable API key/model")

        try:
            client = OpenAI(base_url=self.base_url, api_key=self.api_key)
            response = client.chat.completions.create(
                model=self.model,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            content = response.choices[0].message.content
            if not content:
                raise RuntimeError("LLM returned empty content")
            return content
        except Exception as exc:
            raise RuntimeError(f"LLM request failed for provider={self.provider}, model={self.model}: {exc}") from exc
