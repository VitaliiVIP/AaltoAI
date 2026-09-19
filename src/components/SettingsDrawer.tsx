import { STRICTNESS_LABELS, type ScoringSettings } from "../useScoringSettings";

interface SettingsDrawerProps {
  open: boolean;
  settings: ScoringSettings;
  onChange: <K extends keyof ScoringSettings>(key: K, value: ScoringSettings[K]) => void;
  onClose: () => void;
  onSave: () => void;
}

export default function SettingsDrawer({ open, settings, onChange, onClose, onSave }: SettingsDrawerProps) {
  return (
    <>
      <div className={"overlay" + (open ? " visible" : "")} onClick={onClose} />

      <aside className={"settings-drawer" + (open ? " open" : "")} aria-label="Scoring settings">
        <div className="drawer-header">
          <h2>Scoring settings</h2>
          <button className="icon-btn" aria-label="Close settings" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="drawer-body">
          <div className="setting-group">
            <label className="setting-label" htmlFor="modelSelect">
              Scoring model
            </label>
            <select
              id="modelSelect"
              className="setting-select"
              value={settings.model}
              onChange={(e) => onChange("model", e.target.value)}
            >
              <option>GPT-4o</option>
              <option>Claude Sonnet 4.5</option>
              <option>Llama 3 70B</option>
              <option>Internal fine-tuned model</option>
            </select>
          </div>

          <div className="setting-group">
            <div className="setting-label-row">
              <label className="setting-label" htmlFor="temperature">
                Temperature
              </label>
              <span className="setting-value">{settings.temperature.toFixed(2)}</span>
            </div>
            <input
              id="temperature"
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={settings.temperature}
              className="slider"
              onChange={(e) => onChange("temperature", parseFloat(e.target.value))}
            />
          </div>

          <div className="setting-group">
            <div className="setting-label-row">
              <label className="setting-label" htmlFor="strictness">
                Scoring strictness
              </label>
              <span className="setting-value">{STRICTNESS_LABELS[settings.strictness]}</span>
            </div>
            <input
              id="strictness"
              type="range"
              min={0}
              max={2}
              step={1}
              value={settings.strictness}
              className="slider"
              onChange={(e) => onChange("strictness", parseInt(e.target.value, 10))}
            />
            <div className="slider-ticks">
              <span>Lenient</span>
              <span>Balanced</span>
              <span>Strict</span>
            </div>
          </div>

          <div className="setting-divider">Score weighting</div>

          <WeightSlider
            id="wSkills"
            label="Skills match"
            value={settings.weightSkills}
            onChange={(v) => onChange("weightSkills", v)}
          />
          <WeightSlider
            id="wExperience"
            label="Experience"
            value={settings.weightExperience}
            onChange={(v) => onChange("weightExperience", v)}
          />
          <WeightSlider
            id="wProjects"
            label="Projects"
            value={settings.weightProjects}
            onChange={(v) => onChange("weightProjects", v)}
          />
          <WeightSlider
            id="wEducation"
            label="Education"
            value={settings.weightEducation}
            onChange={(v) => onChange("weightEducation", v)}
          />

          <div className="setting-divider">Governance</div>

          <div className="setting-group toggle-row">
            <div>
              <label className="setting-label" htmlFor="toggleRecourse">
                Algorithmic recourse suggestions
              </label>
              <p className="setting-hint">Show applicants what would change the outcome</p>
            </div>
            <label className="switch">
              <input
                id="toggleRecourse"
                type="checkbox"
                checked={settings.recourseEnabled}
                onChange={(e) => onChange("recourseEnabled", e.target.checked)}
              />
              <span className="switch-track" />
            </label>
          </div>

          <div className="setting-group toggle-row">
            <div>
              <label className="setting-label" htmlFor="toggleAnon">
                Anonymise PII before scoring
              </label>
              <p className="setting-hint">Strip name, photo, age before the model sees the CV</p>
            </div>
            <label className="switch">
              <input
                id="toggleAnon"
                type="checkbox"
                checked={settings.anonymisePII}
                onChange={(e) => onChange("anonymisePII", e.target.checked)}
              />
              <span className="switch-track" />
            </label>
          </div>

          <div className="setting-group toggle-row">
            <div>
              <label className="setting-label" htmlFor="toggleHuman">
                Require human approval
              </label>
              <p className="setting-hint">No rejection is final without a recruiter's click</p>
            </div>
            <label className="switch">
              <input id="toggleHuman" type="checkbox" checked disabled />
              <span className="switch-track" />
            </label>
          </div>

          <div className="setting-group">
            <div className="setting-label-row">
              <label className="setting-label" htmlFor="wRecourseCount">
                Diverse recourse paths to show
              </label>
              <span className="setting-value">{settings.recoursePathCount}</span>
            </div>
            <input
              id="wRecourseCount"
              type="range"
              min={1}
              max={5}
              step={1}
              value={settings.recoursePathCount}
              className="slider"
              onChange={(e) => onChange("recoursePathCount", parseInt(e.target.value, 10))}
            />
          </div>
        </div>

        <div className="drawer-footer">
          <button className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={onSave}>
            Save settings
          </button>
        </div>
      </aside>
    </>
  );
}

interface WeightSliderProps {
  id: string;
  label: string;
  value: number;
  onChange: (value: number) => void;
}

function WeightSlider({ id, label, value, onChange }: WeightSliderProps) {
  return (
    <div className="setting-group">
      <div className="setting-label-row">
        <label className="setting-label" htmlFor={id}>
          {label}
        </label>
        <span className="setting-value">{value}%</span>
      </div>
      <input
        id={id}
        type="range"
        min={0}
        max={100}
        step={5}
        value={value}
        className="slider"
        onChange={(e) => onChange(parseInt(e.target.value, 10))}
      />
    </div>
  );
}
