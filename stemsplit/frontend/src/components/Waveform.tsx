import { useEffect, useRef } from "react";

interface Props {
  peaks: number[] | undefined;
  color: string;
  progress: number; // 0..1
  loop?: { a: number | null; b: number | null; enabled: boolean };
  duration: number;
  dimmed?: boolean;
  onSeek: (fraction: number) => void;
}

/** Desenha a forma de onda duas vezes (apagada e colorida) e revela a colorida até o ponto tocado.
 *  Assim os canvas são desenhados só uma vez e a animação é só a largura de uma div. */
export function Waveform({ peaks, color, progress, loop, duration, dimmed, onSeek }: Props) {
  const baseRef = useRef<HTMLCanvasElement>(null);
  const playedRef = useRef<HTMLCanvasElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const draw = () => {
      const box = boxRef.current;
      if (!box || !peaks?.length) return;
      const width = box.clientWidth;
      const height = box.clientHeight;
      const ratio = window.devicePixelRatio || 1;
      for (const [canvas, fill] of [
        [baseRef.current, "rgba(163,163,163,0.35)"],
        [playedRef.current, color],
      ] as const) {
        if (!canvas) continue;
        canvas.width = width * ratio;
        canvas.height = height * ratio;
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;
        const ctx = canvas.getContext("2d")!;
        ctx.scale(ratio, ratio);
        ctx.fillStyle = fill;
        const bars = Math.max(1, Math.floor(width / 3));
        const mid = height / 2;
        for (let i = 0; i < bars; i++) {
          const start = Math.floor((i / bars) * peaks.length);
          const end = Math.max(start + 1, Math.floor(((i + 1) / bars) * peaks.length));
          let peak = 0;
          for (let j = start; j < end; j++) peak = Math.max(peak, peaks[j]);
          const h = Math.max(1, peak * height * 0.95);
          ctx.fillRect(i * 3, mid - h / 2, 2, h);
        }
      }
    };
    draw();
    const observer = new ResizeObserver(draw);
    if (boxRef.current) observer.observe(boxRef.current);
    return () => observer.disconnect();
  }, [peaks, color]);

  const pct = (t: number | null) => (t === null || !duration ? 0 : (t / duration) * 100);

  return (
    <div
      ref={boxRef}
      className={`relative h-14 w-full cursor-pointer overflow-hidden rounded-md bg-neutral-950/60 transition-opacity ${
        dimmed ? "opacity-30" : ""
      }`}
      onClick={(e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        onSeek((e.clientX - rect.left) / rect.width);
      }}
      title="Clique para pular para este ponto"
    >
      {loop && loop.a !== null && loop.b !== null && (
        <div
          className={`absolute inset-y-0 ${loop.enabled ? "bg-brand-500/20" : "bg-neutral-500/10"}`}
          style={{ left: `${pct(loop.a)}%`, width: `${pct(loop.b) - pct(loop.a)}%` }}
        />
      )}
      <canvas ref={baseRef} className="absolute inset-0" />
      <div className="absolute inset-y-0 left-0 overflow-hidden" style={{ width: `${progress * 100}%` }}>
        <canvas ref={playedRef} className="absolute inset-y-0 left-0" />
      </div>
      <div className="absolute inset-y-0 w-px bg-white/80" style={{ left: `${progress * 100}%` }} />
      {!peaks && <div className="absolute inset-0 animate-pulse bg-neutral-800/50" />}
    </div>
  );
}
