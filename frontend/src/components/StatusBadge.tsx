interface StatusBadgeProps {
  online: boolean;
  children: string;
}

export function StatusBadge({ online, children }: StatusBadgeProps) {
  return (
    <span className={`status-badge ${online ? "is-online" : "is-offline"}`}>
      <span className="status-dot" aria-hidden="true" />
      {children}
    </span>
  );
}
