'use client';

import { useState } from 'react';
import type { HeatmapData } from '@/lib/api';

interface HeatmapProps {
  data: HeatmapData;
}

function getColor(value: number, max: number): string {
  if (value === 0) return 'bg-gray-800';
  const intensity = Math.min(value / Math.max(max, 1), 1);
  if (intensity < 0.25) return 'bg-blue-900/60';
  if (intensity < 0.5) return 'bg-blue-700/70';
  if (intensity < 0.75) return 'bg-orange-600/70';
  return 'bg-red-600/80';
}

export default function Heatmap({ data }: HeatmapProps) {
  const [tooltip, setTooltip] = useState<{ sample: string; drugClass: string; count: number; x: number; y: number } | null>(null);

  const maxVal = Math.max(...data.matrix.flat(), 1);

  if (data.samples.length === 0 || data.drug_classes.length === 0) {
    return (
      <div className="text-center py-12 text-gray-500">
        No heatmap data available. Run analyses on samples first.
      </div>
    );
  }

  return (
    <div className="relative">
      <div className="overflow-x-auto">
        <div className="inline-block min-w-full">
          {/* Column headers */}
          <div className="flex">
            <div className="w-32 flex-shrink-0" />
            {data.drug_classes.map((dc) => (
              <div
                key={dc}
                className="w-16 flex-shrink-0 text-center"
              >
                <span className="text-[10px] text-gray-400 writing-mode-vertical inline-block transform -rotate-45 origin-bottom-left whitespace-nowrap">
                  {dc}
                </span>
              </div>
            ))}
          </div>

          {/* Rows */}
          {data.samples.map((sample, rowIdx) => (
            <div key={sample} className="flex items-center">
              <div className="w-32 flex-shrink-0 text-right pr-3">
                <span className="text-xs text-gray-400 truncate block">{sample}</span>
              </div>
              {data.drug_classes.map((dc, colIdx) => {
                const value = data.matrix[rowIdx]?.[colIdx] ?? 0;
                return (
                  <div
                    key={dc}
                    className={`w-16 h-8 flex-shrink-0 border border-gray-900 ${getColor(value, maxVal)} cursor-pointer transition-all hover:ring-1 hover:ring-blue-400`}
                    onMouseEnter={(e) => {
                      const rect = e.currentTarget.getBoundingClientRect();
                      setTooltip({ sample, drugClass: dc, count: value, x: rect.left, y: rect.top });
                    }}
                    onMouseLeave={() => setTooltip(null)}
                  >
                    {value > 0 && (
                      <span className="flex items-center justify-center h-full text-[10px] text-gray-200 font-medium">
                        {value}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-4 justify-center">
        <span className="text-xs text-gray-500">Low</span>
        <div className="flex">
          <div className="w-8 h-4 bg-gray-800 border border-gray-700" />
          <div className="w-8 h-4 bg-blue-900/60 border border-gray-700" />
          <div className="w-8 h-4 bg-blue-700/70 border border-gray-700" />
          <div className="w-8 h-4 bg-orange-600/70 border border-gray-700" />
          <div className="w-8 h-4 bg-red-600/80 border border-gray-700" />
        </div>
        <span className="text-xs text-gray-500">High</span>
      </div>

      {/* Tooltip */}
      {tooltip && (
        <div
          className="fixed z-50 bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 shadow-xl pointer-events-none"
          style={{ left: tooltip.x + 20, top: tooltip.y - 10 }}
        >
          <p className="text-xs font-semibold text-gray-200">{tooltip.sample}</p>
          <p className="text-xs text-gray-400">{tooltip.drugClass}</p>
          <p className="text-xs text-blue-400">{tooltip.count} ARG(s)</p>
        </div>
      )}
    </div>
  );
}
