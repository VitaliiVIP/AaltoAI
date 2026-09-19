import GearIcon from "./GearIcon";

interface TopBarProps {
  jobTitle: string;
  settingsOpen: boolean;
  onOpenSettings: () => void;
}

export default function TopBar({ jobTitle, settingsOpen, onOpenSettings }: TopBarProps) {
  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-dot" />
        <span className="brand-name">Recourse</span>
      </div>

      <div className="role-pill">
        Hiring for <strong>{jobTitle}</strong>
      </div>

      <button
        className={"gear-btn" + (settingsOpen ? " spin" : "")}
        aria-label="Open settings"
        title="Scoring settings"
        onClick={onOpenSettings}
      >
        <GearIcon />
      </button>
    </header>
  );
}
