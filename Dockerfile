FROM alpine:3.20
RUN apk add --no-cache python3 py3-psycopg2 postgresql-client
WORKDIR /launcher
COPY runtime_loader.py /launcher/runtime_loader.py
ENV PORT=3000
EXPOSE 3000
CMD ["python3","-u","/launcher/runtime_loader.py"]
