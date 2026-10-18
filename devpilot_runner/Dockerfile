# Build this controlled runner once; do NOT build arbitrary Dockerfiles from analyzed repos.
FROM python:3.12-slim
RUN python -m pip install --no-cache-dir \
    'pytest>=8,<10' 'langgraph>=0.3,<2' 'langchain-groq>=0.3,<2' 'python-dotenv>=1,<2'
WORKDIR /work
ENTRYPOINT ["python", "-m", "pytest"]
