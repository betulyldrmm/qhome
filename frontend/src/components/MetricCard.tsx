interface MetricCardProps {
  label: string;
  value: string;
  detail?: string;
  percent?: number | null;
  icon: string;
  href?: string;
}

export function MetricCard({ label, value, detail, percent, icon, href }: MetricCardProps) {
  const bounded = percent == null ? undefined : Math.max(0, Math.min(100, percent));
  return (
    <article className="metric-card">
      <div className="metric-heading">
        <span className="metric-icon" aria-hidden="true">{icon}</span>
        <span>{label}</span>
      </div>
      {href ? <a className="metric-value metric-link" href={href}>{value}</a> : <strong className="metric-value">{value}</strong>}
      {bounded !== undefined && <div className="metric-progress" aria-label={`${label} ${Math.round(bounded)}%`}>
        <span className={bounded > 90 ? "is-high" : ""} style={{ width: `${bounded}%` }} />
      </div>}
      {detail && <p className="metric-detail">{detail}</p>}
    </article>
  );
}
