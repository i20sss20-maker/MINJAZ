#!/bin/sh
# Verify a FULL restore of a downloaded preview S3 backup in an isolated,
# temporary PostgreSQL 18 cluster. Never connect to the original database.
# The temporary PostgreSQL server has UNIX sockets only, zero TCP listeners.
set -eu
umask 077
if [ "$#" -ne 3 ]; then
  echo "RESTORE_VERIFY_REFUSED usage: archive expected_sha256 expected_bytes" >&2
  exit 4
fi
archive="$1"; expected_sha="$2"; expected_bytes="$3"
case "$expected_sha" in
  *[!a-f0-9]*|'') echo "RESTORE_VERIFY_REFUSED invalid sha" >&2; exit 4 ;;
esac
[ "${#expected_sha}" -eq 64 ] || { echo "RESTORE_VERIFY_REFUSED invalid sha length" >&2; exit 4; }
case "$expected_bytes" in
  *[!0-9]*|'') echo "RESTORE_VERIFY_REFUSED invalid byte count" >&2; exit 4 ;;
esac
[ -f "$archive" ] && [ ! -L "$archive" ] || { echo "RESTORE_VERIFY_REFUSED archive absent" >&2; exit 4; }
[ "$(wc -c < "$archive" | tr -d ' ')" = "$expected_bytes" ] || { echo "RESTORE_VERIFY_FAILED downloaded size mismatch" >&2; exit 5; }
[ "$(sha256sum "$archive" | cut -d' ' -f1)" = "$expected_sha" ] || { echo "RESTORE_VERIFY_FAILED downloaded hash mismatch" >&2; exit 5; }
[ "$expected_bytes" -ge 500 ] && [ "$expected_bytes" -le 536870912 ] || { echo "RESTORE_VERIFY_REFUSED archive outside size limits" >&2; exit 4; }
command -v su-exec >/dev/null || { echo "RESTORE_VERIFY_REFUSED postgres user switching unavailable" >&2; exit 4; }
pg_restore --list "$archive" >/dev/null || { echo "RESTORE_VERIFY_FAILED invalid archive" >&2; exit 5; }

work="$(mktemp -d /tmp/minjaz-verify-XXXXXXXX)"
chmod 700 "$work"
started=0
cleanup() {
  if [ "$started" -eq 1 ]; then
    su-exec postgres pg_ctl -D "$work/data" -m immediate -w stop >/dev/null 2>&1 || true
  fi
  rm -rf -- "$work"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir "$work/data" "$work/socket"
cp "$archive" "$work/restore.dump"
chown -R postgres:postgres "$work"
# Initialize a brand-new private cluster, not the Railway Postgres service.
su-exec postgres initdb -D "$work/data" -A trust --no-instructions >"$work/init.log" 2>&1 || {
  echo "RESTORE_VERIFY_FAILED temporary cluster init" >&2; exit 5;
}
cat >> "$work/data/postgresql.conf" <<EOF
listen_addresses = ''
unix_socket_directories = '$work/socket'
port = 7432
fsync = off
EOF
# The owned cluster/socket dirs are mode 0700; trust auth is local-only.
su-exec postgres pg_ctl -D "$work/data" -l "$work/server.log" -w start >"$work/start.log" 2>&1 || {
  echo "RESTORE_VERIFY_FAILED temporary cluster startup" >&2; exit 5;
}
started=1
su-exec postgres createdb -h "$work/socket" -p 7432 -U postgres minjaz_restore_verification
su-exec postgres pg_restore --exit-on-error --single-transaction --no-owner --no-privileges \
  -h "$work/socket" -p 7432 -U postgres -d minjaz_restore_verification \
  "$work/restore.dump" >"$work/restore.log" 2>&1 || {
  echo "RESTORE_VERIFY_FAILED archive cannot be fully restored" >&2; exit 6;
}
# Verify the core relational tables actually exist and can be queried.
# Caller selects the expected tables so the same verifier can be exercised
# in CI against synthetic data. No table contents or secrets are ever printed.
required="${RESTORE_EXPECT_TABLES:-users tasks proposals orders}"
table_count=0
for table in $required; do
  case "$table" in
    *[!a-z0-9_]*|'') echo "RESTORE_VERIFY_REFUSED invalid table name" >&2; exit 4 ;;
  esac
  count="$(su-exec postgres psql -X -q -t -A -v ON_ERROR_STOP=1 \
    -h "$work/socket" -p 7432 -U postgres -d minjaz_restore_verification \
    -c "select count(*) from public.$table" 2>/dev/null)" || {
    echo "RESTORE_VERIFY_FAILED missing or unreadable table $table" >&2; exit 6;
  }
  case "$count" in
    *[!0-9]*|'') echo "RESTORE_VERIFY_FAILED invalid row count for $table" >&2; exit 6 ;;
  esac
  table_count=$((table_count+1))
done
[ "$table_count" -ge 2 ] || { echo "RESTORE_VERIFY_REFUSED too few table assertions" >&2; exit 4; }
echo "RESTORE_VERIFY_OK source=downloaded_s3_bytes bytes=$expected_bytes checked_tables=$table_count isolated_cluster=yes"
