'use client';

import StatusBadge from './StatusBadge';
import type { RiskScore } from '@/lib/api';

interface RadarChartProps {
  riskScore: RiskScore;
}

const tierColor: Record<string, string> = {
  Reserve: '#ef4444',
  Watch: '#eab308',
  Access: '#22c55e',
};

export default function RadarChartComponent({ riskScore }: RadarChartProps) {
  const rank = riskScore.hazard_rank || 'NG';
  const tier = riskScore.aware_tier;
  const color = tier ? tierColor[tier] || '#6b7280' : '#6b7280';

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-100">Hazard Rank</h3>
        <StatusBadge status={rank} type="hazard" />
      </div>

      <div className="flex flex-col items-center py-6">
        <p className="text-6xl font-bold" style={{ color }}>
          {rank}
        </p>
        {tier && (
          <p className="text-sm mt-2" style={{ color }}>
            {tier} Tier
          </p>
        )}
        {riskScore.mdr_flag && (
          <span className="mt-2 px-3 py-1 bg-orange-600/20 border border-orange-600/50 rounded-full text-orange-400 text-xs font-semibold">
            MDR ({riskScore.drug_class_count} classes)
          </span>
        )}
      </div>

      <div className="space-y-3 mt-2">
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">Worst-case ARG</span>
          <span className="text-gray-200 font-mono">{riskScore.worst_case_arg || '-'}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">Drug class</span>
          <span className="text-gray-200 text-xs">{riskScore.worst_case_drug_class || '-'}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">Location</span>
          <span className="text-gray-200 text-xs">{riskScore.worst_case_location || '-'}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">Transmissibility</span>
          <span className="text-gray-200">Level {riskScore.transmissibility_level ?? '-'}/5</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">VF categories</span>
          <span className="text-gray-200">{riskScore.vf_category_count ?? '-'}</span>
        </div>
      </div>
    </div>
  );
}
