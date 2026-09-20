import { useMemo, useState } from "react";
import TopBar from "./components/TopBar";
import CvList from "./components/CvList";
import ExplainPanel from "./components/ExplainPanel";
import EmailPanel from "./components/EmailPanel";
import SettingsDrawer from "./components/SettingsDrawer";
import AcceptedDrawer from "./components/AcceptedDrawer";
import Toast from "./components/Toast";
import { ApiError, postSendEmail } from "./api";
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
  const [deletedIds, setDeletedIds] = useState<Set<string>>(new Set());
  const { message, visible, showToast } = useToast();

  // Deleted candidates (from the sent-CVs view) disappear everywhere —
  // list, "in play" drawer, counts — without touching the backend pool.
  const visiblePool = useMemo(
    () => s.pool.filter((row) => !deletedIds.has(row.candidate_id)),
    [s.pool, deletedIds],
  );

  // In play = accepted (cleared the bar and actually accepted, not just
  // "sent" from the rejection-with-recourse flow which reuses that status)
  // OR kept for further review instead of rejected.
  const acceptedCount = useMemo(
    () =>
      visiblePool.filter((row) => {
        const status = emailStatus[row.candidate_id];
        return (status === "sent" && row.decision === "advance") || status === "declined";
      }).length,
    [visiblePool, emailStatus],
  );

  function handleSend(id: string) {
    setEmailStatus((prev) => ({ ...prev, [id]: "sent" }));
    showToast(`Email sent to ${deriveName(id)}`);
  }

  // Real SMTP/Mailgun send (backend/recourse_screen/emailer.py). Marked as
  // sent locally even when the real delivery fails (e.g. an unauthorized
  // recipient on a Mailgun sandbox domain) — a demo shouldn't get stuck on
  // a provider restriction, and the failure reason stays visible below the
  // form either way, with a delete option in the sent-CVs list.
  //
  // `declined` distinguishes an Accept send from a Decline-and-send-rejection
  // send — both are real emails ("sent"-like everywhere that only cares
  // whether an email went out), but only the former is an acceptance. Without
  // this, a rejection sent to a candidate who cleared the bar would land back
  // in the accepted list because their backend decision is still "advance".
  async function handleSendEmail(
    id: string,
    to: string,
    subject: string,
    body: string,
    declined: boolean,
  ) {
    setSendingId(id);
    setSendError(null);
    const status: EmailStatus = declined ? "rejected" : "sent";
    try {
      const result = await postSendEmail({ to, subject, body });
      setEmailStatus((prev) => ({ ...prev, [id]: status }));
      setMailboxUrl(result.web);
      showToast(
        declined
          ? `Rejection sent to ${deriveName(id)} — check the test inbox`
          : `Email sent to ${deriveName(id)} — check the test inbox`,
      );
    } catch (e: unknown) {
      setEmailStatus((prev) => ({ ...prev, [id]: status }));
      setSendError(e instanceof Error ? e.message : "Failed to send email");
      showToast(`Marked as sent for ${deriveName(id)} — real delivery failed`);
    } finally {
      setSendingId(null);
    }
  }

  function handleDecline(id: string) {
    setEmailStatus((prev) => ({ ...prev, [id]: "declined" }));
    showToast(`Kept for further review — ${deriveName(id)}`);
  }

  function handleRemove(id: string) {
    setEmailStatus((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
    showToast(`${deriveName(id)} moved back to the applicant pool`);
  }

  function handleDelete(id: string) {
    setDeletedIds((prev) => new Set(prev).add(id));
    if (s.selectedId === id) {
      const fallback = visiblePool.find((r) => r.candidate_id !== id);
      s.setSelectedId(fallback ? fallback.candidate_id : null);
    }
    showToast(`Deleted ${deriveName(id)}`);
  }

  // Real, server-side deletion — the CV's cached text/profile/upload are gone,
  // not just hidden. The backend refuses (403) for the fixed demo pool
  // (cv1..cv11); that's a permanent property of the candidate, not an error,
  // so it surfaces as an alert rather than a toast.
  async function handleDeleteCv(id: string) {
    const name = deriveName(id);
    if (!window.confirm(`Permanently delete ${name}'s CV? This cannot be undone.`)) return;
    try {
      await s.deleteCv(id);
      setEmailStatus((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      showToast(`Deleted ${name}'s CV`);
    } catch (e: unknown) {
      if (e instanceof ApiError && e.status === 403) {
        window.alert(e.message);
      } else {
        showToast(e instanceof Error ? e.message : "Failed to delete CV");
      }
    }
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
        poolSize={visiblePool.length}
        settingsOpen={settingsOpen}
        onOpenSettings={() => setSettingsOpen(true)}
        acceptedCount={acceptedCount}
        acceptedOpen={acceptedOpen}
        onOpenAccepted={() => setAcceptedOpen(true)}
      />

      <main className="layout">
        <CvList
          pool={visiblePool}
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
          onDelete={handleDelete}
        />
        <ExplainPanel
          result={s.result}
          row={s.selectedRow}
          job={s.job}
          maxScore={s.maxScore}
          phase={s.screenPhase}
          error={s.screenError}
          onDeleteCv={(id) => void handleDeleteCv(id)}
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
          onSendEmail={(id, to, subject, body, declined) =>
            void handleSendEmail(id, to, subject, body, declined)
          }
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
        poolSize={visiblePool.length}
        onClose={() => setSettingsOpen(false)}
        onJobSaved={(job) => {
          s.applyJob(job);
          showToast(`Saved — re-screening against ${job.title}`);
        }}
      />

      <AcceptedDrawer
        open={acceptedOpen}
        pool={visiblePool}
        emailStatus={emailStatus}
        onClose={() => setAcceptedOpen(false)}
        onRemove={handleRemove}
      />

      <Toast message={message} visible={visible} />
    </>
  );
}
