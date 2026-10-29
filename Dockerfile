FROM python:3.12-slim
WORKDIR /app

RUN pip install --no-cache-dir psycopg2-binary boto3

COPY migrate.py storage.py server.py minjaz_digital_services.py minjaz_digital_workflow.py minjaz_digital_deliverables.py minjaz_email_auth.py minjaz_account_auth.py minjaz_admin_claim.py /app/
COPY scripts /app/scripts
COPY database /app/database
COPY public /app/public
COPY tests /app/tests
COPY Dockerfile /app/Dockerfile
COPY Dockerfile.backup /app/Dockerfile.backup

RUN set -eux; \
    test "$(wc -c < server.py)" -gt 160000; \
    test "$(wc -c < public/index.html)" -gt 290000; \
    grep -q "ThreadingHTTPServer" server.py; \
    grep -q "/health" server.py; \
    grep -qi "<!doctype html" public/index.html; \
    migration_count="$(find database/migrations -maxdepth 1 -name '*.sql' | wc -l)"; \
    test "$migration_count" -ge 1; \
    test "$(find database/migrations -maxdepth 1 -name '*.sql' -printf '%f\n' | cut -d_ -f1 | sort | uniq -d | wc -l)" -eq 0; \
    python -m py_compile server.py migrate.py storage.py minjaz_digital_services.py minjaz_digital_workflow.py minjaz_digital_deliverables.py minjaz_email_auth.py minjaz_account_auth.py minjaz_admin_claim.py scripts/seed_digital_services_preview.py scripts/seed_minjaz_full_catalog_preview.py scripts/smoke_digital_services.py; \
    python -m unittest discover -s tests -p 'test_digital*.py' -v

ENV PORT=3000
EXPOSE 3000

CMD ["sh","-c","python migrate.py && if [ \"${APP_ENV:-}\" = \"preview\" ] && [ \"${MINJAZ_FULL_CATALOG_SEED:-}\" = \"enabled\" ]; then python scripts/seed_minjaz_full_catalog_preview.py; fi && exec python -u server.py"]
