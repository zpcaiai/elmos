import { NextResponse } from "next/server";
import { pricingCatalog } from "../../lib/pricingCatalog";

export const dynamic = "force-static";

export function GET() {
  return NextResponse.json(pricingCatalog, {
    headers: {
      "Cache-Control": "public, max-age=300, stale-while-revalidate=3600",
      "X-ELMOS-Catalog-Version": pricingCatalog.catalogVersion,
    },
  });
}
