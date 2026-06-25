'use client';

import { useState, useEffect, useMemo } from 'react';
import { useParams } from 'next/navigation';
import { ArrowLeft } from 'lucide-react';
import Link from 'next/link';
import { getProject, getPhylogeny } from '@/lib/api';
import type { Project, PhylogenyData } from '@/lib/api';

// Parse Newick tree into a renderable structure
interface TreeNode {
  name: string;
  length: number;
  children: TreeNode[];
  x?: number;
  y?: number;
  leafIndex?: number;
}

function parseNewick(s: string): TreeNode | null {
  if (!s || s === ';') return null;
  let i = 0;

  function readNode(): TreeNode {
    const node: TreeNode = { name: '', length: 0, children: [] };
    if (s[i] === '(') {
      i++; // skip '('
      node.children.push(readNode());
      while (s[i] === ',') {
        i++; // skip ','
        node.children.push(readNode());
      }
      i++; // skip ')'
    }
    // Read name
    let name = '';
    while (i < s.length && s[i] !== ':' && s[i] !== ',' && s[i] !== ')' && s[i] !== ';') {
      name += s[i++];
    }
    node.name = name;
    // Read branch length
    if (i < s.length && s[i] === ':') {
      i++; // skip ':'
      let len = '';
      while (i < s.length && s[i] !== ',' && s[i] !== ')' && s[i] !== ';') {
        len += s[i++];
      }
      node.length = parseFloat(len) || 0;
    }
    return node;
  }

  const tree = readNode();
  return tree;
}

function getLeafCount(node: TreeNode): number {
  if (node.children.length === 0) return 1;
  return node.children.reduce((sum, c) => sum + getLeafCount(c), 0);
}

function getMaxDepth(node: TreeNode, depth = 0): number {
  if (node.children.length === 0) return depth + node.length;
  return Math.max(...node.children.map((c) => getMaxDepth(c, depth + node.length)));
}

// Layout the tree for SVG rendering
function layoutTree(
  node: TreeNode,
  x: number,
  leafCounter: { count: number },
  leafSpacing: number,
  xScale: number,
): void {
  if (node.children.length === 0) {
    node.x = x + node.length * xScale;
    node.y = leafCounter.count * leafSpacing;
    node.leafIndex = leafCounter.count;
    leafCounter.count++;
  } else {
    for (const child of node.children) {
      layoutTree(child, x + node.length * xScale, leafCounter, leafSpacing, xScale);
    }
    node.x = x + node.length * xScale;
    const childYs = node.children.map((c) => c.y!);
    node.y = (Math.min(...childYs) + Math.max(...childYs)) / 2;
  }
}

// Collect all nodes for rendering
function collectNodes(node: TreeNode, parentX: number, result: { node: TreeNode; parentX: number }[]): void {
  result.push({ node, parentX });
  for (const child of node.children) {
    collectNodes(child, node.x!, result);
  }
}

const RISK_COLORS: Record<string, string> = {
  'ST131': '#EF4444',
  'ST410': '#F59E0B',
  'ST69': '#3B82F6',
  'ST38': '#10B981',
  'ST648': '#8B5CF6',
  'ST73': '#EC4899',
  'ST95': '#06B6D4',
  'ST10': '#F97316',
};

function stColor(st: string | null): string {
  if (!st) return '#6B7280';
  return RISK_COLORS[`ST${st}`] || '#6B7280';
}

