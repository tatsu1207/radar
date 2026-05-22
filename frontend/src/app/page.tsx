import Link from 'next/link';
import { ArrowRight } from 'lucide-react';

export default function IntroductionPage() {
  const steps = [
    { num: 1, title: 'Upload sequencing data', desc: 'Upload FASTQ files or fetch directly from NCBI SRA.', href: '/files' },
    { num: 2, title: 'Add metadata', desc: 'Upload a TSV with sample source, collection date, location, and any custom fields.', href: '/metadata' },
    { num: 3, title: 'Run the analysis pipeline', desc: 'QC, assembly, ARG detection, plasmid analysis, mobile element detection, and more.', href: '/analysis' },
    { num: 4, title: 'Explore results', desc: 'Resistance genes, plasmids, virulence factors, and phenotype predictions.', href: '/results' },
    { num: 5, title: 'Assess risk', desc: 'Composite risk scores combining ARG burden, virulence, and mobility.', href: '/risk' },
  ];

  return (
    <div className="max-w-3xl">
      <div className="mb-10">
        <h1 className="text-3xl font-bold text-white mb-3">RADAR</h1>
        <p className="text-lg text-gray-300 leading-relaxed">
          <strong>R</strong>esistome <strong>A</strong>nalysis, <strong>D</strong>etection,{' '}
          <strong>A</strong>ssessment &amp; <strong>R</strong>isk
        </p>
        <p className="text-gray-400 mt-3 leading-relaxed">
          A bioinformatics platform for whole-genome sequencing based antibiotic resistance analysis.
          RADAR takes raw Illumina or long-read sequencing data, runs a multi-step pipeline to detect
          resistance genes, characterize their regulatory context, identify mobile genetic elements
          and plasmids, then produces a composite clinical risk score.
        </p>
      </div>

      <h2 className="text-xl font-semibold text-white mb-4">Getting Started</h2>
      <div className="space-y-4 mb-10">
        {steps.map((step) => (
          <Link
            key={step.num}
            href={step.href}
            className="card flex items-start gap-4 hover:border-blue-500/50 transition-colors group"
          >
            <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-600/20 text-blue-400 flex items-center justify-center text-sm font-bold">
              {step.num}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-gray-100 font-medium group-hover:text-blue-400 transition-colors">
                {step.title}
              </p>
              <p className="text-sm text-gray-400 mt-0.5">{step.desc}</p>
            </div>
            <ArrowRight className="w-4 h-4 text-gray-600 group-hover:text-blue-400 flex-shrink-0 mt-1 transition-colors" />
          </Link>
        ))}
      </div>

      <h2 className="text-xl font-semibold text-white mb-4">Pipeline Overview</h2>
      <div className="card">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-3 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-400">Read QC</span>
            <span className="text-gray-300">fastp + Filtlong</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Assembly</span>
            <span className="text-gray-300">SPAdes / Flye</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Assembly QC</span>
            <span className="text-gray-300">QUAST + BUSCO</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">ARG detection</span>
            <span className="text-gray-300">AMRFinderPlus</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Promoter analysis</span>
            <span className="text-gray-300">BPROM</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">RBS analysis</span>
            <span className="text-gray-300">OSTIR</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">MGE detection</span>
            <span className="text-gray-300">MobileElementFinder</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Plasmid analysis</span>
            <span className="text-gray-300">MOB-recon</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Virulence factors</span>
            <span className="text-gray-300">AMRFinderPlus</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Risk scoring</span>
            <span className="text-gray-300">Composite (0-10)</span>
          </div>
        </div>
      </div>
    </div>
  );
}
