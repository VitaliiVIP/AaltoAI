import { useMemo, useState } from "react";
import TopBar from "./components/TopBar";
import CvList from "./components/CvList";
import ExplainPanel from "./components/ExplainPanel";
import EmailPanel from "./components/EmailPanel";
import SettingsDrawer from "./components/SettingsDrawer";
import AcceptedDrawer from "./components/AcceptedDrawer";
import Toast from "./components/Toast";
import { deriveName } from "./candidateMeta";
import type { EmailStatus } from "./types";
import { useScreening } from "./useScreening";
import { useToast } from "./useToast";

export default function App() {
  const s = useScreening();
  const [emailStatus, setEmailStatus] = useState<Record<string, EmailStatus>>({});
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [acceptedOpen, setAcceptedOpen] = useState(false);
  const { message, visible, showToast } = useToast();

  // Accepted = cleared the bar AND actually accepted (not just "sent" from
  // the rejection-with-recourse flow, which uses the same status value).
  const acceptedCount = useMemo(
    () =>
      s.pool.filter((row) => row.decision === "advance" && emailStatus[row.candidate_id] === "sent")
        .length,
    [s.pool, emailStatus],
  );

  function handleSend(id: string) {
    setEmailStatus((prev) => ({ ...prev, [id]: "sent" }));
    showToast(`Email sent to ${deriveName(id)}`);
  }

  function handleDecline(id: string) {
    setEmailStatus((prev) => ({ ...prev, [id]: "declined" }));
    showToast(`Kept for further review — ${deriveName(id)}`);
  }

  function handleUnaccept(id: string) {
    setEmailStatus((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
    showToast(`${deriveName(id)} moved back to the applicant pool`);
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
        acceptedCount={acceptedCount}
        acceptedOpen={acceptedOpen}
        onOpenAccepted={() => setAcceptedOpen(true)}
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
        onClose={() => setSettingsOpen(false)}
      />

      <AcceptedDrawer
        open={acceptedOpen}
        pool={s.pool}
        emailStatus={emailStatus}
        onClose={() => setAcceptedOpen(false)}
        onUnaccept={handleUnaccept}
      />

      <Toast message={message} visible={visible} />
    </>
  );
}
