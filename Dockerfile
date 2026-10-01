FROM alpine:3.20
RUN apk add --no-cache python3 py3-psycopg2 postgresql-client
WORKDIR /app
COPY minjaz_rc5_runtime.tgz /tmp/minjaz_rc5_runtime.tgz
RUN tar -xzf /tmp/minjaz_rc5_runtime.tgz -C /app \
    && rm /tmp/minjaz_rc5_runtime.tgz \
    && python3 -m py_compile /app/server.py /app/storage.py /app/migrate.py
ENV PORT=3000
EXPOSE 3000
CMD ["sh","-c","python3 /app/migrate.py && exec python3 /app/server.py"]
