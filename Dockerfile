FROM python:3.12-slim-trixie
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /code/app

COPY . /code/app/

RUN uv sync

CMD ["uv", "run", "uvicorn", "app.fast_api:app", "--host", "0.0.0.0", "--port", "8000"]

