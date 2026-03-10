'use client';

import Link from 'next/link';
import { FolderKanban, Calendar, TestTubes } from 'lucide-react';
import type { Project } from '@/lib/api';

interface ProjectCardProps {
  project: Project;
}

export default function ProjectCard({ project }: ProjectCardProps) {
  return (
    <Link href={`/projects/${project.id}`}>
      <div className="card hover:border-blue-500/50 hover:shadow-blue-500/10 transition-all duration-200 cursor-pointer group">
        <div className="flex items-start justify-between mb-3">
          <div className="p-2 rounded-lg bg-blue-600/20 text-blue-400 group-hover:bg-blue-600/30 transition-colors">
            <FolderKanban className="w-5 h-5" />
          </div>
        </div>
        <h3 className="text-lg font-semibold text-gray-100 mb-1 group-hover:text-blue-400 transition-colors">
          {project.name}
        </h3>
        <p className="text-sm text-gray-400 mb-4 line-clamp-2">
          {project.description || 'No description'}
        </p>
        <div className="flex items-center gap-4 text-xs text-gray-500">
          <span className="flex items-center gap-1">
            <TestTubes className="w-3.5 h-3.5" />
            {project.sample_count ?? 0} samples
          </span>
          <span className="flex items-center gap-1">
            <Calendar className="w-3.5 h-3.5" />
            {new Date(project.created_at).toLocaleDateString()}
          </span>
        </div>
      </div>
    </Link>
  );
}
