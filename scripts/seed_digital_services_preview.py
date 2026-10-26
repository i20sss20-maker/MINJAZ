"""Populate sample MINJAZ digital service packages in an isolated sandbox only.

This is not a migration. Never run against production.
"""
import os
import psycopg2

SAMPLES = [
    ("website-starter-demo", "website", "موقع تعريفي احترافي", "موقع متجاوب لعرض نشاطك وخدماتك وصفحات التواصل.", "1499.00", 7, 2),
    ("ecommerce-starter-demo", "ecommerce", "متجر إلكتروني متكامل", "واجهة متجر مع عرض المنتجات والسلة وتجربة طلب واضحة.", "3499.00", 14, 3),
    ("branding-starter-demo", "branding", "هوية بصرية للمشروع", "تصميم شعار وألوان وهوية أساسية متناسقة لنشاطك.", "899.00", 5, 2),
]

def main():
    if os.getenv("APP_ENV") != "preview" or os.getenv("MINJAZ_DEMO_SEED") != "enabled":
        raise SystemExit("Refusing demo seed outside explicitly enabled preview environment")
    if not os.getenv("RAILWAY_PROJECT_ID") or os.getenv("RAILWAY_PROJECT_ID") != "b64c32a3-e7d0-4f5c-8482-c0f43bc1f3f4":
        raise SystemExit("Refusing demo seed outside dedicated sandbox Railway project")
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL is required")
    with psycopg2.connect(db_url) as connection:
        with connection.cursor() as cur:
            for slug, category, title, description, price, days, revisions in SAMPLES:
                cur.execute("""INSERT INTO digital_service_packages
                    (slug, category, title_ar, description_ar, price_sar, delivery_days, revision_limit, active)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,TRUE)
                    ON CONFLICT (slug) DO NOTHING""",
                    (slug, category, title, description, price, days, revisions))
    print("[digital-services] sandbox demo packages seeded idempotently")

if __name__ == "__main__":
    main()
