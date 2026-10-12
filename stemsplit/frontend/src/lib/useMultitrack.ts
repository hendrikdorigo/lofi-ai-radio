// Motor do player multitrack.
//
// Cada stem toca num <audio> próprio (streaming, pouca memória mesmo com 12+
// stems de 5 minutos). O primeiro stem é o "mestre": a cada poucos quadros os
// outros são realinhados a ele se desviarem mais que DRIFT_LIMIT segundos.
//
// - Mute/Solo/Volume: aplicados direto em cada <audio>.
// - Velocidade sem mudar o tom: playbackRate + preservesPitch (nativo do navegador).
// - Transposição: o servidor gera prévias transpostas (rubberband); aqui só
//   trocamos as fontes mantendo a posição.
// - Loop A-B: verificado a cada quadro de animação.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, Stem } from "./api";

export interface TrackState {
  volume: number; // 0..1
  muted: boolean;
  solo: boolean;
}

export interface LoopState {
  a: number | null;
  b: number | null;
  enabled: boolean;
}

const DRIFT_LIMIT = 0.06;

type AudioWithPitch = HTMLAudioElement & { mozPreservesPitch?: boolean; webkitPreservesPitch?: boolean };

export function isAudible(tracks: Record<string, TrackState>, name: string): boolean {
  const anySolo = Object.values(tracks).some((t) => t.solo);
  const t = tracks[name];
  if (!t) return false;
  return anySolo ? t.solo && !t.muted : !t.muted;
}

