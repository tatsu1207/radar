'use client';

import { useEffect, useState, useRef } from 'react';
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
  const mapRef = useRef<any>(null);
  const mapId = 'resistome-map-container';
  const [selectedDate, setSelectedDate] = useState<string>('all');

  // Get unique dates
  const dates = Array.from(new Set(geo.map((g) => g.collection_date?.split(' ')[0]).filter(Boolean) as string[])).sort();

  // Filter samples by selected date
  const filteredGeo = selectedDate === 'all' ? geo : geo.filter((g) => g.collection_date?.startsWith(selectedDate));

  useEffect(() => {
    if (filteredGeo.length === 0) return;

    let map: any = null;

    (async () => {
      const L = (await import('leaflet')).default;

      const container = document.getElementById(mapId);
      if (!container) return;

      // Clean up existing map
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }

      const lats = geo.map((g) => g.latitude);
      const lons = geo.map((g) => g.longitude);
      const centerLat = lats.reduce((a, b) => a + b, 0) / lats.length;
      const centerLon = lons.reduce((a, b) => a + b, 0) / lons.length;

      map = L.map(mapId).setView([centerLat, centerLon], 7);
      mapRef.current = map;

      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 19,
      }).addTo(map);

      // Group filtered samples by location for pie-chart-like markers
      const locGroups: Record<string, GeoSample[]> = {};
      for (const s of filteredGeo) {
        const key = `${s.latitude},${s.longitude}`;
        if (!locGroups[key]) locGroups[key] = [];
        locGroups[key].push(s);
      }

      for (const [, samples] of Object.entries(locGroups)) {
        const s0 = samples[0];
        const totalClasses = new Set(samples.flatMap((s) => s.drug_classes));
        const mdrCount = samples.filter((s) => s.mdr_flag).length;
        const worstRank = samples.reduce((worst, s) => {
          const r = s.hazard_rank;
          if (!r) return worst;
          if (!worst) return r;
          const rn = r === 'NG' ? 99 : parseInt(r.replace('R', ''), 10);
          const wn = worst === 'NG' ? 99 : parseInt(worst.replace('R', ''), 10);
          return rn < wn ? r : worst;
        }, null as string | null);

        const radius = Math.max(8, Math.min(20, 6 + samples.length * 4));
        const color = rankColor(worstRank);

        const marker = L.circleMarker([s0.latitude, s0.longitude], {
          radius,
          fillColor: color,
          color: mdrCount > 0 ? '#FCD34D' : '#374151',
          weight: mdrCount > 0 ? 2.5 : 1,
          fillOpacity: 0.85,
        }).addTo(map);

        // Label with count
        if (samples.length > 1) {
          const icon = L.divIcon({
            html: `<div style="color:white;font-size:10px;font-weight:bold;text-align:center;line-height:${radius * 2}px;">${samples.length}</div>`,
            iconSize: [radius * 2, radius * 2],
            className: '',
          });
          L.marker([s0.latitude, s0.longitude], { icon, interactive: false }).addTo(map);
        }

        const sampleList = samples.map((s) =>
          `<div style="margin:2px 0;"><strong>${s.sample_name}</strong> ${s.hazard_rank || ''} ${s.mdr_flag ? '<span style="color:#ea580c;">MDR</span>' : ''} — ${s.drug_classes.join(', ')}</div>`
        ).join('');

        marker.bindPopup(`
          <div style="font-size:11px;max-width:300px;">
            <p style="font-weight:bold;font-size:13px;margin:0 0 6px 0;">${s0.location}</p>
            <p style="margin:2px 0;color:#888;">${samples.length} sample(s), ${totalClasses.size} drug classes, ${mdrCount} MDR</p>
            <div style="max-height:150px;overflow-y:auto;margin-top:6px;border-top:1px solid #ddd;padding-top:4px;">
              ${sampleList}
            </div>
          </div>
        `);

        marker.bindTooltip(`${s0.location} (${samples.length})`, { direction: 'top', offset: [0, -radius] });
      }
    })();

    return () => {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, [filteredGeo, selectedDate]);

  return (
    <div className="space-y-3">
      {/* Time filter */}
      {dates.length > 1 && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-400">Time filter:</span>
          <button onClick={() => setSelectedDate('all')} className={`px-2 py-1 rounded text-xs ${selectedDate === 'all' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
            All dates
          </button>
          {dates.map((d) => (
            <button key={d} onClick={() => setSelectedDate(d)} className={`px-2 py-1 rounded text-xs ${selectedDate === d ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
              {d}
            </button>
          ))}
        </div>
      )}

      <div id={mapId} style={{ height: '600px', maxWidth: '450px' }} className="rounded-lg overflow-hidden border border-gray-700 bg-gray-900" />

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-4 text-xs text-gray-400">
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full" style={{ background: '#DC2626' }} /> Critical (R1-R3)</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full" style={{ background: '#EA580C' }} /> High (R4-R5)</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full" style={{ background: '#D97706' }} /> Medium (R6-R10)</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full" style={{ background: '#16A34A' }} /> Low (R11-R12)</span>
        <span className="flex items-center gap-1"><span className="w-4 h-4 rounded-full border-2 border-yellow-400" style={{ background: 'transparent' }} /> MDR</span>
        <span className="text-gray-600">| Marker size = sample count at location</span>
      </div>

      {/* Location summary */}
      {locations.length > 0 && (
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
      )}
    </div>
  );
}
