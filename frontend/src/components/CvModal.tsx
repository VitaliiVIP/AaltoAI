import { useEffect, useState } from "react";
import { assetsFor, deriveName } from "../candidateMeta";

interface CvModalProps {
  candidateId: string;
  hasPdf: boolean;
  onClose: () => void;
}

/** The full first page of a CV, over everything else. Escape or a click outside closes it. */
export default function CvModal({ candidateId, hasPdf, onClose }: CvModalProps) {
  const [broken, setBroken] = useState(false);
  const name = deriveName(candidateId);
  const { thumbUrl } = assetsFor(candidateId, hasPdf);

  useEffect(() => setBroken(false), [thumbUrl]);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div className="cv-modal-overlay" onClick={onClose}>
      <div className="cv-modal" onClick={(e) => e.stopPropagation()}>
        <button className="icon-btn cv-modal-close" aria-label="Close CV" onClick={onClose}>
          ✕
        </button>
        {broken ? (
          <p className="cv-modal-empty">
            No CV file on record for {name}. A CV added as plain text has nothing to show
            here; the parsed text is under “What we read”.
          </p>
        ) : (
          <img src={thumbUrl} alt={`${name} full CV`} onError={() => setBroken(true)} />
        )}
      </div>
    </div>
  );
}
