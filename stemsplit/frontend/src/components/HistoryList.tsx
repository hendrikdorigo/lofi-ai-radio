import { Job } from "../lib/api";
import { formatDate, MODE_LABELS } from "../lib/format";

interface Props {
  jobs: Job[];
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
}

const STATUS: Record<string, { label: string; cls: string }> = {
  na_fila: { label: "Na fila", cls: "bg-neutral-700 text-neutral-200" },
  processando: { label: "Processando", cls: "bg-brand-600/30 text-brand-400" },
  concluido: { label: "Pronto", cls: "bg-emerald-500/20 text-emerald-300" },
  erro: { label: "Erro", cls: "bg-red-500/20 text-red-300" },
};

/** Histórico das músicas processadas (guardado no disco do servidor local). */
export function HistoryList({ jobs, onOpen, onDelete }: Props) {
  if (!jobs.length) {
    return <p className="text-sm text-neutral-500">Nenhuma música processada ainda.</p>;
  }
  return (
    <ul className="divide-y divide-neutral-800">
      {jobs.map((job) => {
        const st = STATUS[job.status] ?? STATUS.erro;
        return (
          <li key={job.id} className="flex items-center gap-3 py-3">
            <button className="min-w-0 flex-1 text-left" onClick={() => onOpen(job.id)}>
              <div className="truncate font-medium hover:text-brand-400">{job.title}</div>
              <div className="text-xs text-neutral-500">
                {formatDate(job.created_at)} · {MODE_LABELS[job.mode] ?? job.mode}
                {job.analysis?.bpm ? ` · ${Math.round(job.analysis.bpm)} BPM` : ""}
                {job.analysis?.key_label ? ` · ${job.analysis.key_label}` : ""}
              </div>
            </button>
            <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${st.cls}`}>
              {job.status === "processando" ? `${Math.round(job.progress * 100)}%` : st.label}
            </span>
            <button
              className="shrink-0 rounded-md px-2 py-1 text-neutral-500 hover:bg-neutral-800 hover:text-red-400 disabled:opacity-30"
              disabled={job.status === "processando"}
              onClick={() => {
                if (confirm(`Apagar "${job.title}" e todos os stems gerados?`)) onDelete(job.id);
              }}
              title="Apagar do histórico"
              aria-label={`Apagar ${job.title}`}
            >
              🗑
            </button>
          </li>
        );
      })}
    </ul>
  );
}
