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

  // Email sending is turned off for the public demo. The site is
  // unauthenticated, so a real `/send-email` would be an open relay through
  // the Mailgun domain; the endpoint is gone (the sender itself is still in
  // backend/recourse_screen/emailer.py). The button behaves exactly as it did
  // — the candidate is marked as emailed for this session — but nothing leaves
  // the browser. `to`, `subject` and `body` are accepted so the panel's
  // contract is unchanged.
  //
  // `declined` distinguishes an Accept send from a Decline-and-send-rejection
  // send: only the former is an acceptance. Without this, a rejection sent to
  // a candidate who cleared the bar would land back in the accepted list
  // because their backend decision is still "advance".
  function handleSendEmail(
    id: string,
    _to: string,
    _subject: string,
    _body: string,
    declined: boolean,
  ) {
    const status: EmailStatus = declined ? "rejected" : "sent";
    setEmailStatus((prev) => ({ ...prev, [id]: status }));
    showToast(declined ? `Rejection sent to ${deriveName(id)}` : `Email sent to ${deriveName(id)}`);
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

  // Deleting a CV is turned off for the public demo: the pool is shared by
  // every visitor, so `DELETE /candidates/{id}` no longer exists. The button
  // still works as far as this session can tell — the candidate disappears
  // from the list, the drawer and the counts — but the backend pool is
  // untouched and a reload brings them back.
  function handleDeleteCv(id: string) {
    const name = deriveName(id);
    if (!window.confirm(`Permanently delete ${name}'s CV? This cannot be undone.`)) return;
    setEmailStatus((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
    handleDelete(id);
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
          onSelect={s.setSelectedId}
          onRetry={() => void s.refreshPool()}
          onDelete={handleDelete}
        />
        <ExplainPanel
          result={s.result}
          row={s.selectedRow}
          job={s.job}
          maxScore={s.maxScore}
          phase={s.screenPhase}
          error={s.screenError}
          onDeleteCv={handleDeleteCv}
        />
        <EmailPanel
          result={s.result}
          jobTitle={s.job?.title ?? ""}
          status={s.selectedId ? emailStatus[s.selectedId] : undefined}
          onSend={handleSend}
          onSendEmail={handleSendEmail}
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
        // Saving is session-only in the public demo (see useJobEditor.save):
        // the toast is the same, but nothing is written and no re-screen runs.
        onJobSaved={() => showToast(`Saved ${s.job?.title ?? "job"}`)}
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
