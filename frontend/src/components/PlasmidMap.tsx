'use client';

import { useEffect, useRef, useState, useMemo } from 'react';
import { Download } from 'lucide-react';

interface Feature {
  type: 'arg' | 'virulence' | 'mobile_element' | 'prophage' | 'relaxase' | 'orit' | 't4ss' | 'replicon';
  name: string;
  label: string;
  family: string;
  start: number;
  end: number;
}

interface PlasmidMapData {
  plasmid_id: string;
  contig: string;
  size: number;
  replicon: string;
  mob_type: string;
  mpf_type: string;
  orit_type: string;
  predicted_mobility: string;
  features: Feature[];
}

interface PlasmidMapProps {
  data: PlasmidMapData;
}

const LEGEND_COLORS: Record<string, string> = {
  arg:            '#EF4444',
  virulence:      '#FB923C',
  mobile_element: '#F59E0B',
  prophage:       '#8B5CF6',
  relaxase:       '#06B6D4',
  orit:           '#EC4899',
  t4ss:           '#10B981',
  replicon:       '#6366F1',
};

const LEGEND_LABELS: Record<string, string> = {
  arg:            'Resistance Gene',
  virulence:      'Virulence Factor',
  mobile_element: 'IS Element',
  prophage:       'Prophage',
  relaxase:       'Relaxase',
  orit:           'oriT',
  t4ss:           'T4SS / MPF',
  replicon:       'Replicon',
};

function buildCGViewJSON(data: PlasmidMapData) {
  // Build legend items for feature types present
  const presentTypes = Array.from(new Set(data.features.map((f) => f.type)));
  const legendItems = presentTypes.map((type) => ({
    name: LEGEND_LABELS[type] || type,
    swatchColor: LEGEND_COLORS[type] || '#888',
    decoration: type === 'arg' ? 'arrow' : 'arc',
  }));

  // Assign features to tracks based on type
  // Inner tracks: ARGs, relaxase/oriT
  // Outer tracks: IS elements, T4SS, replicons, prophages
  const trackOrder = ['arg', 'virulence', 'relaxase', 'orit', 'mobile_element', 't4ss', 'replicon', 'prophage'];
  const trackPosition: Record<string, string> = {
    arg: 'inside',
    virulence: 'inside',
    relaxase: 'inside',
    orit: 'inside',
    mobile_element: 'outside',
    t4ss: 'outside',
    replicon: 'outside',
    prophage: 'outside',
  };

  // Group features by type for separate tracks
  const featuresByType: Record<string, Feature[]> = {};
  for (const f of data.features) {
    if (!featuresByType[f.type]) featuresByType[f.type] = [];
    featuresByType[f.type].push(f);
  }

  // Build CGView features array
  const cgFeatures = data.features.map((f, i) => ({
    name: f.type === 'arg' ? f.name
      : f.type === 'mobile_element' ? f.label
      : f.type === 'orit' ? 'oriT'
      : f.name,
    type: f.type,
    start: f.start,
    stop: f.end,
    strand: 1,
    legend: LEGEND_LABELS[f.type] || f.type,
    source: f.type,
    tags: [f.type],
    favorite: f.type === 'arg',
    meta: {
      drug_class: f.type === 'arg' ? f.label : undefined,
      family: f.family || undefined,
    },
  }));

  // Build tracks — one per feature type present, in order
  const tracks = trackOrder
    .filter((type) => featuresByType[type])
    .map((type) => ({
      name: LEGEND_LABELS[type] || type,
      position: trackPosition[type] || 'outside',
      separateFeaturesBy: 'none',
      dataType: 'feature',
      dataMethod: 'source',
      dataKeys: type,
      drawOrder: 'score',
    }));

  // Mobility label
  const mobilityLabel = data.predicted_mobility && data.predicted_mobility !== '-'
    ? data.predicted_mobility.charAt(0).toUpperCase() + data.predicted_mobility.slice(1)
    : '';

  return {
    cgview: {
      version: '1.8.0',
      name: `${data.plasmid_id} (${data.contig})`,
      format: 'circular',
      sequence: {
        length: data.size,
        name: data.plasmid_id,
      },
      settings: {
        backgroundColor: '#FFFFFF',
        backgroundColorAlternate: '#F9FAFB',
      },
      backbone: {
        color: '#D1D5DB',
        colorAlternate: '#D1D5DB',
        thickness: 12,
      },
      ruler: {
        font: 'monospace, plain, 9',
        color: '#374151',
      },
      annotation: {
        font: 'sans-serif, bold, 12',
        color: '#000000',
        onlyDrawFavorites: false,
        visible: true,
        labelLineColor: '#6B7280',
        labelLineWidth: 1,
      },
      legend: {
        visible: true,
        position: 'bottom-right',
        textAlignment: 'left',
        defaultFont: 'sans-serif, plain, 11',
        backgroundColor: 'rgba(255,255,255,0.9)',
        fontColor: '#1F2937',
        items: legendItems,
      },
      captions: [
        {
          name: data.plasmid_id,
          position: 'middle-center',
          font: 'sans-serif, bold, 16',
          fontColor: '#111827',
        },
        ...(data.replicon !== '-' ? [{
          name: data.replicon,
          position: 'middle-center',
          font: 'sans-serif, plain, 10',
          fontColor: '#6B7280',
        }] : []),
        ...(mobilityLabel ? [{
          name: mobilityLabel,
          position: 'top-center',
          font: 'sans-serif, bold, 13',
          fontColor: data.predicted_mobility === 'conjugative' ? '#DC2626'
            : data.predicted_mobility === 'mobilizable' ? '#D97706'
            : '#6B7280',
        }] : []),
      ],
      tracks,
      features: cgFeatures,
    },
  };
}

