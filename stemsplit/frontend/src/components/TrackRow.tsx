import { Stem } from "../lib/api";
import { LoopState, TrackState } from "../lib/useMultitrack";
import { Waveform } from "./Waveform";

interface Props {
  stem: Stem;
  state: TrackState;
  audible: boolean;
  peaks: number[] | undefined;
  progress: number;
  duration: number;
  loop: LoopState;
  onChange: (patch: Partial<TrackState>) => void;
  onSeek: (fraction: number) => void;
  onDownload: () => void;
}

/** Um canal do mixer: nome, Mute, Solo, volume, download e forma de onda. */
export function TrackRow({ stem, state, audible, peaks, progress, duration, loop, onChange, onSeek, onDownload }: Props) {
  return (
    <div className="grid grid-cols-1 items-center gap-2 border-b border-neutral-800/70 py-3 last:border-0 md:grid-cols-[240px_1fr] md:gap-4">
      <div className="flex items-center gap-2">
        <span className="h-8 w-1.5 shrink-0 rounded-full" style={{ background: stem.color }} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium" title={stem.description || stem.label}>
            {stem.label}
          </div>
          <input
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={state.volume}
            onChange={(e) => onChange({ volume: Number(e.target.value) })}
            className="w-full"
            aria-label={`Volume de ${stem.label}`}
            title={`Volume: ${Math.round(state.volume * 100)}%`}
          />
        </div>
        <button
          onClick={() => onChange({ muted: !state.muted })}
          className={`h-8 w-8 rounded-md text-xs font-bold transition ${
            state.muted ? "bg-red-500 text-white" : "bg-neutral-800 text-neutral-400 hover:bg-neutral-700"
          }`}
          title="Mute (silenciar este canal)"
        >
          M
        </button>
        <button
          onClick={() => onChange({ solo: !state.solo })}
          className={`h-8 w-8 rounded-md text-xs font-bold transition ${
            state.solo ? "bg-yellow-400 text-neutral-900" : "bg-neutral-800 text-neutral-400 hover:bg-neutral-700"
          }`}
          title="Solo (ouvir só este canal)"
        >
          S
        </button>
        <button
          onClick={onDownload}
          className="h-8 w-8 rounded-md bg-neutral-800 text-neutral-300 transition hover:bg-neutral-700"
          title="Baixar este stem"
          aria-label={`Baixar ${stem.label}`}
        >
          ↓
        </button>
      </div>
      <Waveform
        peaks={peaks}
        color={stem.color}
        progress={progress}
        duration={duration}
        loop={loop}
        dimmed={!audible}
        onSeek={onSeek}
      />
    </div>
  );
}
