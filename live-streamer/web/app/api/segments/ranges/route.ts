import { DatabaseSync } from "node:sqlite";
import fs from "fs";
import path from "path";

const DB_PATH =
  process.env.DB_PATH ?? path.join(process.cwd(), "../server/segments.db");

const GAP_THRESHOLD_MS = 10_000;

interface SegmentRow {
  start_time: string;
  end_time: string;
}

interface CoverageRange {
  start: string;
  end: string;
}

function openDb(): { db: DatabaseSync; error?: never } | { db?: never; error: string } {
  if (!fs.existsSync(DB_PATH)) {
    return { error: `Database file not found: ${DB_PATH}` };
  }
  try {
    return { db: new DatabaseSync(DB_PATH, { open: true }) };
  } catch (e) {
    return { error: `Failed to open database at ${DB_PATH}: ${(e as Error).message}` };
  }
}

function mergeRanges(rows: SegmentRow[]): CoverageRange[] {
  if (rows.length === 0) return [];

  const ranges: CoverageRange[] = [];
  let rangeStart = rows[0].start_time;
  let rangeEnd = rows[0].end_time;

  for (let i = 1; i < rows.length; i++) {
    const segStart = new Date(rows[i].start_time).getTime();
    const prevEnd = new Date(rangeEnd).getTime();

    if (segStart - prevEnd <= GAP_THRESHOLD_MS) {
      rangeEnd = rows[i].end_time;
    } else {
      ranges.push({ start: rangeStart, end: rangeEnd });
      rangeStart = rows[i].start_time;
      rangeEnd = rows[i].end_time;
    }
  }
  ranges.push({ start: rangeStart, end: rangeEnd });
  return ranges;
}

export async function GET() {
  const result = openDb();

  if (!result.db) {
    console.error("[ranges]", result.error);
    return Response.json(
      { error: result.error, ranges: [], earliest: null, latest: null },
      { status: 503 }
    );
  }

  const db = result.db;
  try {
    const rows = db
      .prepare("SELECT start_time, end_time FROM segments ORDER BY start_time")
      .all() as unknown as SegmentRow[];

    const ranges = mergeRanges(rows);
    const earliest = rows.length > 0 ? rows[0].start_time : null;
    const latest = rows.length > 0 ? rows[rows.length - 1].end_time : null;

    return Response.json(
      { ranges, earliest, latest },
      { headers: { "Cache-Control": "public, max-age=30" } }
    );
  } catch (e) {
    console.error("[ranges] query failed:", (e as Error).message);
    return Response.json(
      { error: "Query failed", ranges: [], earliest: null, latest: null },
      { status: 500 }
    );
  } finally {
    db.close();
  }
}
