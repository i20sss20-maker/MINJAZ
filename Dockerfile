FROM alpine:3.20

RUN apk add --no-cache python3 py3-psycopg2 postgresql-client

WORKDIR /app
COPY runtime_src /src

RUN set -eux; \
    mkdir -p /app/public /app/database/migrations; \
    cat /src/server.parts/part*.txt > /app/server.py; \
    cat /src/public/index.parts/part*.txt > /app/public/index.html; \
    cp /src/migrate.py /app/migrate.py; \
    cp /src/storage.py /app/storage.py; \
    cp /src/public/icon.svg /app/public/icon.svg; \
    cp /src/public/manifest.webmanifest /app/public/manifest.webmanifest; \
    cp /src/public/sw.js /app/public/sw.js; \
    cp /src/database/migrations/*.sql /app/database/migrations/; \
    echo "488a785d0075bb7ca195dc76983e1c414b9c781e173e0f45e52dba89e2be18c6  /app/server.py" | sha256sum -c -; \
    echo "2543d61c398bcb62afcc49d715d763e4cdf1fed7b5e68029639aa17ca2b1235c  /app/public/index.html" | sha256sum -c -; \
    echo "b63bada96e425ab4a79f120405164667395fcc4c97b845de6b43a37aa528e9b1  /app/migrate.py" | sha256sum -c -; \
    echo "35290c9865268174455491ebde212d3e52b7c2e4d4343cd39c295297a028b1cc  /app/storage.py" | sha256sum -c -; \
    python3 -m py_compile /app/server.py /app/migrate.py /app/storage.py; \
    test "$(find /app/database/migrations -maxdepth 1 -name '*.sql' | wc -l)" -eq 10; \
    rm -rf /src

ENV PORT=3000
EXPOSE 3000

CMD ["sh","-c","python3 /app/migrate.py && exec python3 -u /app/server.py"]
