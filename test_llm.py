
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.environ["GROQ_API_KEY"],
    base_url="https://api.groq.com/openai/v1"
)

response = client.chat.completions.create(
    model="openai/gpt-oss-120b",
    messages=[
        {
            "role": "system",
            "content": "You are an expert Python software engineer."
        },
        {
            "role": "user",
            "content": (
                "Find the bug in this Python code and return "
                "a corrected version:\n\n"
                "def divide(a, b):\n"
                "    return a / b\n\n"
                "Handle division by zero safely."
            )
        }
    ],
)

print(response.choices[0].message.content)
