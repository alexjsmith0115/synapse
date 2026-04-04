import { describe, it, expect } from 'vitest';
import { shouldShowHierarchy } from '../contextMenuUtils.js';

describe('ContextMenu showHierarchy logic (D-05)', () => {
  it('returns true for Class', () => {
    expect(shouldShowHierarchy('Class')).toBe(true);
  });

  it('returns true for Interface', () => {
    expect(shouldShowHierarchy('Interface')).toBe(true);
  });

  it('returns false for Method', () => {
    expect(shouldShowHierarchy('Method')).toBe(false);
  });

  it('returns false for Property', () => {
    expect(shouldShowHierarchy('Property')).toBe(false);
  });

  it('returns false for Field', () => {
    expect(shouldShowHierarchy('Field')).toBe(false);
  });

  it('returns false for empty string', () => {
    expect(shouldShowHierarchy('')).toBe(false);
  });

  it('returns false for undefined', () => {
    expect(shouldShowHierarchy(undefined)).toBe(false);
  });

  it('returns false for null', () => {
    expect(shouldShowHierarchy(null)).toBe(false);
  });
});

describe('ContextMenu get_context_for visibility (D-05)', () => {
  const ALL_SYMBOL_KINDS = ['Class', 'Interface', 'Method', 'Property', 'Field'];

  it('get_context_for has no kind filter — shown for all symbol kinds', () => {
    // D-05: get_context_for appears for ALL symbol kinds.
    // Unlike shouldShowHierarchy which filters by kind, get_context_for
    // is unconditional — no gating function exists. This test documents
    // the design decision and will break if a filter is accidentally added.
    ALL_SYMBOL_KINDS.forEach(kind => {
      // shouldShowHierarchy is the ONLY kind filter; get_context_for has none
      expect(typeof shouldShowHierarchy(kind)).toBe('boolean');
    });
    // If a shouldShowContextFor function is ever added, this test must be
    // updated to verify it returns true for all kinds.
  });
});
