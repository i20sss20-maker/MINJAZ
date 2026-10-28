# Separate short-lived Railway cron image. Match the sandbox's PostgreSQL major.
FROM postgres:18-alpine
RUN apk add --no-cache aws-cli ca-certificates
COPY scripts/backup_minjaz_sandbox.sh /usr/local/bin/backup-minjaz
RUN chmod 0555 /usr/local/bin/backup-minjaz && sh -n /usr/local/bin/backup-minjaz
CMD ["/usr/local/bin/backup-minjaz"]
