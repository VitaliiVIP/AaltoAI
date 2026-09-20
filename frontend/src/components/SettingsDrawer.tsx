import { useState } from "react";
import type { AuditSummary, JobSummary, Mode, ScreenResult } from "../apiTypes";
import { fmtValue, maxScoreOf } from "../present";
import { useJobEditor } from "../useJobEditor";
import BudgetEditor from "./BudgetEditor";
import DraftFromAd from "./DraftFromAd";
import KnockoutChecklist from "./KnockoutChecklist";

interface SettingsDrawerProps {
  open: boolean;
  job: JobSummary | null;
  result: ScreenResult | null;
  audit: AuditSummary | null;
  mode: Mode;
  slotsN: number;
  poolSize: number;
  onClose: () => void;
  onJobSaved: (job: JobSummary) => void;
}

/**
 * Job configuration, in two halves.
 *
 * **Review** is everything the system is willing to be held to: the budget, the
 * costs, the attributes it refuses to look at, the audit chain. It stays
 * read-only, because it includes things no recruiter should be editing.
 *
 * **Edit** is the subset that is genuinely an employer value judgement — the
 * point budget, the hard requirements, and where the bar sits. Causal
 * constraints appear in Review and are absent from Edit on purpose: they are
 * facts about how skills are acquired, and they belong to the manifest.
 */
