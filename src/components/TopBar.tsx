import GearIcon from "./GearIcon";
import ModeControl from "./ModeControl";
import type { Mode } from "../apiTypes";

interface TopBarProps {
  jobTitle: string;
  mode: Mode;
  onModeChange: (m: Mode) => void;
  slotsN: number;
  onSlotsNChange: (n: number) => void;
  threshold: number | null;
  poolSize: number;
  settingsOpen: boolean;
  onOpenSettings: () => void;
}

export default function TopBar({
  jobTitle,
  mode,
  onModeChange,
  slotsN,
  onSlotsNChange,
  threshold,
  poolSize,
  settingsOpen,
  onOpenSettings,
}: TopBarProps) {
  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-dot" />
        <span className="brand-name">Recourse</span>
      </div>

      <div className="role-pill">
        Hiring for <strong>{jobTitle}</strong>
      </div>

      <ModeControl
        mode={mode}
        onModeChange={onModeChange}
        slotsN={slotsN}
        onSlotsNChange={onSlotsNChange}
        threshold={threshold}
        poolSize={poolSize}
      />

      <button
        className={"gear-btn" + (settingsOpen ? " spin" : "")}
        aria-label="Open job configuration"
        title="Job configuration & audit"
        onClick={onOpenSettings}
      >
        <GearIcon />
      </button>
    </header>
  );
}
