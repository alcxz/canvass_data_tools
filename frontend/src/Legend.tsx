import { NO_DATA_COLOR, SCALES, type Metric } from './scales'

/** Colour key for whichever metric the map is showing. Sits over the map so it
 *  reads next to the colours it explains. */
export function Legend({ metric }: { metric: Metric }) {
  const scale = SCALES[metric]
  return (
    <div className="legend" aria-label={`${scale.title} colour key`}>
      <div className="legend-title">{scale.title}</div>
      <div className="legend-note">{scale.note}</div>
      <ul>
        {scale.bins.map((bin) => (
          <li key={bin.label}>
            <span className="swatch" style={{ background: bin.color }} />
            {bin.label}
          </li>
        ))}
        <li>
          <span className="swatch" style={{ background: NO_DATA_COLOR }} />
          No data
        </li>
      </ul>
    </div>
  )
}
