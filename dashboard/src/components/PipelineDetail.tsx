import { useEvents } from "@/lib/api";
import { severityOf, SEVERITY_COLORS } from "@/lib/events";
import StatusBadge from "./StatusBadge";
import EventRow from "./EventRow";
import type { PipelineSummary } from "@/lib/types";

interface Props {
  id: string;
  summary: PipelineSummary | undefined;
  onClose: () => void;
}

export default function PipelineDetail({ id, summary, onClose }: Props) {
  const now = Date.now();
  const { data } = useEvents({ pipeline: id, from: now - 86400000, to: now });
  const events = data?.events?.slice(0, 10) ?? [];

  const lastType = summary?.lastEvent?.eventType ?? "UNKNOWN";
  const sev = severityOf(lastType);
  const dotColor = SEVERITY_COLORS[sev];

  const types = summary?.types ?? {};
  const hasBreach = (types["SLA_BREACH"] ?? 0) > 0;
  const hasWarning = (types["SLA_WARNING"] ?? 0) > 0;
  const slaStatus = hasBreach ? "Breach" : hasWarning ? "Warning" : "OK";
  const slaColor = hasBreach ? "text-failure" : hasWarning ? "text-warning" : "text-success";

  return (
    <div className="border border-border rounded-lg bg-surface shadow-md p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-full" style={{ backgroundColor: dotColor }} />
          <h3 className="font-semibold text-text">{id}</h3>
        </div>
        <button
          onClick={onClose}
          className="text-text-muted hover:text-text text-lg leading-none px-1"
        >
          &times;
        </button>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-4">
        <div className="text-center p-2 rounded bg-background">
          <div className={`text-lg font-bold ${slaColor}`}>{slaStatus}</div>
          <div className="text-xs text-text-muted">SLA Status</div>
        </div>
        <div className="text-center p-2 rounded bg-background">
          <div className="text-lg font-bold text-text">{summary?.events ?? 0}</div>
          <div className="text-xs text-text-muted">Events (24h)</div>
        </div>
        <div className="text-center p-2 rounded bg-background">
          {summary?.lastEvent ? (
            <>
              <StatusBadge type={summary.lastEvent.eventType} />
              <div className="text-xs text-text-muted mt-1">Last Event</div>
            </>
          ) : (
            <div className="text-xs text-text-muted">No events</div>
          )}
        </div>
      </div>

      {events.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-2">
            Recent Events
          </h4>
          <div className="border border-border rounded-lg overflow-hidden">
            {events.map((e, i) => (
              <EventRow key={`${e.timestamp}-${i}`} event={e} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
