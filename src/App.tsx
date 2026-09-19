import { useState } from "react";
import TopBar from "./components/TopBar";
import CvList from "./components/CvList";
import ExplainPanel from "./components/ExplainPanel";
import EmailPanel from "./components/EmailPanel";
import SettingsDrawer from "./components/SettingsDrawer";
import Toast from "./components/Toast";
import { CANDIDATES, JOB } from "./data";
import type { EmailStatus } from "./types";
import { useScoringSettings } from "./useScoringSettings";
import { useToast } from "./useToast";

export default function App() {
  const [selectedId, setSelectedId] = useState(CANDIDATES[0].id);
  const [emailStatus, setEmailStatus] = useState<Record<string, EmailStatus>>({});
  const [settingsOpen, setSettingsOpen] = useState(false);

  const { settings, update } = useScoringSettings();
  const { message, visible, showToast } = useToast();

  const selected = CANDIDATES.find((c) => c.id === selectedId) ?? CANDIDATES[0];

  function handleSend(id: string) {
    const candidate = CANDIDATES.find((c) => c.id === id);
    setEmailStatus((prev) => ({ ...prev, [id]: "sent" }));
    showToast(`Email sent to ${candidate?.name}`);
  }

  function handleDecline(id: string) {
    const candidate = CANDIDATES.find((c) => c.id === id);
    setEmailStatus((prev) => ({ ...prev, [id]: "declined" }));
    showToast(`Draft discarded for ${candidate?.name}`);
  }

  function handleSaveSettings() {
    setSettingsOpen(false);
    showToast("Scoring settings saved (demo only)");
  }

  return (
    <>
      <TopBar jobTitle={JOB.title} settingsOpen={settingsOpen} onOpenSettings={() => setSettingsOpen(true)} />

      <main className="layout">
        <CvList
          candidates={CANDIDATES}
          selectedId={selectedId}
          emailStatus={emailStatus}
          onSelect={setSelectedId}
        />
        <ExplainPanel candidate={selected} />
        <EmailPanel
          candidate={selected}
          status={emailStatus[selected.id]}
          onSend={handleSend}
          onDecline={handleDecline}
        />
      </main>

      <SettingsDrawer
        open={settingsOpen}
        settings={settings}
        onChange={update}
        onClose={() => setSettingsOpen(false)}
        onSave={handleSaveSettings}
      />

      <Toast message={message} visible={visible} />
    </>
  );
}
