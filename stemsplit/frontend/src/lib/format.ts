// Pequenas funções de formatação usadas pela interface.

export function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) seconds = 0;
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function formatDate(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)} s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return s ? `${m} min ${s} s` : `${m} min`;
}

const NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const NOTES_PT = ["Dó", "Dó#", "Ré", "Ré#", "Mi", "Fá", "Fá#", "Sol", "Sol#", "Lá", "Lá#", "Si"];

/** Transpõe um tom como "Em" ou "C#" em N semitons e devolve o nome em português. */
export function transposeKey(key: string | null | undefined, semitones: number): string | null {
  if (!key) return null;
  const minor = key.endsWith("m");
  const root = minor ? key.slice(0, -1) : key;
  const idx = NOTES.indexOf(root);
  if (idx < 0) return null;
  const shifted = (((idx + semitones) % 12) + 12) % 12;
  return `${NOTES_PT[shifted]} ${minor ? "menor" : "maior"}`;
}

export const MODE_LABELS: Record<string, string> = {
  rapido: "Rápido",
  completo: "Completo",
  detalhado: "Detalhado",
};
