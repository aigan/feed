# Processor base class (stub)

class Processor:
    @classmethod
    def ask_llm(
            cls,
            prompt: str,
            params: dict = None,
            *,
            model: str = 'gpt-4.1-mini',
            temperature: float = 0.8, # 0 to 2
            ) -> str:
        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI

        prompt_template = ChatPromptTemplate.from_template(prompt)
        llm = ChatOpenAI(model=model, temperature=temperature)
        chain = prompt_template | llm | StrOutputParser()
        return chain.invoke(params)

    @classmethod
    def preview_prompt(cls, prompt: str, params: dict) -> str:
        from langchain_core.prompts import ChatPromptTemplate
        template = ChatPromptTemplate.from_template(prompt)
        prompt_value = template.format_prompt(**(params or {}))
        return prompt_value.to_string()
