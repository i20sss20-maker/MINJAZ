"""One-time first-party MINJAZ service scope curation in dedicated sandbox only.

This curation intentionally excludes services requiring staff, live advertising,
audio/video production or other execution capability not yet verified. It does
not delete records or touch the independent freelancer marketplace taxonomy.
Future admin republishing is never overridden on subsequent deployments.
"""
import os
import psycopg2
from scripts.seed_minjaz_full_catalog_preview import CATALOG,SANDBOX_PROJECT_ID

APPROVED_SLUGS=frozenset([
    "landing-page",
    "corporate-website",
    "personal-portfolio",
    "booking-website",
    "blog-content-site",
    "multilingual-website",
    "website-redesign",
    "custom-web-platform",
    "android-app",
    "ios-app",
    "cross-platform-app",
    "mobile-uiux",
    "app-maintenance",
    "app-api-integration",
    "pwa-app",
    "ecommerce-setup",
    "woocommerce-store",
    "salla-zid-setup",
    "shopify-store",
    "product-catalog-setup",
    "checkout-ux-review",
    "logo-design",
    "visual-identity",
    "presentation-design",
    "website-maintenance",
    "speed-optimization",
    "bug-fixing",
    "hosting-deployment",
    "backup-recovery-setup",
    "accessibility-audit",
    "ai-chatbot",
    "ai-knowledge-assistant",
    "ai-content-workflow",
    "ai-customer-support",
    "ai-document-extraction",
    "ai-consultation",
    "website-copywriting",
    "product-descriptions",
    "proofreading",
    "workflow-automation",
    "crm-integration",
    "spreadsheet-automation",
    "notifications-integration",
    "api-connector",
    "forms-automation",
    "dashboard-business",
    "data-cleaning",
    "excel-reporting",
    "data-visualization",
    "database-design",
    "secure-code-review",
    "access-control-review",
    "product-discovery",
    "technical-roadmap",
    "ux-review",
    "architecture-review",
    "prototype-mvp-plan",
])
POLICY_VERSION="first-party-executable-only-v1"

def curate(cur):
    known={row[0] for row in CATALOG}
    if len(known)!=len(CATALOG) or not APPROVED_SLUGS<=known:
        raise RuntimeError("Curated service list inconsistent with existing catalog")
    cur.execute("""CREATE TABLE IF NOT EXISTS minjaz_preview_catalog_policy (
        version TEXT PRIMARY KEY,
        disabled_count INTEGER NOT NULL,
        applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")
    cur.execute("SELECT disabled_count FROM minjaz_preview_catalog_policy WHERE version=%s",
                (POLICY_VERSION,))
    saved=cur.fetchone()
    if saved is not None:return {"applied":False,"disabled":saved[0]}
    # Scope updates exclusively to packages added by the original generated
    # sandbox catalog. Never touch admin-created slugs or old demo packages.
    disabled=sorted(known-APPROVED_SLUGS)
    cur.execute("""UPDATE digital_service_packages SET active=FALSE, updated_at=NOW()
        WHERE slug=ANY(%s) AND active=TRUE""",(disabled,))
    count=cur.rowcount
    cur.execute("""INSERT INTO minjaz_preview_catalog_policy(version,disabled_count)
        VALUES (%s,%s)""",(POLICY_VERSION,count))
    return {"applied":True,"disabled":count}

def main():
    if (os.getenv("APP_ENV")!="preview"
        or os.getenv("RAILWAY_PROJECT_ID")!=SANDBOX_PROJECT_ID
        or os.getenv("MINJAZ_SERVICE_CURATE")!="enabled"):
        raise SystemExit("Refusing first-party curation outside dedicated MINJAZ sandbox")
    db_url=os.getenv("DATABASE_URL")
    if not db_url:raise SystemExit("DATABASE_URL required")
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as cur:
            result=curate(cur)
    print(f"[catalog-policy] reviewed={len(CATALOG)} approved={len(APPROVED_SLUGS)} "
          f"disabled_on_first_apply={result['disabled']} applied={result['applied']}")

if __name__=="__main__":
    main()
