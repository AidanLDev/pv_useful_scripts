import HlsPlayer from "./HlsPlayer";

export default function Home() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-black p-8">
      <div className="w-full max-w-4xl">
        <h1 className="mb-4 text-2xl font-semibold text-white">Live Stream</h1>
        <HlsPlayer src="/api/hls/stream.m3u8" />
      </div>
    </div>
  );
}