export default function PlasmidMap({ data }: PlasmidMapProps) {
  const containerId = useMemo(() => `cgv-${data.contig.replace(/[^a-zA-Z0-9]/g, '-')}`, [data.contig]);
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<any>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cgJSON = useMemo(() => buildCGViewJSON(data), [data]);

  useEffect(() => {
    if (!containerRef.current) return;

    let cancelled = false;

    (async () => {
      try {
        const CGView = await import('cgview');

        // If cleanup ran while we were awaiting the import, bail out
        if (cancelled || !containerRef.current) return;

        // Clear any leftover content from a previous render
        containerRef.current.innerHTML = '';

        const viewer = new CGView.Viewer(`#${containerId}`, {
          height: 500,
          width: containerRef.current.clientWidth || 700,
        });

        viewer.io.loadJSON(cgJSON);
        viewer.draw();
        viewerRef.current = viewer;
        setLoaded(true);
      } catch (err) {
        if (!cancelled) {
          console.error('CGView error:', err);
          setError(err instanceof Error ? err.message : 'Failed to load CGView');
        }
      }
    })();

    return () => {
      cancelled = true;
      if (viewerRef.current && typeof viewerRef.current.destroy === 'function') {
        viewerRef.current.destroy();
      }
      if (containerRef.current) {
        containerRef.current.innerHTML = '';
      }
      viewerRef.current = null;
    };
  }, [cgJSON, containerId]);

  // Resize handler
  useEffect(() => {
    if (!viewerRef.current || !containerRef.current) return;
    const ro = new ResizeObserver(() => {
      if (viewerRef.current && containerRef.current) {
        viewerRef.current.resize(containerRef.current.clientWidth, 500);
      }
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, [loaded]);

  const handleExportPNG = () => {
    if (!viewerRef.current) return;
    try {
      viewerRef.current.io.downloadImage(2000, 2000, `${data.plasmid_id}_map.png`);
    } catch (e) {
      console.error('PNG export failed', e);
      // Fallback: try SVG
      try {
        viewerRef.current.io.downloadSVG(`${data.plasmid_id}_map.svg`);
      } catch (e2) {
        console.error('SVG export also failed', e2);
      }
    }
  };

  const mobilityBadge = data.predicted_mobility && data.predicted_mobility !== '-' ? (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
      data.predicted_mobility === 'conjugative' ? 'bg-red-600/20 text-red-300 border border-red-600/30'
      : data.predicted_mobility === 'mobilizable' ? 'bg-yellow-600/20 text-yellow-300 border border-yellow-600/30'
      : 'bg-gray-600/20 text-gray-300 border border-gray-600/30'
    }`}>{data.predicted_mobility}</span>
  ) : null;

  const formatBp = (bp: number) => bp >= 1e6 ? `${(bp/1e6).toFixed(2)} Mb` : bp >= 1e3 ? `${(bp/1e3).toFixed(1)} kb` : `${bp} bp`;

  // Feature summary counts
  const typeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const f of data.features) {
      counts[f.type] = (counts[f.type] || 0) + 1;
    }
    return counts;
  }, [data.features]);

  return (
    <div className="card">
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-gray-100 flex items-center gap-3">
            {data.plasmid_id}
            <span className="text-sm font-normal text-gray-400">({data.contig})</span>
            {mobilityBadge}
          </h3>
          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1 text-xs text-gray-400">
            <span>{formatBp(data.size)}</span>
            {data.replicon !== '-' && <span>Replicon: <span className="text-gray-300">{data.replicon}</span></span>}
            {data.mob_type !== '-' && <span>MOB: <span className="text-gray-300">{data.mob_type}</span></span>}
            {data.mpf_type !== '-' && (
              <span>MPF: <span className="text-cyan-400">
                {Array.from(new Set(data.mpf_type.split(','))).join(', ')}
              </span></span>
            )}
          </div>
          {/* Feature counts */}
          <div className="flex flex-wrap gap-3 mt-2">
            {Object.entries(typeCounts).map(([type, count]) => (
              <span key={type} className="inline-flex items-center gap-1 text-xs">
                <span className="w-2 h-2 rounded-sm" style={{ backgroundColor: LEGEND_COLORS[type] || '#888' }} />
                <span className="text-gray-400">{count} {LEGEND_LABELS[type] || type}</span>
              </span>
            ))}
          </div>
        </div>
        <button onClick={handleExportPNG} disabled={!loaded}
          className="btn-secondary flex items-center gap-2 text-xs">
          <Download className="w-3.5 h-3.5" />
          Export PNG
        </button>
      </div>

      {/* CGView container */}
      {error ? (
        <div className="text-center py-8 text-red-400 text-sm">{error}</div>
      ) : (
        <div id={containerId} ref={containerRef} className="w-full rounded-lg overflow-hidden border border-gray-800"
          style={{ minHeight: 500 }} />
      )}

      {/* Feature table */}
      <details className="mt-4">
        <summary className="text-sm text-gray-400 cursor-pointer hover:text-gray-200">
          Feature details ({data.features.length} features)
        </summary>
        <div className="mt-2 overflow-x-auto max-h-[400px] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-gray-900">
              <tr className="border-b border-gray-800">
                <th className="text-left py-1.5 px-2 text-gray-400 font-medium">Type</th>
                <th className="text-left py-1.5 px-2 text-gray-400 font-medium">Name</th>
                <th className="text-left py-1.5 px-2 text-gray-400 font-medium">Details</th>
                <th className="text-right py-1.5 px-2 text-gray-400 font-medium">Position</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/50">
              {data.features.map((f, i) => (
                <tr key={i} className="hover:bg-gray-800/30">
                  <td className="py-1.5 px-2">
                    <span className="inline-flex items-center gap-1">
                      <span className="w-2 h-2 rounded-sm" style={{ backgroundColor: LEGEND_COLORS[f.type] || '#888' }} />
                      <span className="text-gray-400">{LEGEND_LABELS[f.type] || f.type}</span>
                    </span>
                  </td>
                  <td className="py-1.5 px-2 font-medium text-gray-200">
                    {f.type === 'mobile_element' ? f.label : f.type === 'orit' ? 'oriT' : f.name}
                  </td>
                  <td className="py-1.5 px-2 text-gray-400">
                    {f.type === 'arg' ? f.label : f.family || f.label}
                  </td>
                  <td className="py-1.5 px-2 text-right text-gray-500 font-mono">
                    {f.start.toLocaleString()}-{f.end.toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
