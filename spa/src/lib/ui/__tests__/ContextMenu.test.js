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
