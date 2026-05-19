import { readFile } from "fs/promises";
import { existsSync } from "fs";
import { spawn } from "child_process";
import path from "path";

const HLS_DIR = "/tmp/hls";

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

  // .ts requested — remux the stored .h264 on-the-fly (no .ts written to disk)
  if (ext === ".ts") {
    const h264Path = filePath.replace(/\.ts$/, ".h264");
    if (!existsSync(h264Path)) {
      return new Response("Not found", { status: 404 });
    }

    const ffmpeg = spawn("ffmpeg", [
      "-i", h264Path,
      "-c", "copy",
      "-f", "mpegts",
      "pipe:1",
    ]);

    const stream = new ReadableStream({
      start(controller) {
        ffmpeg.stdout.on("data", (chunk: Buffer) => controller.enqueue(chunk));
        ffmpeg.stdout.on("end", () => controller.close());
        ffmpeg.stderr.on("data", () => {}); // suppress ffmpeg logs
        ffmpeg.on("error", (err) => controller.error(err));
      },
      cancel() {
        ffmpeg.kill();
      },
    });

    return new Response(stream, {
      headers: {
        "Content-Type": "video/mp2t",
        "Cache-Control": "no-cache",
      },
    });
  }

  // .m3u8 and anything else — serve directly from disk
  const MIME: Record<string, string> = {
    ".m3u8": "application/vnd.apple.mpegurl",
  };

  try {
    const data = await readFile(filePath);
    return new Response(data, {
      headers: {
        "Content-Type": MIME[ext] ?? "application/octet-stream",
        "Cache-Control": "no-cache",
      },
    });
  } catch {
    return new Response("Not found", { status: 404 });
  }
}
