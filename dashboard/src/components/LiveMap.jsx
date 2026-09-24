import { useEffect } from 'react'
import { MapContainer, TileLayer, WMSTileLayer, LayersControl, LayerGroup, CircleMarker, Circle, Polyline, Popup, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'

// NASA GIBS (Global Imagery Browse Services): free, no API key. https://nasa-gibs.github.io/gibs-api-docs/
const GIBS_WMS = 'https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi'
const FALLBACK_LAT = Number(import.meta.env.VITE_MAP_LATITUDE) || 20.5937
const FALLBACK_LON = Number(import.meta.env.VITE_MAP_LONGITUDE) || 78.9629

const utcDate = (offsetDays = 0) => new Date(Date.now() + offsetDays * 86400000).toISOString().slice(0, 10)

// FIRMS confidence: VIIRS reports l / n / h, MODIS reports 0-100.
function tier(conf) {
  const s = String(conf ?? '').toLowerCase()
  if (s === 'h' || s === 'high') return 'high'
  if (s === 'l' || s === 'low') return 'low'
  if (s === 'n' || s === 'nominal') return 'nominal'
  const n = Number(s)
  if (!Number.isNaN(n) && s !== '') return n >= 80 ? 'high' : n >= 30 ? 'nominal' : 'low'
  return 'nominal'
}
const COLORS = { high: '#ff3b30', nominal: '#ff9f0a', low: '#ffd60a' }

// Point `km` away from (lat, lon) along a compass bearing.
function destination(lat, lon, bearingDeg, km) {
  const r = Math.PI / 180, d = km / 6371.0088, b = bearingDeg * r, la = lat * r, lo = lon * r
  const la2 = Math.asin(Math.sin(la) * Math.cos(d) + Math.cos(la) * Math.sin(d) * Math.cos(b))
  const lo2 = lo + Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(la), Math.cos(d) - Math.sin(la) * Math.sin(la2))
  return [la2 / r, lo2 / r]
}

function Recenter({ center, zoom }) {
  const map = useMap()
  useEffect(() => { map.setView(center, zoom) }, [center[0], center[1], zoom]) // eslint-disable-line react-hooks/exhaustive-deps
  return null
}

/**
 * Live operational map. Real geodata only:
 *  - NASA GIBS imagery + VIIRS thermal-anomaly tiles (keyless, straight from NASA)
 *  - NASA FIRMS hotspots returned by the backend (needs FIREGUARD_FIRMS_MAP_KEY on the server)
 *  - the detector's fire event, if any
 *  - a wind vector from the live weather reading
 * It never invents a fire, hotspot or forecast perimeter.
 */
