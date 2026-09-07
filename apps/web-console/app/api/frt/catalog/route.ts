import { NextResponse } from "next/server";

import { frtCatalog } from "../../../lib/frtCatalog.generated";

export const dynamic = "force-dynamic";

export function GET(request: Request) {
  const url = new URL(request.url);
  const batch = url.searchParams.get("batch")?.toLocaleUpperCase("en-US");
  const query = url.searchParams.get("query")?.trim().toLocaleLowerCase("zh-CN");
  const requestedLimit = Number.parseInt(url.searchParams.get("limit") ?? "100", 10);
  const limit = Number.isFinite(requestedLimit) ? Math.min(Math.max(requestedLimit, 1), 200) : 100;
  const skills = frtCatalog.skills.filter((skill) =>
    (!batch || skill.batch === batch)
    && (!query || `${skill.id} ${skill.name} ${skill.title} ${skill.description}`.toLocaleLowerCase("zh-CN").includes(query)),
  );
  return NextResponse.json({
    schemaVersion: frtCatalog.schemaVersion,
    package: frtCatalog.package,
    batchCount: frtCatalog.batchCount,
    skillCount: frtCatalog.skillCount,
    directedRouteCount: frtCatalog.directedRouteCount,
    matchedSkillCount: skills.length,
    skills: skills.slice(0, limit),
    evidenceBoundary: frtCatalog.evidenceBoundary,
  }, {
    headers: { "cache-control": "public, max-age=300, stale-while-revalidate=3600" },
  });
}