export default function ComparisonPage() {
  const params = useParams();
  const projectId = params.id as string;

  const [project, setProject] = useState<Project | null>(null);
  const [phylo, setPhylo] = useState<PhylogenyData | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<'tree' | 'matrix'>('tree');

  useEffect(() => {
    Promise.all([
      getProject(projectId),
      getPhylogeny(projectId),
    ]).then(([proj, ph]) => {
      setProject(proj);
      setPhylo(ph);
    }).catch(() => {})
      .finally(() => setLoading(false));
  }, [projectId]);

  // Tree SVG
  const treeSvg = useMemo(() => {
    if (!phylo?.newick) return null;
    const tree = parseNewick(phylo.newick);
    if (!tree) return null;

    const leafCount = getLeafCount(tree);
    const maxDepth = getMaxDepth(tree);
    if (maxDepth === 0) return null;

    const MARGIN = { top: 20, right: 200, bottom: 20, left: 30 };
    const leafSpacing = 32;
    const plotWidth = 400;
    const plotHeight = leafCount * leafSpacing;
    const xScale = plotWidth / maxDepth;

    layoutTree(tree, 0, { count: 0 }, leafSpacing, xScale);

    const allNodes: { node: TreeNode; parentX: number }[] = [];
    collectNodes(tree, 0, allNodes);

    const width = MARGIN.left + plotWidth + MARGIN.right;
    const height = MARGIN.top + plotHeight + MARGIN.bottom;

    // Build info map
    const infoMap: Record<string, (typeof phylo.sample_info)[0]> = {};
    for (const si of phylo.sample_info) {
      infoMap[si.name] = si;
    }

    return (
      <svg width={width} height={height} className="bg-gray-900/50 rounded-lg">
        {/* Branch lines */}
        {allNodes.map(({ node, parentX }, i) => {
          if (!node.x || node.y === undefined) return null;
          const x = MARGIN.left + node.x;
          const y = MARGIN.top + node.y;
          const px = MARGIN.left + parentX;
          return (
            <g key={i}>
              {/* Horizontal branch */}
              <line x1={px} y1={y} x2={x} y2={y} stroke="#4B5563" strokeWidth={1.5} />
              {/* Vertical connector from parent */}
              {node !== tree && node.children.length === 0 && null}
            </g>
          );
        })}

        {/* Vertical connectors for internal nodes */}
        {allNodes.filter(({ node }) => node.children.length > 0).map(({ node }, i) => {
          const x = MARGIN.left + node.x!;
          const childYs = node.children.map((c) => MARGIN.top + c.y!);
          const minY = Math.min(...childYs);
          const maxY = Math.max(...childYs);
          return (
            <line key={`v-${i}`} x1={x} y1={minY} x2={x} y2={maxY} stroke="#4B5563" strokeWidth={1.5} />
          );
        })}

        {/* Leaf labels */}
        {allNodes.filter(({ node }) => node.children.length === 0).map(({ node }, i) => {
          const x = MARGIN.left + node.x!;
          const y = MARGIN.top + node.y!;
          const info = infoMap[node.name];
          const color = stColor(info?.st || null);
          return (
            <g key={`leaf-${i}`}>
              <circle cx={x} cy={y} r={4} fill={color} />
              <text x={x + 10} y={y + 1} dominantBaseline="middle" fill="#E5E7EB" fontSize={12} fontFamily="sans-serif">
                {node.name}
              </text>
              {info?.st && (
                <text x={x + 10} y={y + 14} dominantBaseline="middle" fill={color} fontSize={10} fontFamily="sans-serif">
                  ST{info.st}
                </text>
              )}
              {info?.species && (
                <text x={x + 10} y={y - 12} dominantBaseline="middle" fill="#9CA3AF" fontSize={9} fontFamily="sans-serif" fontStyle="italic">
                  {info.species}
                </text>
              )}
            </g>
          );
        })}

        {/* Scale bar */}
        {maxDepth > 0 && (() => {
          const scaleAlleles = Math.max(1, Math.round(maxDepth / 5));
          const scaleWidth = scaleAlleles * xScale;
          const sy = height - 10;
          return (
            <g>
              <line x1={MARGIN.left} y1={sy} x2={MARGIN.left + scaleWidth} y2={sy} stroke="#9CA3AF" strokeWidth={1.5} />
              <line x1={MARGIN.left} y1={sy - 3} x2={MARGIN.left} y2={sy + 3} stroke="#9CA3AF" strokeWidth={1} />
              <line x1={MARGIN.left + scaleWidth} y1={sy - 3} x2={MARGIN.left + scaleWidth} y2={sy + 3} stroke="#9CA3AF" strokeWidth={1} />
              <text x={MARGIN.left + scaleWidth / 2} y={sy - 6} textAnchor="middle" fill="#9CA3AF" fontSize={10}>
                {scaleAlleles} allele{scaleAlleles !== 1 ? 's' : ''}
              </text>
            </g>
          );
        })()}
      </svg>
    );
  }, [phylo]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <Link href={`/projects/${projectId}`} className="text-gray-400 hover:text-gray-200">
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <div>
          <h1 className="text-2xl font-bold text-white">Genomic Comparison</h1>
          <p className="text-gray-400 text-sm">{project?.name} — cgMLST-based phylogeny</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6">
        {(['tree', 'matrix'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === t ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-gray-200'
            }`}
          >
            {t === 'tree' ? 'Phylogenetic Tree' : 'Distance Matrix'}
          </button>
        ))}
      </div>

      {phylo?.message && (
        <div className="card mb-6">
          <p className="text-gray-400 text-center py-4">{phylo.message}</p>
        </div>
      )}

      {/* Tree tab */}
      {tab === 'tree' && (
        <div className="card">
          <h2 className="text-lg font-semibold text-gray-100 mb-4">
            Neighbor-Joining Tree (cgMLST allelic distances)
          </h2>
          {treeSvg ? (
            <div className="overflow-x-auto">{treeSvg}</div>
          ) : (
            <p className="text-gray-500 text-center py-8">
              {phylo && phylo.samples.length < 2
                ? 'Need at least 2 samples with cgMLST profiles.'
                : 'No cgMLST data available. Run the pipeline with a supported species.'}
            </p>
          )}
          {phylo && phylo.sample_info.length > 0 && (
            <div className="mt-4 text-xs text-gray-500">
              Supported species: E. coli, Salmonella, K. pneumoniae, L. monocytogenes, C. jejuni, S. aureus.
              cgMLST schemas must be installed in databases/cgmlst_schemas/.
            </div>
          )}
        </div>
      )}

      {/* Distance matrix tab */}
      {tab === 'matrix' && phylo && phylo.distance_matrix.length > 0 && (
        <div className="card">
          <h2 className="text-lg font-semibold text-gray-100 mb-4">
            Pairwise Allelic Distance Matrix
          </h2>
          <div className="overflow-x-auto">
            <table className="text-xs">
              <thead>
                <tr>
                  <th className="px-2 py-1 text-left text-gray-400 font-medium sticky left-0 bg-gray-900"></th>
                  {phylo.samples.map((s) => (
                    <th key={s} className="px-2 py-1 text-gray-400 font-medium text-center whitespace-nowrap" style={{ writingMode: 'vertical-lr', maxHeight: 120 }}>
                      {s}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {phylo.samples.map((s, i) => (
                  <tr key={s}>
                    <td className="px-2 py-1 text-gray-300 font-medium whitespace-nowrap sticky left-0 bg-gray-900">{s}</td>
                    {phylo.distance_matrix[i].map((d, j) => {
                      const maxDist = Math.max(...phylo.distance_matrix.flat().filter((v) => v > 0));
                      const intensity = maxDist > 0 ? d / maxDist : 0;
                      const bg = i === j ? 'transparent'
                        : `rgba(239, 68, 68, ${Math.min(0.6, intensity * 0.6)})`;
                      return (
                        <td key={j} className="px-2 py-1 text-center font-mono"
                          style={{ backgroundColor: bg }}
                          title={phylo.shared_loci ? `${d} differences / ${phylo.shared_loci[i][j]} shared loci` : `${d} allelic differences`}
                        >
                          <span className={i === j ? 'text-gray-700' : 'text-gray-200'}>{d}</span>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {phylo.shared_loci && (
            <p className="mt-2 text-xs text-gray-500">
              Hover cells to see shared loci count. Distance = number of differing alleles among shared loci.
            </p>
          )}
        </div>
      )}

      {tab === 'matrix' && (!phylo || phylo.distance_matrix.length === 0) && (
        <div className="card">
          <p className="text-gray-500 text-center py-8">No distance matrix available.</p>
        </div>
      )}
    </div>
  );
}
