'use client';

import { useState } from 'react';
import { Save, Plus, Trash2 } from 'lucide-react';
import type { Metadata } from '@/lib/api';

interface MetadataFormProps {
  metadata: Metadata | null;
  onSave: (data: Partial<Omit<Metadata, 'id' | 'sample_id'>>) => Promise<void>;
}

const SOURCE_OPTIONS = [
  'clinical',
  'environmental',
  'food',
  'animal',
  'wastewater',
  'soil',
  'water',
  'human',
  'other',
];

export default function MetadataForm({ metadata, onSave }: MetadataFormProps) {
  const [source, setSource] = useState(metadata?.source || '');
  const [collectionDate, setCollectionDate] = useState(metadata?.collection_date || '');
  const [location, setLocation] = useState(metadata?.location || '');
  const [customFields, setCustomFields] = useState<Record<string, string>>(
    metadata?.custom_fields || {}
  );
  const [newFieldKey, setNewFieldKey] = useState('');
  const [newFieldValue, setNewFieldValue] = useState('');
  const [saving, setSaving] = useState(false);

  const handleAddCustomField = () => {
    if (newFieldKey.trim()) {
      setCustomFields((prev) => ({ ...prev, [newFieldKey.trim()]: newFieldValue }));
      setNewFieldKey('');
      setNewFieldValue('');
    }
  };

  const handleRemoveCustomField = (key: string) => {
    setCustomFields((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await onSave({
        source,
        collection_date: collectionDate,
        location,
        custom_fields: customFields,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm text-gray-400 mb-1">Source</label>
          <select value={source} onChange={(e) => setSource(e.target.value)} className="input w-full">
            <option value="">Select source...</option>
            {SOURCE_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">Collection Date</label>
          <input
            type="date"
            value={collectionDate}
            onChange={(e) => setCollectionDate(e.target.value)}
            className="input w-full"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">Location</label>
          <input
            type="text"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="e.g., Hospital ICU, River sample site"
            className="input w-full"
          />
        </div>
      </div>

      {/* Custom fields */}
      <div>
        <label className="block text-sm text-gray-400 mb-2">Custom Fields</label>
        {Object.entries(customFields).length > 0 && (
          <div className="space-y-2 mb-3">
            {Object.entries(customFields).map(([key, value]) => (
              <div key={key} className="flex items-center gap-2">
                <span className="text-sm text-gray-300 font-medium min-w-[120px]">{key}:</span>
                <input
                  type="text"
                  value={value}
                  onChange={(e) => setCustomFields((prev) => ({ ...prev, [key]: e.target.value }))}
                  className="input flex-1 text-sm"
                />
                <button
                  type="button"
                  onClick={() => handleRemoveCustomField(key)}
                  className="p-1.5 rounded-lg hover:bg-red-600/20 text-gray-400 hover:text-red-400 transition-colors"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={newFieldKey}
            onChange={(e) => setNewFieldKey(e.target.value)}
            placeholder="Field name"
            className="input text-sm flex-1"
          />
          <input
            type="text"
            value={newFieldValue}
            onChange={(e) => setNewFieldValue(e.target.value)}
            placeholder="Value"
            className="input text-sm flex-1"
          />
          <button
            type="button"
            onClick={handleAddCustomField}
            disabled={!newFieldKey.trim()}
            className="btn-secondary p-2"
          >
            <Plus className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="flex justify-end pt-2">
        <button type="submit" disabled={saving} className="btn-primary flex items-center gap-2">
          <Save className="w-4 h-4" />
          {saving ? 'Saving...' : 'Save Metadata'}
        </button>
      </div>
    </form>
  );
}
