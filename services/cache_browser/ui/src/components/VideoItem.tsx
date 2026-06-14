import { useEffect, useRef } from "react";
import type { CacheItem } from "../types";

// Module-level set to track playing video elements
const playingVideos = new Set<HTMLVideoElement>();
const MAX_PLAYING = 4;

function formatDuration(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  return `${m}:${String(sec).padStart(2, "0")}`;
}

interface Props {
  item: CacheItem;
}

export function VideoItem({ item }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const src = `/proxy/video/cache/${item.hash}`;
  const isGif = item.mime_type === "image/gif";

  useEffect(() => {
    const video = videoRef.current;
    if (!video || isGif) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (entry.isIntersecting) {
          if (playingVideos.size < MAX_PLAYING && video.paused) {
            // Add synchronously before play() to prevent race when multiple
            // IntersectionObserver callbacks fire before any play event resolves
            playingVideos.add(video);
            video.play().catch(() => playingVideos.delete(video));
          }
        } else {
          if (!video.paused) {
            video.pause();
          }
        }
      },
      { threshold: 0.5 }
    );

    const handlePause = () => playingVideos.delete(video);

    video.addEventListener("pause", handlePause);
    observer.observe(video);

    return () => {
      observer.disconnect();
      video.removeEventListener("pause", handlePause);
      playingVideos.delete(video);
    };
  }, []);

  const handleFullscreen = () => {
    videoRef.current?.requestFullscreen().catch(() => undefined);
  };

  if (isGif) {
    return (
      <div className="rounded overflow-hidden bg-black group relative">
        <img
          src={src}
          alt={item.url ?? item.hash}
          className="w-full aspect-video object-contain"
          title={item.url ?? item.hash}
        />
        <div className="bg-gray-900 text-gray-300 px-2 py-1.5 text-xs truncate" title={item.filename ?? item.url ?? item.hash}>
          {item.filename ?? item.url ?? item.hash}
        </div>
      </div>
    );
  }

  return (
    <div className="rounded overflow-hidden bg-black group relative">
      <video
        ref={videoRef}
        src={src}
        preload="metadata"
        controls
        muted
        loop
        className="w-full aspect-video object-contain"
        title={item.url ?? item.hash}
      />
      <div className="bg-gray-900 text-gray-300 px-2 py-1.5 text-xs flex items-center justify-between gap-2">
        <span className="truncate" title={item.filename ?? item.url ?? item.hash}>
          {item.filename ?? item.url ?? item.hash}
        </span>
        <div className="flex items-center gap-2 shrink-0">
          {item.duration_s != null && (
            <span className="text-gray-500">{formatDuration(item.duration_s)}</span>
          )}
          <button
            onClick={handleFullscreen}
            className="text-gray-400 hover:text-white"
            title="Fullscreen"
          >
            ⤢
          </button>
        </div>
      </div>
    </div>
  );
}
