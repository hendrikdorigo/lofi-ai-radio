// Cliente da API do StemSplit. Todas as rotas ficam sob /api (mesma origem).

export type JobStatus = "na_fila" | "processando" | "concluido" | "erro";

export interface Stem {
  name: string;
  label: string;
  group: string;
  color: string;
  description: string;
}

export interface Analysis {
  duration?: number;
  bpm?: number | null;
  key?: string | null;
  key_label?: string | null;
  key_confidence?: number | null;
}

export interface Job {
  id: string;
  title: string;
  filename: string;
  mode: string;
  split_drums: boolean;
  status: JobStatus;
  progress: number;
  stage: string;
  error: string | null;
  created_at: number;
  finished_at: number | null;
  seconds: number | null;
  device: string | null;
  stems: Stem[];
  analysis: Analysis;
  warnings: string[];
  queue_position: number | null;
}

export interface Health {
  dispositivo: string;
  modos: { id: string; label: string; descricao: string; stems: string[] }[];
  formatos: { id: string; label: string }[];
  extensoes: string[];
  max_upload_mb: number;
}

async function check<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = `Erro ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* resposta sem JSON */
    }
    throw new Error(msg);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const api = {
  health: () => fetch("/api/saude").then((r) => check<Health>(r)),
  jobs: () => fetch("/api/jobs").then((r) => check<Job[]>(r)),
  job: (id: string) => fetch(`/api/jobs/${id}`).then((r) => check<Job>(r)),
  remove: (id: string) => fetch(`/api/jobs/${id}`, { method: "DELETE" }).then((r) => check<void>(r)),
  peaks: (id: string) => fetch(`/api/jobs/${id}/ondas`).then((r) => check<Record<string, number[]>>(r)),

  /** Envia a música com barra de progresso do upload (XHR permite acompanhar). */
  upload(file: File, mode: string, splitDrums: boolean, onProgress: (frac: number) => void): Promise<Job> {
    return new Promise((resolve, reject) => {
      const form = new FormData();
      form.append("arquivo", file);
      form.append("modo", mode);
      form.append("bateria", String(splitDrums));
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/jobs");
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
      xhr.onload = () => {
        let body: any = null;
        try {
          body = JSON.parse(xhr.responseText);
        } catch {
          /* ignora */
        }
        if (xhr.status >= 200 && xhr.status < 300) resolve(body as Job);
        else reject(new Error(body?.detail || `Erro ${xhr.status} ao enviar o arquivo`));
      };
      xhr.onerror = () => reject(new Error("Não consegui falar com o servidor. Ele está rodando?"));
      xhr.send(form);
    });
  },

  /** Acompanha o job em tempo real via Server-Sent Events. Devolve função para parar. */
  watch(id: string, onUpdate: (job: Job) => void): () => void {
    const source = new EventSource(`/api/jobs/${id}/eventos`);
    source.onmessage = (e) => {
      const job = JSON.parse(e.data) as Job;
      onUpdate(job);
      if (job.status === "concluido" || job.status === "erro") source.close();
    };
    // Se a conexão cair, o EventSource reconecta sozinho.
    return () => source.close();
  },

  previewUrl: (id: string, stem: string, semitones: number) =>
    `/api/jobs/${id}/previa/${stem}${semitones ? `?tom=${semitones}` : ""}`,
  stemUrl: (id: string, stem: string, format: string, semitones: number) =>
    `/api/jobs/${id}/baixar/${stem}?formato=${format}&tom=${semitones}`,
  zipUrl: (id: string, format: string, semitones: number) => `/api/jobs/${id}/zip?formato=${format}&tom=${semitones}`,

  async downloadMix(id: string, volumes: Record<string, number>, format: string, semitones: number) {
    const res = await fetch(`/api/jobs/${id}/mix`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ volumes, formato: format, tom: semitones }),
    });
    if (!res.ok) await check(res);
    const blob = await res.blob();
    saveBlob(blob, filenameFrom(res.headers.get("content-disposition")) || "mix.wav");
  },
};

function filenameFrom(header: string | null): string | null {
  if (!header) return null;
  const utf = /filename\*=utf-8''([^;]+)/i.exec(header);
  if (utf) return decodeURIComponent(utf[1]);
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain ? plain[1] : null;
}

function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/** Dispara um download a partir de uma URL (o servidor manda o nome do arquivo). */
export function downloadUrl(url: string) {
  const a = document.createElement("a");
  a.href = url;
  a.download = "";
  a.click();
}
