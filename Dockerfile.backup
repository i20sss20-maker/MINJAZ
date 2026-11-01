# Separate short-lived Railway cron image. Match the sandbox's PostgreSQL major.
FROM postgres:18-alpine
RUN apk add --no-cache aws-cli ca-certificates su-exec
COPY scripts/backup_minjaz_sandbox.sh /usr/local/bin/backup-minjaz
COPY scripts/verify_minjaz_backup_restore.sh /usr/local/bin/verify-minjaz-restore
RUN chmod 0555 /usr/local/bin/backup-minjaz /usr/local/bin/verify-minjaz-restore \
  && sh -n /usr/local/bin/backup-minjaz \
  && sh -n /usr/local/bin/verify-minjaz-restore \
  && command -v su-exec >/dev/null
CMD ["/usr/local/bin/backup-minjaz"]
