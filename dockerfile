# temp stage
FROM python:3.12.2-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc build-essential tini

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY ["requirements.txt", "./"]

RUN pip install -r requirements.txt

COPY ["main.py", "/app/"]

# final stage
FROM python:3.12.2-slim AS deploy 

COPY --from=builder /usr/bin/tini /usr/bin/tini

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

COPY --from=builder /app ./

ENV PATH="/opt/venv/bin:$PATH"

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]