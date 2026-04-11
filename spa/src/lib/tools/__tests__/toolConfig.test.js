import { describe, it, expect } from 'vitest';
import { tools } from '../toolConfig.js';

describe('toolConfig', () => {
  it('exports exactly 13 tools', () => {
    expect(Object.keys(tools)).toHaveLength(13);
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

  it('contains all 13 expected tool IDs', () => {
    const expectedIds = [
      'search_symbols', 'read_symbol', 'find_usages', 'find_callees',
      'find_implementations', 'get_context_for', 'assess_impact',
      'get_architecture', 'find_dead_code', 'find_untested',
      'execute_query', 'find_http_endpoints', 'explore',
    ];
    expect(Object.keys(tools).sort()).toEqual(expectedIds.sort());
  });

  it('get_context_for has context resultType and members_only checkbox', () => {
    expect(tools.get_context_for.resultType).toBe('context');
    expect(tools.get_context_for.category).toBe('Analysis');
    const membersOnlyParam = tools.get_context_for.params.find(p => p.name === 'members_only');
    expect(membersOnlyParam.type).toBe('checkbox');
    expect(membersOnlyParam.default).toBe(false);
  });

  it('explore has Navigate category', () => {
    expect(tools.explore.category).toBe('Navigate');
  });

  it('find_untested and find_http_endpoints have Experimental category', () => {
    expect(tools.find_untested.category).toBe('Experimental');
    expect(tools.find_http_endpoints.category).toBe('Experimental');
  });

  it('autocomplete flag is set on symbol name params', () => {
    const fullNameAutocompleteTools = ['find_usages', 'find_callees', 'find_implementations', 'get_context_for', 'read_symbol', 'assess_impact', 'explore'];
    for (const toolId of fullNameAutocompleteTools) {
      const fullNameParam = tools[toolId].params.find(p => p.name === 'full_name');
      expect(fullNameParam, `${toolId} should have full_name param`).toBeDefined();
      expect(fullNameParam.autocomplete, `${toolId}.full_name should have autocomplete: true`).toBe(true);
    }
    const searchQueryParam = tools.search_symbols.params.find(p => p.name === 'query');
    expect(searchQueryParam.autocomplete).toBe(true);
  });
});