export default function SettingsDrawer({
  open,
  job,
  result,
  audit,
  mode,
  slotsN,
  poolSize,
  onClose,
  onJobSaved,
}: SettingsDrawerProps) {
  const [tab, setTab] = useState<"review" | "edit">("review");
  const editor = useJobEditor(job, onJobSaved);

  const total = job ? maxScoreOf(job) : 0;
  const knockoutResults = result?.decision.knockouts ?? [];

  return (
    <>
      <div className={"overlay" + (open ? " visible" : "")} onClick={onClose} />

      <aside
        className={"settings-drawer" + (open ? " open" : "") + (tab === "edit" ? " editing" : "")}
        aria-label="Job configuration"
        aria-hidden={!open}
      >
        <div className="drawer-header">
          <h2>Job configuration</h2>
          <div className="drawer-tabs" role="tablist">
            <button
              role="tab"
              aria-selected={tab === "review"}
              className={tab === "review" ? "active" : ""}
              onClick={() => setTab("review")}
            >
              Review
            </button>
            <button
              role="tab"
              aria-selected={tab === "edit"}
              className={tab === "edit" ? "active" : ""}
              onClick={() => setTab("edit")}
            >
              Edit{editor.dirty ? " •" : ""}
            </button>
          </div>
          <button className="icon-btn" aria-label="Close" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="drawer-body">
          {!job && <p className="empty-note">Loading configuration…</p>}

          {job && tab === "edit" && (
            <>
              {editor.error && <p className="bad">{editor.error}</p>}
              {!editor.spec && <p className="empty-note">Loading the editor…</p>}

              {editor.spec && editor.catalogue && (
                <>
                  <section className="drawer-section">
                    <h3>Start from the advert</h3>
                    <DraftFromAd
                      draft={editor.draft}
                      busy={editor.phase === "drafting"}
                      onDraft={(text) => void editor.draftFromAd(text)}
                    />
                  </section>

                  <section className="drawer-section">
                    <h3>Hard requirements</h3>
                    <KnockoutChecklist
                      features={editor.catalogue.features}
                      knockouts={editor.spec.knockouts}
                      results={knockoutResults}
                      onToggle={editor.toggleKnockout}
                      onReplace={editor.replaceKnockout}
                    />
                  </section>

                  <section className="drawer-section">
                    <h3>What the role is worth</h3>
                    <BudgetEditor
                      spec={editor.spec}
                      byPath={editor.byPath}
                      unused={editor.unused}
                      allocated={editor.allocated}
                      budgetTotal={job.budget_total}
                      preflight={editor.preflight}
                      quotes={editor.draft?.quotes ?? {}}
                      onPoints={editor.setPoints}
                      onCap={editor.setCap}
                      onAdd={editor.addCriterion}
                      onRemove={editor.removeCriterion}
                    />
                  </section>

                  <section className="drawer-section">
                    <h3>Where the bar sits</h3>
                    <label className="bar-control">
                      <span>
                        Top <strong>{editor.spec.slots_n}</strong> of the pool advance
                        <span className="cell-note"> (mode B)</span>
                      </span>
                      <input
                        type="range"
                        min={1}
                        max={Math.max(1, poolSize)}
                        value={editor.spec.slots_n}
                        onChange={(e) => editor.setSlotsN(Number(e.target.value))}
                      />
                    </label>
                    <label className="bar-control">
                      <span>
                        Fixed threshold <strong>{editor.spec.threshold}</strong> of{" "}
                        {job.budget_total}
                        <span className="cell-note"> (mode A)</span>
                      </span>
                      <input
                        type="range"
                        min={1}
                        max={job.budget_total}
                        value={editor.spec.threshold}
                        onChange={(e) => editor.setThreshold(Number(e.target.value))}
                      />
                    </label>
                    <p className="block-note">
                      Currently running mode {mode}
                      {mode === "B" ? `, N = ${slotsN}` : ""}. Switch it in the top bar.
                    </p>
                  </section>

                  <div className="drawer-actions">
                    <button
                      className="primary-btn"
                      disabled={!editor.dirty || editor.phase === "saving" || !editor.preflight?.ok}
                      onClick={() => void editor.save()}
                    >
                      {editor.phase === "saving" ? "Saving…" : "Save and re-screen"}
                    </button>
                    <button
                      className="link-btn"
                      disabled={!editor.dirty}
                      onClick={() => void editor.revert()}
                    >
                      discard changes
                    </button>
                  </div>
                </>
              )}
            </>
          )}

          {job && tab === "review" && (
            <>
              <p className="block-note">
                {job.title} · {job.job_id} · {job.version} · manifest {job.manifest_version} ·{" "}
                {job.horizon_months}-month horizon · {job.k_routes}-route recourse
                {result && (
                  <>
                    {" "}
                    · screened {result.as_of} · {result.versions.model}
                  </>
                )}
              </p>

              <section className="drawer-section">
                <h3>Hard requirements (knockouts)</h3>
                <p className="block-note">
                  Binary and job-related. Evaluated before any weighted score and never traded
                  off against it.
                </p>
                <ul className="rule-list">
                  {job.knockouts.map((rule) => {
                    const hit = knockoutResults.find((k) => k.rule === rule);
                    return (
                      <li key={rule}>
                        <code>{rule}</code>
                        {hit && (
                          <span className={hit.passed ? "ok" : "bad"}>
                            {" "}
                            {hit.passed ? "✓" : "✗"} currently {fmtValue(hit.current_value)} ·{" "}
                            {hit.actionability.replace(/_/g, " ")}
                          </span>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </section>

              <section className="drawer-section">
                <h3>The point budget</h3>
                <table className="config-table">
                  <thead>
                    <tr>
                      <th>Criterion</th>
                      <th className="num">Points</th>
                      <th>Full marks at</th>
                      <th className="num">per step</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(job.score)
                      .sort((a, b) => b[1].points - a[1].points)
                      .map(([path, f]) => (
                        <tr key={path}>
                          <td>
                            {f.phrase}
                            <br />
                            <code>{path}</code>
                            <br />
                            <span className="cell-note">
                              {f.actionability.replace(/_/g, " ")}
                              {f.cost_per_step != null && <> · cost {f.cost_per_step}/step</>}
                              {f.typical_time_months != null && <> · typ. {f.typical_time_months} mo</>}
                              {f.absent_prior > 0 && <> · absent prior {f.absent_prior}</>}
                            </span>
                          </td>
                          <td className="num">
                            <strong>{f.points}</strong>
                          </td>
                          <td className="cell-note">{fmtValue(f.full_marks_at, f.unit)}</td>
                          <td className="num cell-note">{f.weight}</td>
                        </tr>
                      ))}
                  </tbody>
                  <tfoot>
                    <tr>
                      <td>Whole budget</td>
                      <td className="num">
                        <strong>{total}</strong>
                      </td>
                      <td colSpan={2} className="cell-note">
                        a score is a percentage of the job
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </section>

              <section className="drawer-section">
                <h3>Mode</h3>
                <ul className="rule-list">
                  <li>B — top {job.mode.B.slots_N} of the pool (default)</li>
                  <li>
                    A — fixed threshold {job.mode.A.threshold} of {job.budget_total} (ε{" "}
                    {job.mode.A.margin_eps}, ρ {job.mode.A.weight_shrink_rho})
                  </li>
                </ul>
                <p className="block-note">
                  Currently running mode {mode}
                  {mode === "B" ? `, N = ${slotsN}` : ""}. Switch it in the top bar.
                </p>
              </section>

              <section className="drawer-section">
                <h3>Causal constraints</h3>
                <p className="block-note">
                  Facts about how these skills are acquired, declared by the manifest for the
                  whole job family. Not an employer setting, so not editable here.
                </p>
                <ul className="rule-list">
                  {job.dependencies.map((dep) => (
                    <li key={dep.rule}>
                      <code>{dep.rule}</code>
                      <div className="cell-note">{dep.gloss}</div>
                    </li>
                  ))}
                </ul>
              </section>

              <section className="drawer-section">
                <h3>Never used</h3>
                <p className="block-note">
                  Not representable in the profile, and not readable by the scorer or the solver.
                </p>
                <p className="protected-list">{job.protected_never_use.join(", ")}</p>
                {result && (
                  <>
                    <p className="protected-list">{result.profile.never_extract.join(", ")}</p>
                    <ul className="rule-list">
                      {Object.entries(result.assertions).map(([k, v]) => (
                        <li key={k}>
                          <span className={v ? "ok" : "bad"}>{v ? "✓" : "✗"}</span>{" "}
                          {k.replace(/_/g, " ")}
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </section>

              <section className="drawer-section">
                <h3>Audit chain</h3>
                {audit ? (
                  <p className="block-note">
                    <span className={audit.chain_ok ? "ok" : "bad"}>
                      {audit.chain_ok ? "✓ chain verified" : "✗ chain broken"}
                    </span>{" "}
                    · {audit.count} records
                    {audit.first_bad_index != null && <> · first bad index {audit.first_bad_index}</>}
                  </p>
                ) : (
                  <p className="empty-note">Audit log unavailable.</p>
                )}
              </section>
            </>
          )}
        </div>
      </aside>
    </>
  );
}
