import { describe, it, expect } from 'vitest';
import { tools } from '../toolConfig.js';

describe('toolConfig', () => {
  it('exports exactly 10 tools', () => {
    expect(Object.keys(tools)).toHaveLength(10);
  });

  it('execute_query uses POST method', () => {
    expect(tools.execute_query.method).toBe('POST');
  });

  it('all other tools use GET method', () => {
    for (const [id, config] of Object.entries(tools)) {
      if (id !== 'execute_query') {
        expect(config.method).toBe('GET');
      }
    }
  });

  it('every tool has required metadata fields', () => {
    for (const [id, config] of Object.entries(tools)) {
      expect(config).toHaveProperty('endpoint');
      expect(config).toHaveProperty('method');
      expect(config).toHaveProperty('params');
      expect(config).toHaveProperty('resultType');
      expect(config).toHaveProperty('label');
      expect(config).toHaveProperty('cta');
      expect(Array.isArray(config.params)).toBe(true);
    }
  });

  it('search_symbols has a required query param', () => {
    const queryParam = tools.search_symbols.params.find(p => p.name === 'query');
    expect(queryParam).toBeDefined();
    expect(queryParam.required).toBe(true);
  });

  it('find_callees has graph resultType', () => {
    expect(tools.find_callees.resultType).toBe('graph');
  });

  it('find_usages has graph resultType', () => {
    expect(tools.find_usages.resultType).toBe('graph');
  });

  it('find_dead_code has no path param but has subdirectory param', () => {
    const pathParam = tools.find_dead_code.params.find(p => p.name === 'path');
    expect(pathParam).toBeUndefined();
    const subdirParam = tools.find_dead_code.params.find(p => p.name === 'subdirectory');
    expect(subdirParam).toBeDefined();
    expect(subdirParam.required).toBe(false);
  });

  it('find_untested has no path param but has subdirectory param', () => {
    const pathParam = tools.find_untested.params.find(p => p.name === 'path');
    expect(pathParam).toBeUndefined();
    const subdirParam = tools.find_untested.params.find(p => p.name === 'subdirectory');
    expect(subdirParam).toBeDefined();
  });

  it('get_architecture has autoRun, empty params, and Refresh cta', () => {
    expect(tools.get_architecture.autoRun).toBe(true);
    expect(tools.get_architecture.params).toHaveLength(0);
    expect(tools.get_architecture.cta).toBe('Refresh');
  });

  it('contains all 10 expected tool IDs', () => {
    const expectedIds = [
      'search_symbols', 'find_usages', 'find_callees', 'get_hierarchy',
      'get_context_for', 'get_architecture', 'find_dead_code', 'find_untested',
      'execute_query', 'find_http_endpoints',
    ];
    expect(Object.keys(tools).sort()).toEqual(expectedIds.sort());
  });

  it('get_context_for has context resultType and scope select defaulting to impact', () => {
    expect(tools.get_context_for.resultType).toBe('context');
    expect(tools.get_context_for.category).toBe('Navigate');
    const scopeParam = tools.get_context_for.params.find(p => p.name === 'scope');
    expect(scopeParam.type).toBe('select');
    expect(scopeParam.default).toBe('impact');
    expect(scopeParam.options).not.toContain('');
  });
});
