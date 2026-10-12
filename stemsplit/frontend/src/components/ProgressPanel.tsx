import { useEffect, useState } from "react";
import { Job } from "../lib/api";
import { formatDuration, MODE_LABELS } from "../lib/format";

/** Tela de espera: barra de progresso em tempo real, etapa atual e posição na fila. */
export function ProgressPanel({ job, onBack }: { job: Job; onBack: () => void }) {
  const [now, setNow] = useState(Date.now() / 1000);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(id);
  }, []);

  const pct = Math.round(job.progress * 100);
  const elapsed = now - job.created_at;

  if (job.status === "erro") {
    return (
      <div className="card space-y-4 p-6">
        <h2 className="text-xl font-semibold">Não deu certo 😕</h2>
        <p className="text-neutral-300">
          Houve um problema ao processar <strong>{job.title}</strong>:
        </p>
        <pre className="whitespace-pre-wrap rounded-lg bg-red-500/10 p-3 text-sm text-red-300">{job.error}</pre>
        <p className="text-sm text-neutral-400">
          Verifique se o arquivo toca normalmente e se há memória livre. Se for a primeira execução, o servidor precisa de
          internet para baixar os modelos.
        </p>
        <button className="btn-primary" onClick={onBack}>
          Tentar outra música
        </button>
      </div>
    );
  }

  return (
    <div className="card space-y-5 p-6">
      <div>
        <h2 className="truncate text-xl font-semibold">{job.title}</h2>
        <p className="text-sm text-neutral-400">Modo {MODE_LABELS[job.mode] ?? job.mode}</p>
      </div>

      <div>
        <div className="mb-2 flex justify-between text-sm">
          <span className="text-neutral-200">
            {job.status === "na_fila"
              ? job.queue_position && job.queue_position > 1
                ? `Na fila — ${job.queue_position - 1} música(s) na frente`
                : "Na fila — começa em instantes"
              : job.stage}
          </span>
          <span className="font-mono tabular-nums">{pct}%</span>
        </div>
        <div className="h-3 overflow-hidden rounded-full bg-neutral-800">
          <div
            className="h-full rounded-full bg-gradient-to-r from-brand-600 to-fuchsia-500 transition-all duration-500"
            style={{ width: `${Math.max(2, pct)}%` }}
          />
        </div>
        <p className="mt-2 text-xs text-neutral-500">
          Tempo decorrido: {formatDuration(elapsed)}
          {job.device ? ` · processando em ${job.device}` : ""}
        </p>
      </div>

      {(job.analysis.bpm || job.analysis.key_label) && (
        <p className="text-sm text-neutral-300">
          Já detectamos: {job.analysis.bpm ? `${Math.round(job.analysis.bpm)} BPM` : ""}
          {job.analysis.bpm && job.analysis.key_label ? " · " : ""}
          {job.analysis.key_label ? `tom de ${job.analysis.key_label}` : ""}
        </p>
      )}

      <p className="text-sm text-neutral-400">
        Pode deixar esta página aberta ou voltar depois — a música fica salva no histórico. Em CPU, o modo Detalhado pode
        levar bastante tempo (veja o README).
      </p>
      <button className="btn-ghost" onClick={onBack}>
        Enviar outra música enquanto isso
      </button>
    </div>
  );
}
