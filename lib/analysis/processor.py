# Processor base class (stub)

class Processor:
    @classmethod
    def ask_llm(
            cls,
            prompt: str,
            params: dict = None,
            *,
            model: str = 'gpt-5-mini',
            temperature: float = None,
            reasoning_effort: str = None,
            ) -> str:
        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI

        prompt_template = ChatPromptTemplate.from_template(prompt)
        kwargs = dict(model=model)
        if temperature is not None:
            kwargs['temperature'] = temperature
        if reasoning_effort is not None:
            kwargs['reasoning_effort'] = reasoning_effort
        llm = ChatOpenAI(**kwargs)
        chain = prompt_template | llm | StrOutputParser()
        return chain.invoke(params)

    @classmethod
    def preview_prompt(cls, prompt: str, params: dict) -> str:
        from langchain_core.prompts import ChatPromptTemplate
        template = ChatPromptTemplate.from_template(prompt)
        prompt_value = template.format_prompt(**(params or {}))
        return prompt_value.to_string()
