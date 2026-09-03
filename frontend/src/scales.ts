/** Colour scales for the choropleth. One place, so the map fill and the legend
 *  can never disagree about what a colour means. */

export type Metric = 'coverage' | 'support'

export interface Bin {
  /** Inclusive lower bound. Bins are listed ascending; a value falls in the
   *  last bin whose `min` it meets. */
  min: number
  color: string
  label: string
}

export const NO_DATA_COLOR = '#f4f4f5'

/** Sequential. Coverage is doors knocked / census dwellings, so it can exceed
 *  100% where a building holds more units than the census counted. */
export const COVERAGE_BINS: Bin[] = [
  { min: -Infinity, color: '#eff6ff', label: 'Under 10%' },
  { min: 10, color: '#bfdbfe', label: '10 – 25%' },
  { min: 25, color: '#60a5fa', label: '25 – 50%' },
  { min: 50, color: '#2563eb', label: '50 – 75%' },
  { min: 75, color: '#1e3a8a', label: '75% and over' },
]

/** Diverging around 3 (Undecided). Most doors that answer are undecided, so
 *  nearly every DA averages within half a point of 3. The bins are narrow near
 *  the centre to show that lean, and the colours are deliberately muted: a
 *  DA at 2.9 is not an opposing DA, it is an undecided one with a slight tilt. */
export const SUPPORT_BINS: Bin[] = [
  { min: -Infinity, color: '#d98080', label: 'Opposing (under 2.5)' },
  { min: 2.5, color: '#f0bfb0', label: 'Leaning against (2.5 – 2.9)' },
  { min: 2.9, color: '#d4d4d8', label: 'Undecided (2.9 – 3.1)' },
  { min: 3.1, color: '#cfe3c0', label: 'Leaning for (3.1 – 3.5)' },
  { min: 3.5, color: '#a3cf96', label: 'Supportive (3.5 – 4)' },
  { min: 4, color: '#5f9e6e', label: 'Strongly supportive (4 and over)' },
]

export const SCALES: Record<Metric, { title: string; note: string; bins: Bin[] }> = {
  coverage: {
    title: 'Coverage',
    note: 'Doors knocked as a share of census dwellings',
    bins: COVERAGE_BINS,
  },
  support: {
    title: 'Support',
    note: 'Average support level (1–5) among doors that answered',
    bins: SUPPORT_BINS,
  },
}

export function colorFor(metric: Metric, value: number | null | undefined): string {
  if (value === null || value === undefined) return NO_DATA_COLOR
  const bins = SCALES[metric].bins
  let color = bins[0].color
  for (const bin of bins) {
    if (value >= bin.min) color = bin.color
  }
  return color
}
