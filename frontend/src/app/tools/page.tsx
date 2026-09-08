'use client';

import { useState } from 'react';
import PhenotypePrediction from '@/components/tools/PhenotypePrediction';
import HazardRanking from '@/components/tools/HazardRanking';
import GenomeComparison from '@/components/tools/GenomeComparison';
import SynTracker from '@/components/tools/SynTracker';
import EasyFig from '@/components/tools/EasyFig';
import Pangenome from '@/components/tools/Pangenome';
import ResistomeTracker from '@/components/tools/ResistomeTracker';
import SRASubmission from '@/components/tools/SRASubmission';

type ToolTab = 'phenotype' | 'hazard' | 'comparison' | 'syntracker' | 'easyfig' | 'pangenome' | 'resistome' | 'sra';

export default function ToolsPage() {
  const [toolTab, setToolTab] = useState<ToolTab>('phenotype');

  const tabs: { key: ToolTab; label: string }[] = [
    { key: 'phenotype', label: 'Phenotype Prediction' },
    { key: 'hazard', label: 'Hazard Ranking' },
    { key: 'comparison', label: 'ANI' },
    { key: 'syntracker', label: 'SynTracker' },
    { key: 'easyfig', label: 'EasyFig' },
    { key: 'pangenome', label: 'Pangenome' },
    { key: 'resistome', label: 'Resistome Tracker' },
    { key: 'sra', label: 'SRA Submission' },
  ];

  return (
    <div>
      <h1 className="text-2xl font-bold text-white mb-2">Tools</h1>
      <div className="border-b border-gray-800 mb-6">
        <div className="flex gap-1">
          {tabs.map((t) => (
            <button key={t.key} onClick={() => setToolTab(t.key)} className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${toolTab === t.key ? 'border-blue-500 text-blue-400' : 'border-transparent text-gray-400 hover:text-gray-200'}`}>
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {toolTab === 'phenotype' && <PhenotypePrediction />}
      {toolTab === 'hazard' && <HazardRanking />}
      {toolTab === 'comparison' && <GenomeComparison />}
      {toolTab === 'syntracker' && <SynTracker />}
      {toolTab === 'easyfig' && <EasyFig />}
      {toolTab === 'pangenome' && <Pangenome />}
      {toolTab === 'resistome' && <ResistomeTracker />}
      {toolTab === 'sra' && <SRASubmission />}
    </div>
  );
}
