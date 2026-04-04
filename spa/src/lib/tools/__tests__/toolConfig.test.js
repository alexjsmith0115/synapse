import { describe, it, expect } from 'vitest';
import { tools } from '../toolConfig.js';

describe('toolConfig', () => {
  it('exports exactly 9 tools', () => {
    expect(Object.keys(tools)).toHaveLength(9);
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

  it('contains all 9 expected tool IDs', () => {
    const expectedIds = [
      'search_symbols', 'find_usages', 'find_callees', 'get_hierarchy',
      'get_architecture', 'find_dead_code', 'find_untested',
      'execute_query', 'find_http_endpoints',
    ];
    expect(Object.keys(tools).sort()).toEqual(expectedIds.sort());
  });
});
