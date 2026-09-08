'use client';

import { MapContainer, TileLayer, CircleMarker, Popup, Tooltip } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';

interface GeoSample {
  sample_name: string;
  sample_id: string;
  latitude: number;
  longitude: number;
  location: string;
  source: string;
  collection_date: string | null;
  drug_class_count: number;
  drug_classes: string[];
  hazard_rank: string | null;
  mdr_flag: boolean;
}

interface LocationStat {
  location: string;
  sample_count: number;
  mdr_count: number;
  top_drug_classes: [string, number][];
}

function rankColor(rank: string | null): string {
  if (!rank) return '#6B7280';
  if (['R1', 'R2', 'R3'].includes(rank)) return '#DC2626';
  if (['R4', 'R5'].includes(rank)) return '#EA580C';
  if (['R6', 'R7', 'R8', 'R9', 'R10'].includes(rank)) return '#D97706';
  if (rank === 'R11') return '#16A34A';
  return '#6B7280';
}

export default function ResistomeMapInner({ geo, locations }: { geo: GeoSample[]; locations: LocationStat[] }) {
  // Center on South Korea by default; adjust if data is elsewhere
  const lats = geo.map((g) => g.latitude);
  const lons = geo.map((g) => g.longitude);
  const centerLat = lats.reduce((a, b) => a + b, 0) / lats.length;
  const centerLon = lons.reduce((a, b) => a + b, 0) / lons.length;

  return (
    <div className="space-y-4">
      <div style={{ height: '450px' }} className="rounded-lg overflow-hidden border border-gray-700">
        <MapContainer center={[centerLat, centerLon]} zoom={7} style={{ height: '100%', width: '100%' }} scrollWheelZoom={true}>
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          />
          {geo.map((s) => (
            <CircleMarker
              key={s.sample_id}
              center={[s.latitude, s.longitude]}
              radius={s.mdr_flag ? 12 : 8}
              pathOptions={{
                fillColor: rankColor(s.hazard_rank),
                color: s.mdr_flag ? '#FCD34D' : '#374151',
                weight: s.mdr_flag ? 2 : 1,
                fillOpacity: 0.8,
              }}
            >
              <Tooltip direction="top" offset={[0, -8]}>
                <span className="text-xs font-medium">{s.sample_name}</span>
              </Tooltip>
              <Popup>
                <div className="text-xs space-y-1 min-w-[180px]">
                  <p className="font-bold text-sm">{s.sample_name}</p>
                  <p><span className="text-gray-500">Location:</span> {s.location}</p>
                  <p><span className="text-gray-500">Source:</span> {s.source}</p>
                  {s.collection_date && <p><span className="text-gray-500">Date:</span> {s.collection_date.split(' ')[0]}</p>}
                  <p><span className="text-gray-500">Hazard rank:</span> <strong>{s.hazard_rank || 'N/A'}</strong></p>
                  <p><span className="text-gray-500">Drug classes:</span> {s.drug_class_count} ({s.drug_classes.join(', ')})</p>
                  {s.mdr_flag && <p className="text-orange-600 font-bold">MDR</p>}
                </div>
              </Popup>
            </CircleMarker>
          ))}
        </MapContainer>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-4 text-xs text-gray-400">
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full" style={{ background: '#DC2626' }} /> Critical (R1-R3)</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full" style={{ background: '#EA580C' }} /> High (R4-R5)</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full" style={{ background: '#D97706' }} /> Medium (R6-R10)</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full" style={{ background: '#16A34A' }} /> Low (R11-R12)</span>
        <span className="flex items-center gap-1"><span className="w-4 h-4 rounded-full border-2 border-yellow-400" style={{ background: 'transparent' }} /> MDR (yellow ring)</span>
      </div>

      {/* Location summary */}
      {locations.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-gray-300 mb-2">Location Summary</h3>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="text-left px-2 py-1.5 text-gray-400">Location</th>
                <th className="text-center px-2 py-1.5 text-gray-400">Samples</th>
                <th className="text-center px-2 py-1.5 text-gray-400">MDR</th>
                <th className="text-left px-2 py-1.5 text-gray-400">Top Drug Classes</th>
              </tr>
            </thead>
            <tbody>
              {locations.map((loc) => (
                <tr key={loc.location} className="border-b border-gray-800/30">
                  <td className="px-2 py-1.5 text-gray-200 font-medium">{loc.location}</td>
                  <td className="px-2 py-1.5 text-center text-gray-300">{loc.sample_count}</td>
                  <td className="px-2 py-1.5 text-center">
                    {loc.mdr_count > 0 ? <span className="text-orange-400 font-bold">{loc.mdr_count}</span> : <span className="text-gray-600">0</span>}
                  </td>
                  <td className="px-2 py-1.5 text-gray-400">
                    {loc.top_drug_classes.slice(0, 5).map(([dc, count]) => (
                      <span key={dc} className="mr-2">{dc} <span className="text-gray-500">({count})</span></span>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
