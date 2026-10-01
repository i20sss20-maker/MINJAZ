FROM alpine:3.20
RUN apk add --no-cache python3 py3-psycopg2 postgresql-client
WORKDIR /launcher
COPY runtime_loader.py minjaz_rc5_runtime.tgz minjaz_rc5_runtime.sha256 /launcher/
ENV PORT=3000
EXPOSE 3000
CMD ["python3","-u","/launcher/runtime_loader.py"]
