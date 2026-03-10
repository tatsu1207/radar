'use client';

import {
  RadarChart as RechartsRadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
  Tooltip,
} from 'recharts';
import StatusBadge from './StatusBadge';
import type { RiskScore } from '@/lib/api';

interface RadarChartProps {
  riskScore: RiskScore;
}

const riskColor: Record<string, string> = {
  low: '#22c55e',
  medium: '#eab308',
  high: '#f97316',
  critical: '#ef4444',
};

export default function RadarChartComponent({ riskScore }: RadarChartProps) {
  const data = [
    { axis: 'ARG Risk', value: riskScore.arg_score, fullMark: 1 },
    { axis: 'VF Risk', value: riskScore.vf_score, fullMark: 1 },
    { axis: 'Mobility Risk', value: riskScore.mobility_score, fullMark: 1 },
  ];

  const color = riskColor[riskScore.risk_category] || '#6b7280';

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-100">Risk Assessment</h3>
        <StatusBadge status={riskScore.risk_category} type="risk" />
      </div>

      <div className="w-full h-64">
        <ResponsiveContainer width="100%" height="100%">
          <RechartsRadarChart data={data} cx="50%" cy="50%" outerRadius="75%">
            <PolarGrid stroke="#374151" />
            <PolarAngleAxis
              dataKey="axis"
              tick={{ fill: '#9ca3af', fontSize: 12 }}
            />
            <PolarRadiusAxis
              angle={90}
              domain={[0, 1]}
              tick={{ fill: '#6b7280', fontSize: 10 }}
              tickCount={5}
            />
            <Radar
              name="Risk"
              dataKey="value"
              stroke={color}
              fill={color}
              fillOpacity={0.25}
              strokeWidth={2}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1f2937',
                border: '1px solid #374151',
                borderRadius: '8px',
                color: '#f3f4f6',
              }}
              formatter={(value: number) => [value.toFixed(3), 'Score']}
            />
          </RechartsRadarChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-4 text-center">
        <p className="text-sm text-gray-400">Composite Score</p>
        <p className="text-3xl font-bold" style={{ color }}>
          {riskScore.composite_score.toFixed(3)}
        </p>
      </div>

      <div className="grid grid-cols-3 gap-4 mt-4">
        <div className="text-center">
          <p className="text-xs text-gray-500">ARG</p>
          <p className="text-sm font-semibold text-gray-300">{riskScore.arg_score.toFixed(3)}</p>
        </div>
        <div className="text-center">
          <p className="text-xs text-gray-500">Virulence</p>
          <p className="text-sm font-semibold text-gray-300">{riskScore.vf_score.toFixed(3)}</p>
        </div>
        <div className="text-center">
          <p className="text-xs text-gray-500">Mobility</p>
          <p className="text-sm font-semibold text-gray-300">{riskScore.mobility_score.toFixed(3)}</p>
        </div>
      </div>
    </div>
  );
}
