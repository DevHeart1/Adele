import { NextResponse } from "next/server";

import { checkDynamoHealth, getDynamoConfig } from "@/server/db/client";

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Unknown DynamoDB error";
}

export async function GET() {
  try {
    const health = await checkDynamoHealth();
    return NextResponse.json(health, {
      status: health.ok ? 200 : 503,
    });
  } catch (error) {
    const config = getDynamoConfig();
    return NextResponse.json(
      {
        ok: false,
        region: config.region,
        tableName: config.tableName,
        error: errorMessage(error),
      },
      { status: 503 },
    );
  }
}
