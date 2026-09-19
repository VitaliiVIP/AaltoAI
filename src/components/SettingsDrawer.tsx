import type { AuditSummary, JobSummary, Mode, ScreenResult } from "../apiTypes";
import { fmtValue, maxScoreOf } from "../present";

interface SettingsDrawerProps {
  open: boolean;
  job: JobSummary | null;
  result: ScreenResult | null;
  audit: AuditSummary | null;
  mode: Mode;
  slotsN: number;
  onClose: () => void;
}

/** Plain-English gloss for the two hand-authored causal constraints. */
const DEPENDENCY_GLOSS: Record<string, string> = {
  "x'[skills.kubernetes.held] <= x'[skills.docker.held]":
    "Kubernetes cannot be credited without Docker.",
  "delta[project_counts_by_topic.microservices] <= 2 + 1*delta[experience.backend_months]":
    "Microservice projects can only grow alongside backend experience.",
};

/**
 * Read-only. Everything here is employer policy the system is willing to be
 * held to — the weights, the costs, and the attributes it refuses to look at.
 * The live mode/N controls deliberately live in the top bar instead, so there
 * is only ever one source of truth for them.
 */
export default function SettingsDrawer({
  open,
  job,
  result,
  audit,
  mode,
  slotsN,
  onClose,
}: SettingsDrawerProps) {
  const total = job ? maxScoreOf(job) : 0;
  const knockoutResults = result?.decision.knockouts ?? [];

  return (
    <>
      <div className={"overlay" + (open ? " visible" : "")} onClick={onClose} />

      <aside
        className={"settings-drawer" + (open ? " open" : "")}
        aria-label="Job configuration"
        aria-hidden={!open}
      >
        <div className="drawer-header">
          <h2>Job configuration</h2>
          <button className="icon-btn" aria-label="Close" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="drawer-body">
          {!job && <p className="empty-note">Loading configuration…</p>}

          {job && (
            <>
              <p className="block-note">
                {job.title} · {job.job_id} · {job.version} · manifest {job.manifest_version} ·{" "}
                {job.horizon_months}-month horizon · {job.k_routes} routes
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
                <h3>Weighted features</h3>
                <table className="config-table">
                  <thead>
                    <tr>
                      <th>Feature</th>
                      <th>w × cap</th>
                      <th>max</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(job.score).map(([path, f]) => (
                      <tr key={path}>
                        <td>
                          {f.phrase}
                          <br />
                          <code>{path}</code>
                          <br />
                          <span className="cell-note">
                            {f.unit}, step {f.step_size} · {f.actionability.replace(/_/g, " ")}
                            {f.cost_per_step != null && <> · cost/step {f.cost_per_step}</>}
                            {f.max_delta > 0 && <> · max Δ {f.max_delta}</>}
                            {f.absent_prior > 0 && <> · absent prior {f.absent_prior}</>}
                            {f.typical_time_months != null && <> · typ. {f.typical_time_months} mo</>}
                            {f.is_causal && <> · causal</>}
                          </span>
                        </td>
                        <td className="num">
                          {f.weight} × {f.cap}
                        </td>
                        <td className="num">{f.weight * f.cap}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr>
                      <td>Maximum attainable score</td>
                      <td colSpan={2} className="num">
                        <strong>{total}</strong>
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </section>

              <section className="drawer-section">
                <h3>Mode</h3>
                <ul className="rule-list">
                  <li>
                    A — fixed threshold {job.mode.A.threshold} (ε {job.mode.A.margin_eps}, ρ{" "}
                    {job.mode.A.weight_shrink_rho})
                  </li>
                  <li>B — top {job.mode.B.slots_N} of the pool</li>
                </ul>
                <p className="block-note">
                  Currently running mode {mode}
                  {mode === "B" ? `, N = ${slotsN}` : ""}. Switch it in the top bar.
                </p>
              </section>

              <section className="drawer-section">
                <h3>Causal constraints</h3>
                <ul className="rule-list">
                  {job.dependencies.map((dep) => (
                    <li key={dep}>
                      <code>{dep}</code>
                      {DEPENDENCY_GLOSS[dep] && <div className="cell-note">{DEPENDENCY_GLOSS[dep]}</div>}
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
