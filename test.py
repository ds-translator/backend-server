from openai import OpenAI

client = OpenAI(
    base_url = 'http://localhost:11434/v1',
    api_key='ollama', # required, but unused
)

response = client.chat.completions.create(
  model="gemma:2b",
  messages=[
                            {
                                    "role": "system",
                                    "content": "You are professional translator.",
                                },
                                {
                                    "role": "user",
                                    "content": "translate this sentence to french language and only output the sentence:. Please translate this:\n\n"
                                    + "Thank you for your attention"
                                    + "\n\nTranslation:",
                                },
  ]
)
print(response.choices[0].message.content)