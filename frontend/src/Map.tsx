import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { DASummary } from './types'

type Metric = 'coverage' | 'support'

interface Props {
  summary: DASummary[]
  metric: Metric
  selected: string | null
  onSelect: (dauid: string) => void
}

/** Free raster basemap -- no Mapbox token and no billing account. */
const BASEMAP: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    carto: {
      type: 'raster',
      tiles: [
        'https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png',
        'https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png',
      ],
      tileSize: 256,
      attribution: '© OpenStreetMap contributors © CARTO',
    },
  },
  layers: [{ id: 'basemap', type: 'raster', source: 'carto' }],
}

export function DAMap({ summary, metric, selected, onSelect }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const loaded = useRef(false)

  useEffect(() => {
    if (!container.current || map.current) return

    map.current = new maplibregl.Map({
      container: container.current,
      style: BASEMAP,
      center: [-79.405, 43.665],
      zoom: 12.6,
    })
    map.current.addControl(new maplibregl.NavigationControl(), 'top-right')

    map.current.on('load', async () => {
      // The 161 DA polygons are a 112KB static asset, so they ship with the
      // frontend rather than living in PostGIS.
      const geojson = await fetch('/das.geojson').then((r) => r.json())
      map.current!.addSource('das', { type: 'geojson', data: geojson, promoteId: 'DAUID' })

      map.current!.addLayer({
        id: 'da-fill',
        type: 'fill',
        source: 'das',
        paint: {
          'fill-color': ['coalesce', ['feature-state', 'color'], '#e4e4e7'],
          'fill-opacity': 0.65,
        },
      })
      map.current!.addLayer({
        id: 'da-outline',
        type: 'line',
        source: 'das',
        paint: {
          'line-color': ['case', ['boolean', ['feature-state', 'selected'], false], '#0f172a', '#94a3b8'],
          'line-width': ['case', ['boolean', ['feature-state', 'selected'], false], 3, 0.7],
        },
      })

      map.current!.on('click', 'da-fill', (event) => {
        const dauid = event.features?.[0]?.properties?.DAUID
        if (dauid) onSelect(String(dauid))
      })
      map.current!.on('mouseenter', 'da-fill', () => {
        map.current!.getCanvas().style.cursor = 'pointer'
      })
      map.current!.on('mouseleave', 'da-fill', () => {
        map.current!.getCanvas().style.cursor = ''
      })

      loaded.current = true
      paint()
    })

    return () => {
      map.current?.remove()
      map.current = null
      loaded.current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function paint() {
    if (!map.current || !loaded.current) return

    for (const da of summary) {
      const value = metric === 'coverage' ? da.coverage_pct : da.avg_support
      map.current.setFeatureState(
        { source: 'das', id: da.dauid },
        { color: colorFor(metric, value) },
      )
    }
  }

  useEffect(paint, [summary, metric])

  useEffect(() => {
    if (!map.current || !loaded.current) return
    for (const da of summary) {
      map.current.setFeatureState(
        { source: 'das', id: da.dauid },
        { selected: da.dauid === selected },
      )
    }
  }, [selected, summary])

  return <div ref={container} style={{ position: 'absolute', inset: 0 }} />
}

function colorFor(metric: Metric, value: number | null): string {
  if (value === null || value === undefined) return '#f4f4f5'

  if (metric === 'coverage') {
    // Sequential. Coverage is doors knocked / census dwellings, so it can exceed
    // 100% where a building holds more units than the census counted.
    if (value >= 75) return '#1e3a8a'
    if (value >= 50) return '#2563eb'
    if (value >= 25) return '#60a5fa'
    if (value >= 10) return '#bfdbfe'
    return '#eff6ff'
  }

  // Diverging around 3 (Undecided).
  if (value >= 4.5) return '#15803d'
  if (value >= 3.75) return '#65a30d'
  if (value >= 3.25) return '#a1a1aa'
  if (value >= 2.5) return '#ea580c'
  return '#b91c1c'
}
