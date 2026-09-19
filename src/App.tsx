import { useState } from "react";
import TopBar from "./components/TopBar";
import CvList from "./components/CvList";
import ExplainPanel from "./components/ExplainPanel";
import EmailPanel from "./components/EmailPanel";
import SettingsDrawer from "./components/SettingsDrawer";
import RestateDrawer from "./components/RestateDrawer";
import Toast from "./components/Toast";
import { deriveName } from "./candidateMeta";
import type { EmailStatus } from "./types";
import { useScreening } from "./useScreening";
import { useToast } from "./useToast";

export default function App() {
  const s = useScreening();
  const [emailStatus, setEmailStatus] = useState<Record<string, EmailStatus>>({});
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [candidateViewOpen, setCandidateViewOpen] = useState(false);
  const { message, visible, showToast } = useToast();

  function handleSend(id: string) {
    setEmailStatus((prev) => ({ ...prev, [id]: "sent" }));
    showToast(`Email sent to ${deriveName(id)}`);
  }

  function handleDecline(id: string) {
    setEmailStatus((prev) => ({ ...prev, [id]: "declined" }));
    showToast(`Kept for further review — ${deriveName(id)}`);
  }

  async function handleUpload(file: File) {
    showToast("Reading the CV — this calls the extraction model…");
    try {
      const id = await s.uploadCv(file);
      showToast(`Added ${deriveName(id)} to the pool`);
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Upload failed");
    }
  }

  async function handleRestate(paths: string[]) {
    await s.applyRestatement(paths);
    showToast("Re-screened with the confirmed details");
  }

  return (
    <>
      <TopBar
        jobTitle={s.job?.title ?? "…"}
        mode={s.mode}
        onModeChange={s.setMode}
        slotsN={s.slotsN}
        onSlotsNChange={s.setSlotsN}
        threshold={s.job?.mode.A.threshold ?? null}
        poolSize={s.pool.length}
        settingsOpen={settingsOpen}
        onOpenSettings={() => setSettingsOpen(true)}
      />

      <main className="layout">
        <CvList
          pool={s.pool}
          mode={s.mode}
          maxScore={s.maxScore}
          selectedId={s.selectedId}
          emailStatus={emailStatus}
          aggregateLine={s.result?.aggregate_line ?? null}
          phase={s.poolPhase}
          error={s.poolError}
          uploading={s.uploading}
          onSelect={s.setSelectedId}
          onRetry={() => void s.refreshPool()}
          onUpload={(f) => void handleUpload(f)}
        />
        <ExplainPanel
          result={s.result}
          row={s.selectedRow}
          job={s.job}
          maxScore={s.maxScore}
          phase={s.screenPhase}
          error={s.screenError}
          restatedFrom={s.restatedFrom}
          onRevertRestatement={s.revertRestatement}
          onOpenCandidateView={() => setCandidateViewOpen(true)}
        />
        <EmailPanel
          result={s.result}
          jobTitle={s.job?.title ?? ""}
          status={s.selectedId ? emailStatus[s.selectedId] : undefined}
          polishing={s.screenPhase === "explaining"}
          onPolish={() => void s.polishExplanation()}
          onSend={handleSend}
          onDecline={handleDecline}
        />
      </main>

      <SettingsDrawer
        open={settingsOpen}
        job={s.job}
        result={s.result}
        audit={s.audit}
        mode={s.mode}
        slotsN={s.slotsN}
        poolSize={s.pool.length}
        onClose={() => setSettingsOpen(false)}
        onJobSaved={(job) => {
          s.applyJob(job);
          showToast(`Saved — re-screening against ${job.title}`);
        }}
      />

      <RestateDrawer
        open={candidateViewOpen}
        result={s.result}
        restatedFrom={s.restatedFrom}
        busy={s.screenPhase === "loading"}
        onClose={() => setCandidateViewOpen(false)}
        onConfirm={(paths) => void handleRestate(paths)}
        onRevert={s.revertRestatement}
      />

      <Toast message={message} visible={visible} />
    </>
  );
}
