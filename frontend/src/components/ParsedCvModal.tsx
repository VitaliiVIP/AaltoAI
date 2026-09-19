import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CvParse, ParsedAttribute } from "../apiTypes";
import { getCvParse, isAbortError } from "../api";
import { deriveName } from "../candidateMeta";
import {
  derivationNote,
  fmtValue,
  groupAttributes,
  highlightSegments,
  shortId,
} from "../present";

interface ParsedCvModalProps {
  open: boolean;
  candidateId: string | null;
  jobId: string;
  onClose: () => void;
}

/**
 * The parse, side by side with the CV it came from.
 *
 * The claim this screen has to support is "here is every attribute we read, and
 * here are the exact words we read it from" — so the two panes are driven by one
 * selection, and an attribute with nothing to highlight says why rather than
 * quietly rendering an empty list.
 */
export default function ParsedCvModal({
  open,
  candidateId,
  jobId,
  onClose,
}: ParsedCvModalProps) {
  const [parse, setParse] = useState<CvParse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);

  const textPane = useRef<HTMLDivElement>(null);
  const attrPane = useRef<HTMLDivElement>(null);
  const rowRefs = useRef(new Map<number, HTMLLIElement>());
  const markRefs = useRef(new Map<number, HTMLElement>());

  useEffect(() => {
    if (!open || !candidateId) return;
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    setSelected(null);
    // Drop the previous candidate's parse rather than showing it under this
    // candidate's name for as long as the fetch takes.
    setParse(null);
    getCvParse(candidateId, jobId, ctrl.signal)
      .then((p) => {
        setParse(p);
        setLoading(false);
      })
      .catch((e: unknown) => {
        if (isAbortError(e)) return;
        setParse(null);
        setError(e instanceof Error ? e.message : "Could not load the parse");
        setLoading(false);
      });
    return () => ctrl.abort();
  }, [open, candidateId, jobId]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const attributes = useMemo(() => parse?.attributes ?? [], [parse]);
  const segments = useMemo(
    () => (parse ? highlightSegments(parse.text, attributes) : []),
    [parse, attributes],
  );
  const groups = useMemo(() => groupAttributes(attributes), [attributes]);

  // Where a given attribute is first highlighted, so selecting it can scroll the
  // text pane to the right place without searching the DOM.
  const firstMarkOf = useMemo(() => {
    const out = new Map<number, number>();
    for (const seg of segments) {
      for (const i of seg.attrs) if (!out.has(i)) out.set(i, seg.start);
    }
    return out;
  }, [segments]);

  const located = useMemo(
    () => attributes.reduce((n, a) => n + a.evidence.filter((e) => e.verified).length, 0),
    [attributes],
  );

  const select = useCallback(
    (index: number, from: "row" | "mark") => {
      setSelected(index);
      // Only the other pane moves: the one that was clicked is already where the
      // reader is looking, and scrolling it would pull the click out from under them.
      const start = firstMarkOf.get(index);
      if (from === "row") centreWithin(textPane.current, start == null ? null : markRefs.current.get(start));
      else centreWithin(attrPane.current, rowRefs.current.get(index));
    },
    [firstMarkOf],
  );

  if (!open || !candidateId) return null;

  return (
    <div className="cv-modal-overlay" onClick={onClose}>
      <div
        className="cv-modal parse-modal"
        role="dialog"
        aria-label="What we read from this CV"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="parse-header">
          <div>
            <h2>What we read from this CV</h2>
            <p className="parse-sub">
              {deriveName(candidateId)}
              {parse && (
                <>
                  {" "}
                  · {attributes.length} attributes · {located} quotes located ·{" "}
                  {parse.provenance.extractor_model} · {parse.provenance.prompt_version}
                </>
              )}
            </p>
          </div>
          <button className="icon-btn" aria-label="Close" onClick={onClose}>
            ✕
          </button>
        </div>

        {loading && <div className="loading-bar" role="status" aria-label="Loading the parse" />}
        {error && <div className="panel-error parse-error">{error}</div>}

        {parse && (
          <div className="parse-body">
            <div className="parse-pane parse-text-pane" ref={textPane}>
              <p className="block-note">
                Highlights are the exact character ranges the extractor quoted. Click one to find
                the attribute it produced.
              </p>
              <pre className="parse-text">
                {segments.map((seg) =>
                  seg.attrs.length === 0 ? (
                    <span key={seg.start}>{seg.text}</span>
                  ) : (
                    <mark
                      key={seg.start}
                      ref={(el) => {
                        if (el) markRefs.current.set(seg.start, el);
                        else markRefs.current.delete(seg.start);
                      }}
                      className={
                        "parse-mark" +
                        (selected != null && seg.attrs.includes(selected) ? " active" : "")
                      }
                      title={seg.attrs.map((i) => attributes[i].label).join(" · ")}
                      onClick={() => select(seg.attrs[0], "mark")}
                    >
                      {seg.text}
                    </mark>
                  ),
                )}
              </pre>
              <p className="parse-foot">
                cv {shortId(parse.provenance.cv_sha256)} · extracted {parse.provenance.extracted_at}
              </p>
            </div>

            <div className="parse-pane parse-attr-pane" ref={attrPane}>
              <p className="block-note">
                Every attribute the screen holds for this candidate. ★ marks the ones this job
                actually decides on.
              </p>
              {groups.map((group) => (
                <section className="parse-group" key={group.group}>
                  <h3 className="setting-divider">{group.group}</h3>
                  <ul className="parse-list">
                    {group.items.map(({ attr, index }) => (
                      <AttributeRow
                        key={attr.path + index}
                        attr={attr}
                        active={selected === index}
                        hasMark={firstMarkOf.has(index)}
                        onSelect={() => select(index, "row")}
                        register={(el) => {
                          if (el) rowRefs.current.set(index, el);
                          else rowRefs.current.delete(index);
                        }}
                      />
                    ))}
                  </ul>
                </section>
              ))}
              {parse.unmatched_skills.length > 0 && (
                <section className="parse-group">
                  <h3 className="setting-divider">Read but not usable</h3>
                  <p className="block-note">
                    The CV named these and the taxonomy has no concept for them, so nothing is
                    scored on them either way: {parse.unmatched_skills.join(", ")}.
                  </p>
                </section>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Centre an element in its pane.
 *
 * Deliberately not `scrollIntoView`: that walks every scrollable ancestor, and
 * in a fixed-position modal it ends up scrolling the page underneath instead of
 * the pane you meant. The jump is instant for the same reason the CV modal has
 * no transitions — following a highlight should land, not glide.
 */
function centreWithin(pane: HTMLElement | null, el: HTMLElement | undefined | null) {
  if (!pane || !el) return;
  pane.scrollTop = el.offsetTop - pane.clientHeight / 2 + el.offsetHeight / 2;
}

interface AttributeRowProps {
  attr: ParsedAttribute;
  active: boolean;
  hasMark: boolean;
  onSelect: () => void;
  register: (el: HTMLLIElement | null) => void;
}

function AttributeRow({ attr, active, hasMark, onSelect, register }: AttributeRowProps) {
  const absent = attr.derivation === "absent";
  return (
    <li
      ref={register}
      className={"parse-row" + (active ? " active" : "") + (absent ? " absent" : "")}
    >
      <button className="parse-row-btn" onClick={onSelect} disabled={!hasMark}>
        <span className="parse-row-head">
          <span className="parse-label">
            {attr.scored && <span className="parse-star">★</span>}
            {attr.label}
          </span>
          <span className="parse-value">{fmtValue(attr.value, attr.unit ?? "")}</span>
        </span>
        {attr.detail && <span className="parse-detail">{attr.detail}</span>}
        <span className="parse-meta">
          {derivationNote(attr.derivation)} · {attr.confidence} confidence ·{" "}
          <code>{attr.path}</code>
        </span>
        {attr.evidence.map((ev, i) => (
          <span className={"parse-quote" + (ev.verified ? "" : " unlocated")} key={i}>
            “{ev.quote}”
            {!ev.verified && <em> — not found in the CV text, so it was not trusted</em>}
          </span>
        ))}
      </button>
    </li>
  );
}
