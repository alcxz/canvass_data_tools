import { useEffect, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { DASummary } from './types'
import { colorFor, type Metric } from './scales'

interface Props {
  summary: DASummary[]
  metric: Metric
  selected: string | null
  onSelect: (dauid: string) => void
}

/** Free vector basemap from OpenFreeMap -- no API key, no account, no billing.
 *  (CARTO's keyless raster tiles now render an "API KEY REQUIRED" watermark.)
 *  Attribution is carried by the style itself and rendered by MapLibre. */
const BASEMAP = 'https://tiles.openfreemap.org/styles/positron'

/** Where the DA layers slot into the basemap's own layer stack.
 *
 *  The fill goes beneath the first road layer, so streets draw on top of the
 *  choropleth at full strength and stay easy to follow. The outline goes just
 *  beneath the first symbol (text) layer, so DA boundaries sit above the streets
 *  but street and place names remain legible above everything. */
function insertionPoints(map: maplibregl.Map): { roads?: string; labels?: string } {
  const layers = map.getStyle().layers
  const roads = layers.find((l) => /^(tunnel|highway|road|railway|aeroway)/.test(l.id))?.id
  const labels = layers.find((l) => l.type === 'symbol')?.id
  return { roads: roads ?? labels, labels }
}

export function DAMap({ summary, metric, selected, onSelect }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  // React state rather than a ref: the paint effects below must re-run once the
  // layers exist, and only a state change can trigger that. With a ref, whichever
  // of the summary fetch and the map load finished last would paint with stale
  // data (the load handler captured the empty initial summary).
  const [ready, setReady] = useState(false)

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

      const { roads, labels } = insertionPoints(map.current!)
      map.current!.addLayer({
        id: 'da-fill',
        type: 'fill',
        source: 'das',
        paint: {
          'fill-color': ['coalesce', ['feature-state', 'color'], '#e4e4e7'],
          'fill-opacity': 0.65,
        },
      }, roads)
      map.current!.addLayer({
        id: 'da-outline',
        type: 'line',
        source: 'das',
        paint: {
          'line-color': ['case', ['boolean', ['feature-state', 'selected'], false], '#0f172a', '#475569'],
          // Line widths are in screen pixels, so a fixed width looks thinner and
          // thinner as the streets around it grow. Scale with zoom so the DA
          // boundary keeps its weight relative to the basemap at every level.
          'line-width': [
            'interpolate', ['linear'], ['zoom'],
            11, ['case', ['boolean', ['feature-state', 'selected'], false], 2.5, 0.8],
            14, ['case', ['boolean', ['feature-state', 'selected'], false], 3.5, 1.6],
            17, ['case', ['boolean', ['feature-state', 'selected'], false], 5, 3],
          ],
        },
      }, labels)

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

      setReady(true)
    })

    return () => {
      map.current?.remove()
      map.current = null
      setReady(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!map.current || !ready) return

    for (const da of summary) {
      const value = metric === 'coverage' ? da.coverage_pct : da.avg_support
      map.current.setFeatureState(
        { source: 'das', id: da.dauid },
        { color: colorFor(metric, value) },
      )
    }
  }, [ready, summary, metric])

  useEffect(() => {
    if (!map.current || !ready) return
    for (const da of summary) {
      map.current.setFeatureState(
        { source: 'das', id: da.dauid },
        { selected: da.dauid === selected },
      )
    }
  }, [ready, selected, summary])

  return <div ref={container} style={{ position: 'absolute', inset: 0 }} />
}
