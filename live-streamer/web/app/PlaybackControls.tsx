"use client";

interface PlaybackControlsProps {
  currentTime: Date;
  isPlaying: boolean;
  onPlay: () => void;
  onPause: () => void;
  /** direction: -1 = back one segment (~2s), +1 = forward one segment */
  onStep: (direction: -1 | 1) => void;
  onSkipToStart: () => void;
  onSkipToEnd: () => void;
}

function pad(n: number, len = 2) {
  return String(n).padStart(len, "0");
}

function formatTimestamp(d: Date): string {
  const day = pad(d.getDate());
  const month = pad(d.getMonth() + 1);
  const year = d.getFullYear();
  const h = pad(d.getHours());
  const m = pad(d.getMinutes());
  const s = pad(d.getSeconds());
  const ms = pad(d.getMilliseconds(), 3);
  return `${day}/${month}/${year} ${h}:${m}:${s}.${ms}`;
}

interface IconBtnProps {
  onClick: () => void;
  title: string;
  children: React.ReactNode;
}

function IconBtn({ onClick, title, children }: IconBtnProps) {
  return (
    <button
      onClick={onClick}
      title={title}
      className="flex items-center justify-center w-8 h-8 rounded text-gray-300 hover:text-white hover:bg-gray-700 transition-colors"
    >
      {children}
    </button>
  );
}

export default function PlaybackControls({
  currentTime,
  isPlaying,
  onPlay,
  onPause,
  onStep,
  onSkipToStart,
  onSkipToEnd,
}: PlaybackControlsProps) {
  return (
    <div className="flex items-center gap-1 px-3 py-1.5 bg-gray-900 border-t border-gray-700">
      {/* Skip to start */}
      <IconBtn onClick={onSkipToStart} title="Skip to start">
        <svg viewBox="0 0 24 24" className="w-4 h-4 fill-current">
          <path d="M6 6h2v12H6zm3.5 6 8.5 6V6z" />
        </svg>
      </IconBtn>

      {/* Step back one segment */}
      <IconBtn onClick={() => onStep(-1)} title="Previous segment">
        <svg viewBox="0 0 24 24" className="w-4 h-4 fill-current">
          <path d="M6 6h2v12H6zm3.5 6 8.5 6V6z" transform="scale(-1,1) translate(-24,0)" />
        </svg>
      </IconBtn>

      {/* Frame back */}
      <IconBtn onClick={() => onStep(-1)} title="Step back">
        <svg viewBox="0 0 24 24" className="w-4 h-4 fill-current">
          <path d="M11 18V6l-8.5 6 8.5 6zm.5-6 8.5 6V6z" />
        </svg>
      </IconBtn>

      {/* Play / Pause */}
      {isPlaying ? (
        <IconBtn onClick={onPause} title="Pause">
          <svg viewBox="0 0 24 24" className="w-5 h-5 fill-current">
            <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" />
          </svg>
        </IconBtn>
      ) : (
        <IconBtn onClick={onPlay} title="Play">
          <svg viewBox="0 0 24 24" className="w-5 h-5 fill-current">
            <path d="M8 5v14l11-7z" />
          </svg>
        </IconBtn>
      )}

      {/* Frame forward */}
      <IconBtn onClick={() => onStep(1)} title="Step forward">
        <svg viewBox="0 0 24 24" className="w-4 h-4 fill-current">
          <path d="M4 18l8.5-6L4 6v12zm9-12v12l8.5-6z" />
        </svg>
      </IconBtn>

      {/* Skip forward one segment */}
      <IconBtn onClick={() => onStep(1)} title="Next segment">
        <svg viewBox="0 0 24 24" className="w-4 h-4 fill-current">
          <path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z" />
        </svg>
      </IconBtn>

      {/* Skip to end */}
      <IconBtn onClick={onSkipToEnd} title="Skip to end">
        <svg viewBox="0 0 24 24" className="w-4 h-4 fill-current">
          <path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z" />
        </svg>
      </IconBtn>

      {/* Current timestamp */}
      <span className="ml-auto font-mono text-xs text-white bg-gray-800 px-2 py-0.5 rounded">
        {formatTimestamp(currentTime)}
      </span>
    </div>
  );
}
