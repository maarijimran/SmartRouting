"use client";

// Dependency-free SVG charts. Estimated and measured series are always drawn separately.

function scale(max, height) {
  return (v) => (max > 0 ? (v / max) * height : 0);
}

export function GroupedBars({ title, data, seriesA, seriesB, format = (v) => v.toFixed(4) }) {
  // data: [{label, a, b}] where b may be undefined (single series)
  const width = 520;
  const height = 150;
  const max = Math.max(0, ...data.flatMap((d) => [d.a ?? 0, d.b ?? 0]));
  const y = scale(max, height);
  const group = width / Math.max(1, data.length);
  return (
    <figure style={{ margin: 0 }}>
      <figcaption><strong>{title}</strong></figcaption>
      {data.length === 0 ? (
        <p className="muted">No data yet.</p>
      ) : (
        <svg className="chart" viewBox={`0 0 ${width} ${height + 40}`} role="img" aria-label={title} width="100%">
          {data.map((d, i) => {
            const x = i * group + group * 0.12;
            const w = (group * 0.76) / (d.b === undefined ? 1 : 2);
            return (
              <g key={d.label}>
                <rect className="bar-a" x={x} y={height - y(d.a ?? 0)} width={w} height={y(d.a ?? 0)}>
                  <title>{`${seriesA}: ${format(d.a ?? 0)}`}</title>
                </rect>
                {d.b !== undefined && (
                  <rect className="bar-b" x={x + w} y={height - y(d.b ?? 0)} width={w} height={y(d.b ?? 0)}>
                    <title>{`${seriesB}: ${format(d.b ?? 0)}`}</title>
                  </rect>
                )}
                <text x={x} y={height + 14}>{String(d.label).slice(0, 14)}</text>
                <text x={x} y={height + 28}>{format(d.a ?? 0)}</text>
              </g>
            );
          })}
        </svg>
      )}
      <p className="muted">
        <span className="chip">■ {seriesA}</span>{" "}
        {seriesB && <span className="chip">■ {seriesB}</span>}
      </p>
    </figure>
  );
}

export function Series({ title, points, seriesA, seriesB, format = (v) => v.toFixed(5) }) {
  // points: [{a, b}] per request; two polylines (estimated vs measured), never merged
  const width = 520;
  const height = 140;
  const max = Math.max(0, ...points.flatMap((p) => [p.a ?? 0, p.b ?? 0]));
  const y = scale(max, height - 10);
  const step = width / Math.max(1, points.length - 1);
  const line = (key) =>
    points.map((p, i) => `${(i * step).toFixed(1)},${(height - y(p[key] ?? 0)).toFixed(1)}`).join(" ");
  return (
    <figure style={{ margin: 0 }}>
      <figcaption><strong>{title}</strong></figcaption>
      {points.length === 0 ? (
        <p className="muted">No data yet.</p>
      ) : (
        <svg className="chart" viewBox={`0 0 ${width} ${height + 20}`} role="img" aria-label={title} width="100%">
          <polyline fill="none" stroke="var(--accent)" strokeWidth="2" points={line("a")} />
          <polyline fill="none" stroke="var(--warn)" strokeWidth="2" strokeDasharray="5 3" points={line("b")} />
          <text x="0" y={height + 14}>max {format(max)}</text>
        </svg>
      )}
      <p className="muted">
        <span className="chip">— {seriesA}</span> <span className="chip">╌ {seriesB}</span>
      </p>
    </figure>
  );
}
