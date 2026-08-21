import Link from 'next/link';
import { ArrowRight, Dna, Shield, FlaskConical, Map, BarChart3 } from 'lucide-react';

export default function IntroductionPage() {
  const steps = [
    { num: 1, title: 'Upload sequencing data', desc: 'Upload FASTQ/FASTA files, fetch from NCBI SRA, or import from BV-BRC. Supports Illumina paired-end, ONT, and PacBio HiFi reads.', href: '/files' },
    { num: 2, title: 'Run the analysis pipeline', desc: 'One-click pipeline: QC, assembly, resistance gene detection, plasmid typing, mobile elements, virulence factors, and more. Track progress in real time.', href: '/files' },
    { num: 3, title: 'Add metadata', desc: 'Upload a TSV or manually enter sample metadata: source, collection date, location, and custom fields.', href: '/metadata' },
    { num: 4, title: 'Explore annotation results', desc: 'Per-sample annotation detail with synteny maps, defense systems, plasmid maps, and single-file TSV export.', href: '/results' },
  ];

  const pipelineSteps = [
    { category: 'Quality Control', tools: [
      { name: 'fastp', desc: 'Adapter trimming & quality filtering (Illumina)' },
      { name: 'Chopper', desc: 'Long-read quality filtering & trimming (ONT)' },
    ]},
    { category: 'Assembly', tools: [
      { name: 'SPAdes', desc: 'Short-read de novo assembly' },
      { name: 'Flye + Medaka + Polypolish', desc: 'Hybrid/long-read assembly with polishing' },
      { name: 'QUAST + BUSCO', desc: 'Assembly quality and completeness assessment' },
    ]},
    { category: 'Species & Typing', tools: [
      { name: 'skani / 16S BLAST', desc: 'Species identification (ANI or 16S rRNA)' },
      { name: 'MLST', desc: 'Multi-locus sequence typing' },
      { name: 'SISTR + Kleborate', desc: 'In silico serotyping (Salmonella, Klebsiella)' },
      { name: 'chewBBACA', desc: 'Core-genome MLST for phylogenomic comparison' },
    ]},
    { category: 'Resistance & Virulence', tools: [
      { name: 'AMRFinderPlus', desc: 'Antimicrobial resistance gene detection' },
      { name: 'ResFinder / PointFinder', desc: 'Resistance genes and point mutations' },
      { name: 'BacMet2', desc: 'Biocide and metal resistance genes' },
      { name: 'Virulence factors', desc: 'Virulence gene detection via AMRFinderPlus' },
    ]},
    { category: 'Mobile Genetic Elements', tools: [
      { name: 'MOB-recon', desc: 'Plasmid reconstruction, replicon typing, mobility classification' },
      { name: 'MobileElementFinder', desc: 'Insertion sequence detection' },
      { name: 'IntegronFinder', desc: 'Integron detection' },
      { name: 'geNomad', desc: 'Prophage and viral region detection' },
    ]},
    { category: 'Expression Context', tools: [
      { name: 'BPROM + OSTIR', desc: 'Promoter strength and ribosome binding site analysis' },
      { name: 'Prodigal', desc: 'Gene prediction, codon adaptation, rare codons, GC deviation' },
      { name: 'Infernal / Rfam', desc: 'sRNA detection near resistance genes' },
    ]},
    { category: 'Defense & Structure', tools: [
      { name: 'DefenseFinder', desc: 'Bacterial defense systems (RM, CRISPR-Cas, Abi, BREX, Zorya, etc.)' },
      { name: 'minced', desc: 'CRISPR array detection with spacer/repeat analysis' },
      { name: 'ICEfinder', desc: 'Integrative and conjugative element detection' },
    ]},
    { category: 'Prediction & Scoring', tools: [
      { name: 'ML Phenotype Prediction', desc: '107 Random Forest models across 5 species, 35 antibiotics' },
      { name: 'Hazard Ranking', desc: 'R1-R12 rank from WHO AWaRe tier and ARG transmissibility' },
    ]},
  ];

  const highlights = [
    { icon: Dna, title: '27+ Bioinformatics Tools', desc: 'Isolated conda environments for reproducibility. From QC to phenotype prediction, serotyping, and cgMLST.' },
    { icon: Shield, title: 'ML Phenotype Prediction', desc: 'Pre-trained Random Forest models predict resistance to 13-35 antibiotics per species with confidence scores.' },
    { icon: FlaskConical, title: 'Expression Context', desc: 'Goes beyond gene presence: analyzes promoter strength, RBS efficiency, codon adaptation to explain why genes may or may not confer resistance.' },
    { icon: Map, title: 'Interactive Maps', desc: 'Circular plasmid maps grouped by cluster, synteny maps showing MGE-associated ARGs and virulence factors, and cgMLST-based phylogenetic trees.' },
  ];

  return (
    <div className="max-w-4xl">
      <div className="mb-10">
        <h1 className="text-3xl font-bold text-white mb-3">RADAR</h1>
        <p className="text-lg text-gray-300 leading-relaxed">
          <strong>R</strong>esistome <strong>A</strong>nalysis, <strong>D</strong>etection,{' '}
          <strong>A</strong>ssessment &amp; <strong>R</strong>esearch
        </p>
        <p className="text-gray-400 mt-3 leading-relaxed">
          A bioinformatics platform for whole-genome sequencing (WGS) based antimicrobial resistance analysis.
          RADAR takes raw Illumina, ONT, or PacBio sequencing data (or pre-assembled genomes), runs a
          comprehensive annotation pipeline covering resistance genes, virulence factors, mobile genetic elements,
          biocide/metal resistance, and regulatory context, then uses machine learning to predict antibiotic
          resistance phenotypes and assign hazard ranks based on clinical importance and transmissibility.
        </p>
        <p className="text-gray-500 mt-2 text-sm">
          Supports hybrid assembly (Illumina + ONT), PacBio HiFi, and pre-assembled FASTA input.
          Optimized for <em>Escherichia coli</em>, <em>Salmonella enterica</em>, <em>Klebsiella pneumoniae</em>,{' '}
          <em>Staphylococcus aureus</em>, and <em>Acinetobacter baumannii</em>.
        </p>
      </div>

      {/* Highlights */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-10">
        {highlights.map((h) => {
          const Icon = h.icon;
          return (
            <div key={h.title} className="card">
              <div className="flex items-start gap-3">
                <Icon className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-gray-100 font-medium text-sm">{h.title}</p>
                  <p className="text-gray-400 text-xs mt-1">{h.desc}</p>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <h2 className="text-xl font-semibold text-white mb-4">Getting Started</h2>
      <div className="space-y-3 mb-10">
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
      <p className="text-gray-400 text-sm mb-4">
        The pipeline runs 27+ annotation tools in sequence, with skip logic for re-runs.
        Only one pipeline runs at a time; additional samples are queued automatically.
      </p>
      <div className="space-y-4 mb-10">
        {pipelineSteps.map((group) => (
          <div key={group.category} className="card">
            <h3 className="text-sm font-semibold text-blue-400 mb-2">{group.category}</h3>
            <div className="space-y-1.5">
              {group.tools.map((tool) => (
                <div key={tool.name} className="flex items-start gap-2">
                  <span className="text-gray-300 text-sm font-medium min-w-[180px] flex-shrink-0">{tool.name}</span>
                  <span className="text-gray-500 text-sm">{tool.desc}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <h2 className="text-xl font-semibold text-white mb-4">Input Formats</h2>
      <div className="card mb-10">
        <div className="space-y-3 text-sm">
          <div>
            <p className="text-gray-200 font-medium">Illumina paired-end</p>
            <p className="text-gray-500 font-mono text-xs mt-0.5">SAMPLE_R1.fastq.gz + SAMPLE_R2.fastq.gz &nbsp;or&nbsp; SAMPLE_1.fastq.gz + SAMPLE_2.fastq.gz</p>
          </div>
          <div>
            <p className="text-gray-200 font-medium">Long reads (ONT / PacBio)</p>
            <p className="text-gray-500 font-mono text-xs mt-0.5">SAMPLE.fastq.gz &nbsp;(platform auto-detected from FASTQ headers)</p>
          </div>
          <div>
            <p className="text-gray-200 font-medium">Hybrid (Illumina + ONT)</p>
            <p className="text-gray-500 font-mono text-xs mt-0.5">SAMPLE_R1.fastq.gz + SAMPLE_R2.fastq.gz + SAMPLE.fastq.gz</p>
          </div>
          <div>
            <p className="text-gray-200 font-medium">Pre-assembled genome</p>
            <p className="text-gray-500 font-mono text-xs mt-0.5">SAMPLE.fasta &nbsp;(skips QC and assembly, goes directly to annotation)</p>
          </div>
        </div>
      </div>

      <h2 className="text-xl font-semibold text-white mb-4">Output</h2>
      <div className="card">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-400">Assembly QC</span>
            <span className="text-gray-300">QUAST metrics + BUSCO completeness</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Resistance genes</span>
            <span className="text-gray-300">AMRFinderPlus with expression context</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Phenotype prediction</span>
            <span className="text-gray-300">ML per-antibiotic R/S with confidence</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Plasmid maps</span>
            <span className="text-gray-300">Circular maps with ARGs, VFs, IS, T4SS</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Synteny maps</span>
            <span className="text-gray-300">MGE-flanked ARGs/VFs with adjustable distance</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Defense systems</span>
            <span className="text-gray-300">CRISPR-Cas, RM, Abi, ICE, and more</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Biocide/metal resistance</span>
            <span className="text-gray-300">BacMet2 gene detection</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Serotyping</span>
            <span className="text-gray-300">SISTR (Salmonella) + Kleborate (Klebsiella)</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Genomic comparison</span>
            <span className="text-gray-300">cgMLST phylogenetic tree (NJ from allelic distances)</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Hazard ranking</span>
            <span className="text-gray-300">R1-R12 rank (AWaRe tier x transmissibility)</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Export</span>
            <span className="text-gray-300">Single TSV per sample or bulk ZIP export</span>
          </div>
        </div>
      </div>
    </div>
  );
}
