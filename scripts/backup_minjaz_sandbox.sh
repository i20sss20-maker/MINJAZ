#!/bin/sh
# MINJAZ preview daily logical backup. Short-lived Railway cron, no public port.
# Never modify the source database or write secrets to stdout.
set -eu
umask 077
: "${DATABASE_URL:?Database connection missing}"
: "${BACKUP_ENDPOINT:?Private S3 endpoint missing}"
: "${BACKUP_BUCKET:?Private S3 bucket missing}"
: "${AWS_ACCESS_KEY_ID:?S3 access key missing}"
: "${AWS_SECRET_ACCESS_KEY:?S3 secret missing}"
: "${AWS_DEFAULT_REGION:?S3 region missing}"
: "${APP_ENV:?Environment missing}"
if [ "$APP_ENV" != "preview" ]; then
  echo "BACKUP_REFUSED non-preview environment" >&2
  exit 4
fi
case "$BACKUP_ENDPOINT" in
  https://*) ;;
  *) echo "BACKUP_REFUSED endpoint must be HTTPS" >&2; exit 4 ;;
esac
# Check that pg_dump is new enough for the source. A newer Postgres image
# should not silently dump a database started by a future unsupported version.
pg_dump --version
date_stamp="$(date -u +%Y%m%dT%H%M%SZ)"
key="minjaz/preview/postgresql18/${date_stamp}.dump"
file="$(mktemp /tmp/minjaz-preview-XXXXXXXX.dump)"
trap 'rm -f "$file"' EXIT HUP INT TERM
echo "BACKUP_START ${date_stamp}"
pg_dump --dbname="$DATABASE_URL" --format=custom --compress=6 --no-owner --no-privileges --file="$file"
pg_restore --list "$file" >/dev/null
size="$(wc -c < "$file" | tr -d ' ')"
# Refuse suspicious empty dumps and unexpectedly huge uploads.
if [ "$size" -lt 500 ] || [ "$size" -gt 536870912 ]; then
  echo "BACKUP_REFUSED invalid dump size" >&2; exit 4
fi
sha="$(sha256sum "$file" | cut -d' ' -f1)"
# The AWS CLI writes directly to the private bucket; never mark an upload
# successful until the remote object metadata and byte length are verified.
aws --endpoint-url "$BACKUP_ENDPOINT" s3api put-object \
  --bucket "$BACKUP_BUCKET" --key "$key" --body "$file" \
  --content-type application/octet-stream \
  --metadata "sha256=$sha" --no-cli-pager >/dev/null
remote_size="$(aws --endpoint-url "$BACKUP_ENDPOINT" s3api head-object \
  --bucket "$BACKUP_BUCKET" --key "$key" \
  --query ContentLength --output text --no-cli-pager)"
remote_sha="$(aws --endpoint-url "$BACKUP_ENDPOINT" s3api head-object \
  --bucket "$BACKUP_BUCKET" --key "$key" \
  --query Metadata.sha256 --output text --no-cli-pager)"
if [ "$remote_size" != "$size" ] || [ "$remote_sha" != "$sha" ]; then
  echo "BACKUP_ERROR remote object metadata mismatch" >&2
  exit 5
fi
echo "BACKUP_OK key=$key bytes=$size sha256=$sha"
# No automatic deletion: retention must be reviewed before enabling it.
# Note: pg_restore --list checks archive structure, not full restore. Restore
# drills must happen against an isolated database; never restore over live.
