import { DatabaseSync } from "node:sqlite";
import fs from "fs";
import path from "path";

const DB_PATH =
  process.env.DB_PATH ?? path.join(process.cwd(), "../server/segments.db");

interface SegmentRow {
  filename: string;
  start_time: string;
  end_time: string;
  duration: number;
}

function openDb(): DatabaseSync | null {
  if (!fs.existsSync(DB_PATH)) {
    console.error("[vod] Database file not found:", DB_PATH);
    return null;
  }
  try {
    return new DatabaseSync(DB_PATH, { open: true });
  } catch (e) {
    console.error("[vod] Failed to open database:", (e as Error).message);
    return null;
  }
}

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const from = searchParams.get("from");

  if (!from) {
    return new Response("Missing ?from= parameter (ISO 8601)", { status: 400 });
  }

  const fromDate = new Date(from);
  if (isNaN(fromDate.getTime())) {
    return new Response("Invalid ?from= timestamp", { status: 400 });
  }

  const db = openDb();
  if (!db) {
    return new Response("Database not available", { status: 503 });
  }

  try {
    const rows = db
      .prepare(
        `SELECT filename, start_time, end_time, duration
         FROM segments
         WHERE end_time >= ?
         ORDER BY start_time
         LIMIT 300`
      )
      .all(fromDate.toISOString()) as unknown as SegmentRow[];

    if (rows.length === 0) {
      return new Response("No segments found after given time", { status: 404 });
    }

    // Time offset into the first segment where the user wants to start
    const firstSegStart = new Date(rows[0].start_time).getTime();
    const seekMs = fromDate.getTime() - firstSegStart;
    const timeOffset = Math.max(0, seekMs / 1000);

    const maxDuration = Math.ceil(
      Math.max(...rows.map((r) => r.duration)) + 1
    );

    const lines: string[] = [
      "#EXTM3U",
      "#EXT-X-VERSION:3",
      `#EXT-X-TARGETDURATION:${maxDuration}`,
      "#EXT-X-PLAYLIST-TYPE:VOD",
    ];

    if (timeOffset > 0) {
      lines.push(`#EXT-X-START:TIME-OFFSET=${timeOffset.toFixed(3)}`);
    }

    for (const row of rows) {
      lines.push(`#EXTINF:${row.duration.toFixed(6)},`);
      lines.push(`/api/hls/${row.filename}`);
    }

    lines.push("#EXT-X-ENDLIST");

    return new Response(lines.join("\n") + "\n", {
      headers: {
        "Content-Type": "application/vnd.apple.mpegurl",
        "Cache-Control": "no-cache",
      },
    });
  } catch (e) {
    console.error("[vod] query failed:", (e as Error).message);
    return new Response("Query failed", { status: 500 });
  } finally {
    db.close();
  }
}
