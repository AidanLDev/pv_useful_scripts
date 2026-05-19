import { readFile } from "fs/promises";
import path from "path";

const HLS_DIR = "/tmp/hls";

const MIME: Record<string, string> = {
  ".m3u8": "application/vnd.apple.mpegurl",
  ".ts": "video/mp2t",
};

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path: segments } = await params;
  const filePath = path.join(HLS_DIR, ...segments);

  if (!filePath.startsWith(path.resolve(HLS_DIR))) {
    return new Response("Forbidden", { status: 403 });
  }

  const ext = path.extname(filePath);
  const contentType = MIME[ext] ?? "application/octet-stream";

  try {
    const data = await readFile(filePath);
    return new Response(data, {
      headers: {
        "Content-Type": contentType,
        "Cache-Control": "no-cache",
      },
    });
  } catch {
    return new Response("Not found", { status: 404 });
  }
}
