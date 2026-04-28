# Processor base class (stub)


class Conversation:
    def __init__(self, profile, **overrides):
        from langchain_openai import ChatOpenAI

        from config import LLM_PROFILES

        kwargs = {**LLM_PROFILES[profile], **overrides}
        self.llm = ChatOpenAI(**kwargs)
        self.messages = []

    def system(self, text):
        from langchain_core.messages import SystemMessage
        self.messages.append(SystemMessage(content=text))

    def ask(self, text):
        from langchain_core.messages import HumanMessage
        self.messages.append(HumanMessage(content=text))
        response = self.llm.invoke(self.messages)
        self.messages.append(response)
        return response.content


class Processor:
    @classmethod
    def ask_llm(
            cls,
            prompt: str,
            params: dict = None,
            *,
            profile: str,
            **overrides,
            ) -> str:
        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI

        from config import LLM_PROFILES

        kwargs = {**LLM_PROFILES[profile], **overrides}
        prompt_template = ChatPromptTemplate.from_template(prompt)
        llm = ChatOpenAI(**kwargs)
        chain = prompt_template | llm | StrOutputParser()
        return chain.invoke(params)

    @classmethod
    def conversation(cls, *, profile, **overrides):
        return Conversation(profile=profile, **overrides)

    @classmethod
    def preview_prompt(cls, prompt: str, params: dict) -> str:
        from langchain_core.prompts import ChatPromptTemplate
        template = ChatPromptTemplate.from_template(prompt)
        prompt_value = template.format_prompt(**(params or {}))
        return prompt_value.to_string()
