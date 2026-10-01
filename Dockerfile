FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir psycopg2-binary
COPY . /app
RUN cat server.parts/part*.txt > server.py \
 && cat public/index.parts/part*.txt > public/index.html \
 && sha256sum -c source.sha256 \
 && rm -rf server.parts public/index.parts \
 && python -m py_compile server.py migrate.py storage.py
ENV PORT=3000
EXPOSE 3000
CMD ["sh","-c","python migrate.py && exec python -u server.py"]
