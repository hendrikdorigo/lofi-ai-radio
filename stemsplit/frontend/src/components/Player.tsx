import { useEffect, useMemo, useState } from "react";
import { api, downloadUrl, Health, Job } from "../lib/api";
import { formatDuration, formatTime, MODE_LABELS, transposeKey } from "../lib/format";
import { isAudible, useMultitrack } from "../lib/useMultitrack";
import { TrackRow } from "./TrackRow";

interface Props {
  job: Job;
  health: Health | null;
  onJobChange: (job: Job) => void;
}

const FORMAT_KEY = "stemsplit.formato";

function loadFormat(): string {
  try {
    return localStorage.getItem(FORMAT_KEY) || "wav24";
  } catch {
    return "wav24";
  }
}

export function Player({ job, health, onJobChange }: Props) {
  const [semitones, setSemitones] = useState(0);
  const [pendingSemitones, setPendingSemitones] = useState(0);
  const [format, setFormat] = useState(loadFormat);
  const [peaks, setPeaks] = useState<Record<string, number[]>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const mt = useMultitrack(job.id, job.stems, semitones, job.revision ?? 0);

  useEffect(() => {
    api.peaks(job.id, job.revision ?? 0).then(setPeaks).catch(() => setPeaks({}));
  }, [job.id, job.revision]);

  useEffect(() => {
    setSemitones(0);
    setPendingSemitones(0);
  }, [job.id]);

  const canResplit = job.stems.some((s) => s.name === "guitarra_solo");
  const canRedoVocals = job.mode === "detalhado" && job.vocal_quality !== "melhor";
  const redoVocals = () => {
    if (
      !confirm(
        "Refazer a separação entre voz principal e backing vocals com o modelo de melhor qualidade?\n\n" +
          "Em computador sem placa de vídeo leva bem mais tempo — algo como 10 a 25 minutos por minuto de música. " +
          "O resto da música não muda, e você pode continuar usando o app.",
      )
    )
      return;
    mt.pause();
    run("vozes", async () => onJobChange(await api.redoVocals(job.id, "melhor")));
  };
  const resplit = () => {
    if (!confirm("Refazer a divisão das guitarras com o algoritmo atual? Leva alguns minutos; o resto não muda.")) return;
    mt.pause();
    run("guitarras", async () => onJobChange(await api.resplitGuitars(job.id)));
  };

  useEffect(() => {
    try {
      localStorage.setItem(FORMAT_KEY, format);
    } catch {
      /* armazenamento indisponível: só não lembra a preferência */
    }
  }, [format]);

  // Barra de espaço = play/pause (fora de campos de texto).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (e.code === "Space" && tag !== "INPUT" && tag !== "SELECT" && tag !== "TEXTAREA" && tag !== "BUTTON") {
        e.preventDefault();
        mt.toggle();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mt.toggle]);

  const progress = mt.duration ? mt.time / mt.duration : 0;
  const seekFraction = (f: number) => mt.seek(f * mt.duration);

  // Presets de Karaokê / Play-along: só mostra os que fazem sentido para os stems desta música.
  const presets = useMemo(() => {
    const names = job.stems.map((s) => s.name);
    const byGroup = (g: string) => job.stems.filter((s) => s.group === g).map((s) => s.name);
    const list: { label: string; mute: string[] }[] = [{ label: "Tudo", mute: [] }];
    const add = (label: string, mute: string[]) => mute.length && list.push({ label, mute });
    add("Karaokê (sem voz)", byGroup("voz"));
    add("Sem voz principal", names.filter((n) => n === "vocal_principal"));
    const leads = names.filter((n) => n === "guitarra_solo" || n === "guitarra_dueto");
    add("Sem guitarra solo", names.filter((n) => n === "guitarra_solo"));
    if (names.includes("guitarra_dueto")) add("Sem solo e dueto", leads);
    add("Sem guitarra base", names.filter((n) => ["guitarra_base", "guitarra_1", "guitarra_2"].includes(n)));
    add("Sem guitarras", byGroup("guitarra"));
    add("Sem baixo", byGroup("baixo"));
    add("Sem bateria", byGroup("bateria"));
    return list;
  }, [job.stems]);

  const run = async (label: string, fn: () => Promise<void>) => {
    setBusy(label);
    setNotice(null);
    try {
      await fn();
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const keyNow = transposeKey(job.analysis.key, semitones);
  const formatLabel = health?.formatos.find((f) => f.id === format)?.label ?? format;
  const tomNote = semitones ? ` (tom ${semitones > 0 ? "+" : ""}${semitones})` : "";

  return (
    <div className="space-y-4">
      {/* Cabeçalho com informações da música */}
      <div className="card p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="truncate text-xl font-semibold" title={job.title}>
              {job.title}
            </h2>
            <p className="mt-1 text-sm text-neutral-400">
              Modo {MODE_LABELS[job.mode] ?? job.mode} · {job.stems.length} stems
              {job.seconds ? ` · processado em ${formatDuration(job.seconds)}` : ""}
              {job.device ? ` (${job.device})` : ""}
            </p>
          </div>
          <div className="flex flex-wrap gap-2 text-sm">
            <Info label="BPM" value={job.analysis.bpm ? String(Math.round(job.analysis.bpm)) : "—"} />
            <Info
              label="Tom"
              value={keyNow ?? "—"}
              hint={semitones && job.analysis.key_label ? `original: ${job.analysis.key_label}` : undefined}
            />
            <Info label="Duração" value={formatTime(job.analysis.duration ?? mt.duration)} />
          </div>
        </div>
        {job.warnings.length > 0 && (
          <ul className="mt-3 space-y-1 rounded-lg bg-amber-500/10 p-3 text-sm text-amber-300">
            {job.warnings.map((w) => (
              <li key={w}>⚠ {w}</li>
            ))}
          </ul>
        )}
        {canResplit && (
          <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
            <button className="btn-ghost" disabled={busy !== null} onClick={resplit}>
              {busy === "guitarras" ? <Spinner /> : null}
              {busy === "guitarras" ? "Refazendo as guitarras… (alguns minutos)" : "Refazer separação das guitarras"}
            </button>
            <span className="text-neutral-500">Usa o algoritmo mais recente sem reprocessar a música inteira.</span>
          </div>
        )}
        {canRedoVocals && (
          <div className="mt-2 flex flex-wrap items-center gap-3 text-sm">
            <button className="btn-ghost" disabled={busy !== null} onClick={redoVocals}>
              {busy === "vozes" ? <Spinner /> : null}
              Refazer vozes com qualidade melhor
            </button>
            <span className="text-neutral-500">
              Separa melhor voz principal e backing vocals (modelo RoFormer). Mais lento.
            </span>
          </div>
        )}
      </div>

      {/* Transporte */}
      <div className="card z-10 space-y-4 !bg-neutral-900 p-4 md:sticky md:top-2">
        <div className="flex items-center gap-3">
          <button
            onClick={mt.toggle}
            disabled={mt.loading}
            className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-brand-600 text-xl text-white transition hover:bg-brand-500 disabled:opacity-50"
            aria-label={mt.playing ? "Pausar" : "Tocar"}
            title="Play/Pause (barra de espaço)"
          >
            {mt.loading ? <Spinner /> : mt.playing ? "❚❚" : "▶"}
          </button>
          <span className="w-12 text-right font-mono text-sm tabular-nums">{formatTime(mt.time)}</span>
          <div className="relative flex-1">
            <input
              type="range"
              min={0}
              max={mt.duration || 0}
              step={0.01}
              value={mt.time}
              onChange={(e) => mt.seek(Number(e.target.value))}
              className="w-full"
              aria-label="Posição"
            />
            {mt.loop.a !== null && mt.duration > 0 && <Marker at={mt.loop.a / mt.duration} label="A" />}
            {mt.loop.b !== null && mt.duration > 0 && <Marker at={mt.loop.b / mt.duration} label="B" />}
          </div>
          <span className="w-12 font-mono text-sm tabular-nums text-neutral-400">{formatTime(mt.duration)}</span>
        </div>

        <div className="grid gap-4 text-sm md:grid-cols-3">
          {/* Velocidade */}
          <div>
            <div className="mb-1 flex justify-between text-neutral-400">
              <span>Velocidade (sem mudar o tom)</span>
              <button className="text-brand-400 hover:underline" onClick={() => mt.setRate(1)}>
                {Math.round(mt.rate * 100)}%
              </button>
            </div>
            <input
              type="range"
              min={0.5}
              max={1.5}
              step={0.05}
              value={mt.rate}
              onChange={(e) => mt.setRate(Number(e.target.value))}
              className="w-full"
              aria-label="Velocidade"
            />
          </div>

          {/* Transposição */}
          <div>
            <div className="mb-1 text-neutral-400">Transpor tom (semitons)</div>
            <div className="flex items-center gap-2">
              <button className="btn-ghost px-3" aria-label="Descer meio tom" onClick={() => setPendingSemitones((s) => Math.max(-12, s - 1))}>
                −
              </button>
              <span className="w-10 text-center font-mono">
                {pendingSemitones > 0 ? "+" : ""}
                {pendingSemitones}
              </span>
              <button className="btn-ghost px-3" aria-label="Subir meio tom" onClick={() => setPendingSemitones((s) => Math.min(12, s + 1))}>
                +
              </button>
              <button
                className="btn-primary"
                disabled={pendingSemitones === semitones || mt.loading}
                onClick={() => setSemitones(pendingSemitones)}
                title="Gera as faixas no novo tom (pode levar alguns segundos na primeira vez)"
              >
                Aplicar
              </button>
            </div>
          </div>

          {/* Loop A-B */}
          <div>
            <div className="mb-1 text-neutral-400">
              Loop A-B{" "}
              {mt.loop.a !== null && mt.loop.b !== null && (
                <span className="font-mono text-neutral-300">
                  ({formatTime(mt.loop.a)}–{formatTime(mt.loop.b)})
                </span>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              <button className="btn-ghost" onClick={() => mt.markLoop("a")} title="Marca o início do trecho no ponto atual">
                Marcar A
              </button>
              <button className="btn-ghost" onClick={() => mt.markLoop("b")} title="Marca o fim do trecho no ponto atual">
                Marcar B
              </button>
              <button
                className={mt.loop.enabled ? "btn-primary" : "btn-ghost"}
                disabled={mt.loop.a === null || mt.loop.b === null}
                onClick={() => mt.setLoopEnabled(!mt.loop.enabled)}
              >
                {mt.loop.enabled ? "Loop ligado" : "Loop desligado"}
              </button>
              {(mt.loop.a !== null || mt.loop.b !== null) && (
                <button className="btn-ghost" onClick={mt.clearLoop} aria-label="Limpar loop">
                  ✕
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Karaokê / play-along */}
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-neutral-400">Play-along:</span>
          {presets.map((p) => (
            <button key={p.label} className="btn-ghost px-3 py-1" onClick={() => mt.muteOnly(p.mute)}>
              {p.label}
            </button>
          ))}
        </div>

        {mt.loading && semitones !== 0 && (
          <p className="text-sm text-brand-400">Gerando as faixas no novo tom… (na primeira vez pode levar alguns segundos)</p>
        )}
        {mt.error && <p className="text-sm text-red-400">{mt.error}</p>}
      </div>

      {/* Canais */}
      <div className="card px-4 py-1">
        {job.stems.map((stem) => (
          <TrackRow
            key={stem.name}
            stem={stem}
            state={mt.tracks[stem.name] ?? { volume: 1, muted: false, solo: false }}
            audible={isAudible(mt.tracks, stem.name)}
            peaks={peaks[stem.name]}
            progress={progress}
            duration={mt.duration}
            loop={mt.loop}
            onChange={(patch) => mt.setTrack(stem.name, patch)}
            onSeek={seekFraction}
            onDownload={() => downloadUrl(api.stemUrl(job.id, stem.name, format, semitones))}
          />
        ))}
      </div>

      {/* Downloads */}
      <div className="card flex flex-wrap items-center gap-3 p-4 text-sm">
        <label className="flex items-center gap-2">
          <span className="text-neutral-400">Formato:</span>
          <select className="select" value={format} onChange={(e) => setFormat(e.target.value)}>
            {(health?.formatos ?? [{ id: "wav24", label: "WAV 24 bits" }]).map((f) => (
              <option key={f.id} value={f.id}>
                {f.label}
              </option>
            ))}
          </select>
        </label>
        <button
          className="btn-ghost"
          disabled={busy !== null}
          onClick={() => downloadUrl(api.zipUrl(job.id, format, semitones))}
          title="Pode demorar alguns segundos para montar o ZIP"
        >
          Baixar todos (ZIP)
        </button>
        <button
          className="btn-primary"
          disabled={busy !== null}
          onClick={() => run("mix", () => api.downloadMix(job.id, mt.effectiveVolumes, format, semitones))}
          title="Soma só os canais que estão tocando, com os volumes atuais"
        >
          {busy === "mix" ? <Spinner /> : null}
          Baixar mix personalizado
        </button>
        <span className="text-neutral-500">
          {formatLabel}
          {tomNote}. O mix usa só os canais ativos e seus volumes. Velocidade não é aplicada nos downloads.
        </span>
        {notice && <p className="w-full text-red-400">{notice}</p>}
      </div>
    </div>
  );
}

function Info({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg bg-neutral-800/70 px-3 py-1.5 text-center" title={hint}>
      <div className="text-[11px] uppercase tracking-wide text-neutral-500">{label}</div>
      <div className="font-semibold">{value}</div>
    </div>
  );
}

function Marker({ at, label }: { at: number; label: string }) {
  return (
    <span
      className="pointer-events-none absolute -top-3 -translate-x-1/2 text-[10px] font-bold text-brand-400"
      style={{ left: `${at * 100}%` }}
    >
      {label}
    </span>
  );
}

export function Spinner() {
  return <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />;
}