export function useMultitrack(jobId: string, stems: Stem[], semitones: number, revision = 0) {
  const stemsKey = stems.map((s) => s.name).join(",");
  const elsRef = useRef<Map<string, AudioWithPitch>>(new Map());
  const [tracks, setTracks] = useState<Record<string, TrackState>>({});
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rate, setRate] = useState(1);
  const [loop, setLoop] = useState<LoopState>({ a: null, b: null, enabled: false });

  // Refs espelham o estado para uso dentro do loop de animação.
  const playingRef = useRef(false);
  const loopRef = useRef(loop);
  const timeRef = useRef(0);
  loopRef.current = loop;

  const master = () => elsRef.current.values().next().value as AudioWithPitch | undefined;
  const all = () => Array.from(elsRef.current.values());

  // ---------------------------------------------------------------- criação
  useEffect(() => {
    const map = new Map<string, AudioWithPitch>();
    for (const s of stems) {
      const el = new Audio() as AudioWithPitch;
      el.preload = "auto";
      el.preservesPitch = el.mozPreservesPitch = el.webkitPreservesPitch = true;
      map.set(s.name, el);
    }
    elsRef.current = map;
    setTracks(Object.fromEntries(stems.map((s) => [s.name, { volume: 1, muted: false, solo: false }])));
    setLoop({ a: null, b: null, enabled: false });
    timeRef.current = 0;
    setTime(0);

    const first = map.values().next().value as AudioWithPitch | undefined;
    const onEnded = () => {
      all().forEach((el) => el.pause());
      playingRef.current = false;
      setPlaying(false);
    };
    first?.addEventListener("ended", onEnded);

    return () => {
      first?.removeEventListener("ended", onEnded);
      for (const el of map.values()) {
        el.pause();
        el.removeAttribute("src");
        el.load();
      }
      playingRef.current = false;
      setPlaying(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, stemsKey]);

  // ------------------------------------------------- carregar/trocar fontes
  useEffect(() => {
    let cancelled = false;
    const wasPlaying = playingRef.current;
    const position = timeRef.current;
    all().forEach((el) => el.pause());
    setLoading(true);
    setError(null);

    const loads = Array.from(elsRef.current.entries()).map(
      ([name, el]) =>
        new Promise<void>((resolve, reject) => {
          const ok = () => {
            el.removeEventListener("error", fail);
            resolve();
          };
          const fail = () => {
            el.removeEventListener("canplay", ok);
            reject(new Error(`Falha ao carregar o stem "${name}"`));
          };
          el.addEventListener("canplay", ok, { once: true });
          el.addEventListener("error", fail, { once: true });
          el.src = api.previewUrl(jobId, name, semitones, revision);
          el.load();
        }),
    );

    Promise.all(loads)
      .then(() => {
        if (cancelled) return;
        all().forEach((el) => (el.currentTime = position));
        setDuration(master()?.duration || 0);
        setLoading(false);
        if (wasPlaying) void startAll();
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, stemsKey, semitones, revision]);

  // ------------------------------------------------- volume / mute / solo
  useEffect(() => {
    for (const [name, el] of elsRef.current) {
      const t = tracks[name];
      if (!t) continue;
      el.volume = t.volume;
      el.muted = !isAudible(tracks, name);
    }
  }, [tracks]);

  // ------------------------------------------------- velocidade
  useEffect(() => {
    all().forEach((el) => (el.playbackRate = rate));
  }, [rate, stemsKey]);

  // ------------------------------------------------- relógio, loop e sincronia
  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    let raf = 0;
    const tick = () => {
      const m = master();
      if (m) {
        let t = m.currentTime;
        const lp = loopRef.current;
        if (lp.enabled && lp.a !== null && lp.b !== null && t >= lp.b) {
          seekAll(lp.a);
          t = lp.a;
        } else if (++frame % 15 === 0) {
          for (const el of all()) {
            if (el !== m && Math.abs(el.currentTime - t) > DRIFT_LIMIT) el.currentTime = t;
          }
        }
        timeRef.current = t;
        setTime(t);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing]);

  // ------------------------------------------------- comandos
  const seekAll = (t: number) => {
    const clamped = Math.max(0, Math.min(t, master()?.duration || t));
    all().forEach((el) => (el.currentTime = clamped));
    timeRef.current = clamped;
    setTime(clamped);
  };

  const startAll = async () => {
    const lp = loopRef.current;
    if (lp.enabled && lp.a !== null && lp.b !== null && (timeRef.current < lp.a || timeRef.current >= lp.b)) {
      seekAll(lp.a);
    }
    const t = timeRef.current;
    all().forEach((el) => (el.currentTime = t));
    try {
      await Promise.all(all().map((el) => el.play()));
      playingRef.current = true;
      setPlaying(true);
    } catch (e) {
      all().forEach((el) => el.pause());
      setError("O navegador bloqueou a reprodução. Clique em Play novamente.");
    }
  };

  const pause = useCallback(() => {
    all().forEach((el) => el.pause());
    playingRef.current = false;
    setPlaying(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggle = useCallback(() => {
    if (loading) return;
    if (playingRef.current) pause();
    else void startAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, pause]);

  const setTrack = useCallback((name: string, patch: Partial<TrackState>) => {
    setTracks((prev) => ({ ...prev, [name]: { ...prev[name], ...patch } }));
  }, []);

  /** Preset de play-along: muta exatamente os stems da lista e limpa os solos. */
  const muteOnly = useCallback((names: string[]) => {
    setTracks((prev) =>
      Object.fromEntries(Object.entries(prev).map(([n, t]) => [n, { ...t, solo: false, muted: names.includes(n) }])),
    );
  }, []);

  const markLoop = useCallback((point: "a" | "b") => {
    const t = timeRef.current;
    setLoop((prev) => {
      const next = { ...prev, [point]: t };
      if (next.a !== null && next.b !== null && next.b <= next.a) {
        // Se marcou B antes de A, troca para manter A < B.
        [next.a, next.b] = [next.b, next.a];
      }
      next.enabled = next.a !== null && next.b !== null && next.b - next.a > 0.2;
      return next;
    });
  }, []);

  /** Volumes efetivos (0 para quem está mutado), usados no "mix personalizado". */
  const effectiveVolumes = useMemo(
    () => Object.fromEntries(Object.entries(tracks).map(([n, t]) => [n, isAudible(tracks, n) ? t.volume : 0])),
    [tracks],
  );

  return {
    tracks,
    setTrack,
    muteOnly,
    effectiveVolumes,
    playing,
    toggle,
    pause,
    seek: seekAll,
    time,
    duration,
    loading,
    error,
    rate,
    setRate,
    loop,
    markLoop,
    setLoopEnabled: (enabled: boolean) => setLoop((p) => ({ ...p, enabled: enabled && p.a !== null && p.b !== null })),
    clearLoop: () => setLoop({ a: null, b: null, enabled: false }),
  };
}
