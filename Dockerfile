FROM python:3.12-slim
WORKDIR /app

RUN pip install --no-cache-dir psycopg2-binary

COPY migrate.py storage.py server.py /app/
COPY database /app/database
COPY public /app/public
COPY tests /app/tests

RUN set -eux; \
    test "$(wc -c < server.py)" -gt 160000; \
    test "$(wc -c < public/index.html)" -gt 290000; \
    grep -q "ThreadingHTTPServer" server.py; \
    grep -q "/health" server.py; \
    grep -qi "<!doctype html" public/index.html; \
    test "$(find database/migrations -maxdepth 1 -name '*.sql' | wc -l)" -eq 10; \
    python -m py_compile server.py migrate.py storage.py

ENV PORT=3000
EXPOSE 3000

CMD ["sh","-c","python migrate.py && exec python -u server.py"]
