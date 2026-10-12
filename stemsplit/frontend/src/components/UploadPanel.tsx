import { useRef, useState } from "react";
import { api, Health, Job } from "../lib/api";
import { Spinner } from "./Player";

interface Props {
  health: Health | null;
  onCreated: (job: Job) => void;
}

const MODES = [
  {
    id: "rapido",
    title: "Rápido",
    stems: "4 stems",
    text: "Voz, bateria, baixo e outros.",
  },
  {
    id: "completo",
    title: "Completo",
    stems: "6 stems",
    text: "Inclui guitarra e teclado/piano. Bom para a maioria das músicas.",
  },
  {
    id: "detalhado",
    title: "Detalhado",
    stems: "até 13 stems",
    text: "Voz principal × backing vocals, guitarra solo/base e guitarra 1/2 (esquerda/direita).",
    warning: "Mais lento e a divisão das guitarras é uma estimativa — funciona melhor com guitarras abertas no estéreo.",
  },
];

const MODE_KEY = "stemsplit.modo";

function savedMode(): string {
  try {
    return localStorage.getItem(MODE_KEY) || "completo";
  } catch {
    return "completo";
  }
}

export function UploadPanel({ health, onCreated }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState(savedMode);
  const [splitDrums, setSplitDrums] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const accept = health?.extensoes.join(",") ?? ".mp3,.wav,.flac,.m4a";
  const maxMb = health?.max_upload_mb ?? 200;

  const pick = (f: File | undefined) => {
    setError(null);
    if (!f) return;
    const ext = "." + (f.name.split(".").pop() || "").toLowerCase();
    if (!accept.split(",").includes(ext)) {
      setError("Formato não suportado. Envie um arquivo MP3, WAV, FLAC ou M4A.");
      return;
    }
    if (f.size > maxMb * 1024 * 1024) {
      setError(`Arquivo muito grande. O limite é ${maxMb} MB.`);
      return;
    }
    setFile(f);
  };

  const chooseMode = (id: string) => {
    setMode(id);
    try {
      localStorage.setItem(MODE_KEY, id);
    } catch {
      /* ignora */
    }
  };

  const submit = async () => {
    if (!file) return;
    setError(null);
    setUploading(0);
    try {
      const job = await api.upload(file, mode, splitDrums, setUploading);
      onCreated(job);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(null);
    }
  };

  return (
    <div className="card space-y-6 p-6">
      {/* Área de arrastar e soltar */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          pick(e.dataTransfer.files[0]);
        }}
        onClick={() => input.current?.click()}
        className={`flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed px-6 py-14 text-center transition ${
          dragging ? "border-brand-400 bg-brand-500/10" : "border-neutral-700 hover:border-neutral-500 hover:bg-neutral-800/40"
        }`}
      >
        <div className="text-5xl">🎵</div>
        {file ? (
          <>
            <div className="text-lg font-medium">{file.name}</div>
            <div className="text-sm text-neutral-400">
              {(file.size / 1024 / 1024).toFixed(1)} MB · clique para trocar
            </div>
          </>
        ) : (
          <>
            <div className="text-xl font-semibold">Arraste sua música aqui</div>
            <div className="text-sm text-neutral-400">MP3, WAV, FLAC ou M4A · até {maxMb} MB</div>
            <span className="btn-primary mt-2">Escolher arquivo</span>
          </>
        )}
        <input
          ref={input}
          type="file"
          accept={accept}
          className="hidden"
          onChange={(e) => {
            pick(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </div>

      {/* Modo */}
      <div>
        <h3 className="mb-3 text-sm font-medium text-neutral-300">Como você quer separar?</h3>
        <div className="grid gap-3 md:grid-cols-3">
          {MODES.map((m) => (
            <button
              key={m.id}
              onClick={() => chooseMode(m.id)}
              className={`rounded-xl border p-4 text-left transition ${
                mode === m.id
                  ? "border-brand-500 bg-brand-500/10 ring-1 ring-brand-500"
                  : "border-neutral-800 bg-neutral-900 hover:border-neutral-600"
              }`}
            >
              <div className="flex items-baseline justify-between">
                <span className="font-semibold">{m.title}</span>
                <span className="text-xs text-neutral-400">{m.stems}</span>
              </div>
              <p className="mt-1 text-sm text-neutral-400">{m.text}</p>
              {m.warning && mode === m.id && <p className="mt-2 text-xs text-amber-300">⚠ {m.warning}</p>}
            </button>
          ))}
        </div>
        {mode !== "rapido" && (
          <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm text-neutral-300">
            <input type="checkbox" checked={splitDrums} onChange={(e) => setSplitDrums(e.target.checked)} />
            Separar também a bateria em bumbo, caixa e pratos
          </label>
        )}
      </div>

      {error && <p className="rounded-lg bg-red-500/10 p-3 text-sm text-red-300">{error}</p>}

      <div className="flex items-center justify-between gap-4">
        <span className="text-xs text-neutral-500">
          🔒 Sua música é processada neste computador{health ? ` (${health.dispositivo})` : ""} e não é enviada para ninguém.
        </span>
        <button className="btn-primary px-6 py-3 text-base" disabled={!file || uploading !== null} onClick={submit}>
          {uploading !== null ? (
            <>
              <Spinner /> Enviando {Math.round(uploading * 100)}%
            </>
          ) : (
            "Separar faixas"
          )}
        </button>
      </div>
    </div>
  );
}