export default function LiveMap({ location, radiusKm, fire, satelliteFires = [], environment, forecastMinutes = 0 }) {
  const hasSite = location?.latitude != null && location?.longitude != null
  const hasFire = fire?.latitude != null && fire?.longitude != null
  const first = satelliteFires.find(f => Number.isFinite(Number(f.latitude)))
  const center = hasFire ? [fire.latitude, fire.longitude]
    : hasSite ? [location.latitude, location.longitude]
    : first ? [Number(first.latitude), Number(first.longitude)]
    : [FALLBACK_LAT, FALLBACK_LON]
  const zoom = hasFire ? 12 : hasSite ? (radiusKm >= 150 ? 7 : radiusKm >= 60 ? 8 : 10) : first ? 8 : 5

  // Wind is reported as the bearing it blows FROM; the vector points where it blows TO.
  const windTo = environment?.wind_direction != null ? (Number(environment.wind_direction) + 180) % 360 : null
  const windKm = 2 + Math.min(Number(environment?.wind_speed) || 0, 90) / 15 // visual scale only
  const windOrigin = hasFire ? [fire.latitude, fire.longitude] : hasSite ? [location.latitude, location.longitude] : null
  const windLine = windOrigin && windTo != null ? [windOrigin, destination(windOrigin[0], windOrigin[1], windTo, windKm)] : null

  // Orientation aid only: wind-speed-scaled radius. Not a validated fire-perimeter forecast.
  const forecastRadiusM = forecastMinutes > 0 && hasFire ? Math.max(80, ((Number(environment?.wind_speed) || 5) * 1000 / 60) * forecastMinutes * 0.6) : null

  return (
    <div className="livemap">
      <MapContainer center={center} zoom={zoom} scrollWheelZoom style={{ height: '100%', width: '100%' }}>
        <Recenter center={center} zoom={zoom} />
        <LayersControl position="topright">
          <LayersControl.BaseLayer checked name="NASA VIIRS true colour (yesterday)">
            <WMSTileLayer url={GIBS_WMS} layers="VIIRS_SNPP_CorrectedReflectance_TrueColor" format="image/jpeg" transparent={false} time={utcDate(-1)} maxZoom={9}
              attribution='Imagery: <a href="https://earthdata.nasa.gov/gibs">NASA GIBS</a> / VIIRS' />
          </LayersControl.BaseLayer>
          <LayersControl.BaseLayer name="OpenStreetMap">
            <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={19} attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' />
          </LayersControl.BaseLayer>

          <LayersControl.Overlay checked name="NASA thermal anomalies (VIIRS NOAA-20, GIBS)">
            <WMSTileLayer url={GIBS_WMS} layers="VIIRS_NOAA20_Thermal_Anomalies_375m_All" format="image/png" transparent time={utcDate(0)} maxZoom={12}
              attribution='Thermal anomalies: <a href="https://firms.modaps.eosdis.nasa.gov/">NASA FIRMS</a>' />
          </LayersControl.Overlay>

          <LayersControl.Overlay checked name="NASA FIRMS hotspots (API)">
            <LayerGroup>
              {satelliteFires.slice(0, 500).map((f, i) => {
                const la = Number(f.latitude), lo = Number(f.longitude)
                if (!Number.isFinite(la) || !Number.isFinite(lo)) return null
                const t = tier(f.confidence)
                return (
                  <CircleMarker key={f.event_id || `${la}-${lo}-${i}`} center={[la, lo]} radius={6}
                    pathOptions={{ color: '#3a0d05', weight: 1, fillColor: COLORS[t], fillOpacity: 0.9 }}>
                    <Popup>
                      <b>NASA FIRMS hotspot</b><br />
                      {f.satellite || 'Satellite'} · {f.instrument || ''} · {f.acq_date} {String(f.acq_time || '').padStart(4, '0')} UTC<br />
                      {f.age_minutes != null && <>Observed {Math.round(f.age_minutes)} min ago<br /></>}
                      Confidence: {f.confidence ?? '—'} ({t}) · FRP: {f.frp ?? '—'} MW<br />
                      {f.distance_km != null && <>Distance from site: {f.distance_km} km<br /></>}
                      <small>{f.firms_source}</small>
                    </Popup>
                  </CircleMarker>
                )
              })}
            </LayerGroup>
          </LayersControl.Overlay>
        </LayersControl>

        {hasSite && (
          <>
            <CircleMarker center={[location.latitude, location.longitude]} radius={5} pathOptions={{ color: '#0b2b3a', weight: 2, fillColor: '#4fc3f7', fillOpacity: 1 }}>
              <Popup><b>Monitoring site</b><br />{location.latitude.toFixed(4)}, {location.longitude.toFixed(4)}</Popup>
            </CircleMarker>
            {radiusKm > 0 && <Circle center={[location.latitude, location.longitude]} radius={radiusKm * 1000} interactive={false} pathOptions={{ color: '#4fc3f7', weight: 1, dashArray: '6 6', fillOpacity: 0.02, interactive: false }} />}
          </>
        )}

        {hasFire && (
          <>
            <CircleMarker center={[fire.latitude, fire.longitude]} radius={9} pathOptions={{ color: '#fff', weight: 2, fillColor: '#ff3b30', fillOpacity: 1 }}>
              <Popup><b>{fire.event_id}</b><br />Detector confidence: {Math.round((fire.confidence || 0) * 100)}%<br />Risk: {Math.round(fire.risk_score || 0)}/100</Popup>
            </CircleMarker>
            <Circle center={[fire.latitude, fire.longitude]} radius={Math.max(120, Math.sqrt(fire.visual_area_proxy || 0) * 8)} pathOptions={{ color: '#ff6d3a', weight: 1, fillColor: '#ff6d3a', fillOpacity: 0.14, interactive: false }} />
          </>
        )}
        {forecastRadiusM != null && <Circle center={[fire.latitude, fire.longitude]} radius={forecastRadiusM} pathOptions={{ color: '#ffb347', weight: 1, dashArray: '4 4', fillColor: '#ffb347', fillOpacity: 0.08, interactive: false }} />}
        {windLine && <Polyline positions={windLine} pathOptions={{ color: '#8db0bc', weight: 3, dashArray: '2 6', interactive: false }} />}
        {windLine && <CircleMarker center={windLine[1]} radius={4} pathOptions={{ color: '#8db0bc', fillColor: '#8db0bc', fillOpacity: 1 }}><Popup>Wind blowing toward {Math.round(windTo)}° at {environment.wind_speed ?? '—'} km/h (live reading; line length is a visual scale)</Popup></CircleMarker>}
      </MapContainer>

      <div className="map-legend">
        <b>FIRMS hotspots: {satelliteFires.length}</b>
        {Object.entries(COLORS).map(([k, c]) => <span key={k}><i style={{ background: c }} />{k}</span>)}
        <span><i style={{ background: '#4fc3f7' }} />site</span>
      </div>
      {!hasSite && !hasFire && !first && (
        <div className="map-note">Set FIREGUARD_LATITUDE / FIREGUARD_LONGITUDE on the API server to centre the map and scope satellite queries to your site.</div>
      )}
    </div>
  )
}
