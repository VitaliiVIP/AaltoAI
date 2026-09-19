import { useMemo, useState } from "react";
import TopBar from "./components/TopBar";
import CvList from "./components/CvList";
import ExplainPanel from "./components/ExplainPanel";
import EmailPanel from "./components/EmailPanel";
import SettingsDrawer from "./components/SettingsDrawer";
import AcceptedDrawer from "./components/AcceptedDrawer";
import Toast from "./components/Toast";
import { postSendEmail } from "./api";
import { deriveName } from "./candidateMeta";
import type { EmailStatus } from "./types";
import { useScreening } from "./useScreening";
import { useToast } from "./useToast";

export default function App() {
  const s = useScreening();
  const [emailStatus, setEmailStatus] = useState<Record<string, EmailStatus>>({});
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [acceptedOpen, setAcceptedOpen] = useState(false);
  const [sendingId, setSendingId] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [mailboxUrl, setMailboxUrl] = useState<string | null>(null);
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

  // Real SMTP send (backend/recourse_screen/emailer.py) — defaults to a
  // disposable Ethereal Email test mailbox, so this actually goes out over
  // SMTP but never reaches a real inbox unless the backend is reconfigured.
  async function handleSendEmail(id: string, to: string, subject: string, body: string) {
    setSendingId(id);
    setSendError(null);
    try {
      const result = await postSendEmail({ to, subject, body });
      setEmailStatus((prev) => ({ ...prev, [id]: "sent" }));
      setMailboxUrl(result.web);
      showToast(`Email sent to ${deriveName(id)} — check the test inbox`);
    } catch (e: unknown) {
      setSendError(e instanceof Error ? e.message : "Failed to send email");
    } finally {
      setSendingId(null);
    }
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
          onSelect={(id) => {
            setSendError(null); // don't let a stale error bleed onto the next candidate
            s.setSelectedId(id);
          }}
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
          sending={sendingId !== null && sendingId === s.selectedId}
          sendError={sendError}
          mailboxUrl={mailboxUrl}
          onPolish={() => void s.polishExplanation()}
          onSend={handleSend}
          onSendEmail={(id, to, subject, body) => void handleSendEmail(id, to, subject, body)}
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
