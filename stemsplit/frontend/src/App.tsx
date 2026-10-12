import { useCallback, useEffect, useState } from "react";
import { HistoryList } from "./components/HistoryList";
import { Player } from "./components/Player";
import { ProgressPanel } from "./components/ProgressPanel";
import { UploadPanel } from "./components/UploadPanel";
import { api, Health, Job } from "./lib/api";

// Navegação simples por hash: "#/" (início) e "#/musica/<id>" (resultado).
function useRoute(): [string | null, (id: string | null) => void] {
  const parse = () => /^#\/musica\/([0-9a-f]+)/.exec(window.location.hash)?.[1] ?? null;
  const [jobId, setJobId] = useState(parse);
  useEffect(() => {
    const onHash = () => setJobId(parse());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const go = (id: string | null) => {
    window.location.hash = id ? `/musica/${id}` : "/";
  };
  return [jobId, go];
}

export default function App() {
  const [jobId, go] = useRoute();
  const [health, setHealth] = useState<Health | null>(null);
  const [offline, setOffline] = useState(false);
  const [jobs, setJobs] = useState<Job[]>([]);

  useEffect(() => {
    api
      .health()
      .then((h) => {
        setHealth(h);
        setOffline(false);
      })
      .catch(() => setOffline(true));
  }, []);

  const refreshJobs = useCallback(() => {
    api.jobs().then(setJobs).catch(() => undefined);
  }, []);

  // Atualiza o histórico periodicamente enquanto houver algo processando.
  useEffect(() => {
    refreshJobs();
    const busy = jobs.some((j) => j.status === "na_fila" || j.status === "processando");
    if (!busy) return;
    const id = setInterval(refreshJobs, 3000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, jobs.some((j) => j.status === "na_fila" || j.status === "processando")]);

  return (
    <div className="mx-auto max-w-6xl px-4 pb-16">
      <header className="flex items-center justify-between py-6">
        <button className="flex items-center gap-3" onClick={() => go(null)}>
          <img src="/favicon.svg" alt="" className="h-9 w-9" />
          <div className="text-left">
            <div className="text-xl font-bold tracking-tight">StemSplit</div>
            <div className="text-xs text-neutral-400">Separe as faixas da sua música</div>
          </div>
        </button>
        {jobId && (
          <button className="btn-ghost" onClick={() => go(null)}>
            + Nova música
          </button>
        )}
      </header>

      {offline && (
        <div className="mb-4 rounded-lg bg-red-500/10 p-3 text-sm text-red-300">
          Não consegui falar com o servidor do StemSplit. Verifique se ele está rodando (veja o README).
        </div>
      )}

      {jobId ? (
        <JobView key={jobId} jobId={jobId} health={health} onBack={() => go(null)} onChange={refreshJobs} />
      ) : (
        <div className="space-y-8">
          <UploadPanel
            health={health}
            onCreated={(job) => {
              refreshJobs();
              go(job.id);
            }}
          />
          <section className="card p-6">
            <h2 className="mb-2 text-lg font-semibold">Histórico</h2>
            <HistoryList
              jobs={jobs}
              onOpen={go}
              onDelete={(id) =>
                api
                  .remove(id)
                  .then(refreshJobs)
                  .catch((e) => alert(e.message))
              }
            />
          </section>
        </div>
      )}
    </div>
  );
}

function JobView({
  jobId,
  health,
  onBack,
  onChange,
}: {
  jobId: string;
  health: Health | null;
  onBack: () => void;
  onChange: () => void;
}) {
  const [job, setJob] = useState<Job | null>(null);
  const [missing, setMissing] = useState(false);
  const [offline, setOffline] = useState(false);
  const [attempt, setAttempt] = useState(0); // muda a cada "tentar de novo" para reabrir o acompanhamento

  useEffect(() => {
    let stop: (() => void) | undefined;
    let cancelled = false;
    api
      .job(jobId)
      .then((j) => {
        if (cancelled) return;
        setJob(j);
        if (j.status !== "concluido" && j.status !== "erro") {
          stop = api.watch(
            jobId,
            (updated) => {
              setJob(updated);
              if (updated.status === "concluido" || updated.status === "erro") onChange();
            },
            (ok) => setOffline(!ok),
          );
        }
      })
      .catch(() => setMissing(true));
    return () => {
      cancelled = true;
      stop?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, attempt]);

  const retry = async (mode?: string) => {
    try {
      setJob(await api.retry(jobId, mode));
      setOffline(false);
      setAttempt((n) => n + 1);
      onChange();
    } catch (e) {
      alert((e as Error).message);
    }
  };

  if (missing) {
    return (
      <div className="card space-y-3 p-6">
        <p>Essa música não está mais no histórico.</p>
        <button className="btn-primary" onClick={onBack}>
          Voltar ao início
        </button>
      </div>
    );
  }
  if (!job) return <div className="card h-40 animate-pulse" />;
  if (job.status === "concluido") return <Player job={job} health={health} />;
  return <ProgressPanel job={job} offline={offline} onBack={onBack} onRetry={retry} />;
}
