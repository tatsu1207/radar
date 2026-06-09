'use client';

import { useState } from 'react';
import Modal from '@/components/Modal';
import { submitSRA } from '@/lib/api';

interface SRAFetchDialogProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  onSubmit: () => void;
}

export default function SRAFetchDialog({ isOpen, onClose, projectId, onSubmit }: SRAFetchDialogProps) {
  const [text, setText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function parseGroups(input: string): string[][] {
    return input
      .split(/\n/)
      .map((line) => line.split(/[\s,;]+/).map((s) => s.trim()).filter((s) => s.length > 0))
      .filter((group) => group.length > 0);
  }

  function countSamples(input: string): number {
    return parseGroups(input).length;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const groups = parseGroups(text);
    if (groups.length === 0) return;

    setSubmitting(true);
    setError(null);
    try {
      await submitSRA(projectId, [], groups);
      setText('');
      onSubmit();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit SRA accessions');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Fetch from SRA">
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="p-3 bg-red-600/20 border border-red-600/50 rounded-lg text-red-300 text-sm">
            {error}
          </div>
        )}
        <div>
          <label className="block text-sm text-gray-400 mb-1">SRR Accessions</label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={6}
            className="input w-full resize-none font-mono text-sm"
            placeholder={"SRR1111111 SRR2222222   ← hybrid (Illumina + ONT)\nSRR3333333              ← single platform"}
            autoFocus
          />
          <p className="text-xs text-gray-500 mt-1">
            Each line = one sample. For hybrid samples, put Illumina and ONT accessions on the same line.
          </p>
        </div>
        <div className="flex justify-end gap-3 pt-2">
          <button type="button" onClick={onClose} className="btn-secondary">
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting || countSamples(text) === 0}
            className="btn-primary"
          >
            {submitting ? 'Submitting...' : `Fetch ${countSamples(text) || ''} Sample${countSamples(text) !== 1 ? 's' : ''}`}
          </button>
        </div>
      </form>
    </Modal>
  );
}
