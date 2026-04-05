<script>
  import { untrack } from 'svelte';
  import { apiCall } from '../api.js';
  import { tools } from './toolConfig.js';

  const { toolId, initialValues = null, onResult, onError, onLoading, onRefresh, onClearInitialValues } = $props();
  const config = $derived(tools[toolId]);

  let formValues = $state({});
  let submitting = $state(false);

  // Reset form values when tool changes, applying defaults and optional initialValues
  $effect(() => {
    if (config) {
      const vals = {};
      for (const p of config.params) {
        vals[p.name] = p.default !== undefined ? p.default : (p.type === 'checkbox' ? false : '');
      }
      if (initialValues) {
        for (const [k, v] of Object.entries(initialValues)) {
          if (k in vals) vals[k] = v;
        }
      }
      formValues = vals;
      if (initialValues) {
        untrack(() => { submit(); });
        onClearInitialValues?.();
      }
    }
  });

  async function submit() {
    if (submitting) return;

    // Build params, converting empty strings to null for optional params
    const params = {};
    for (const p of config.params) {
      const val = formValues[p.name];
      if (p.type === 'checkbox') {
        params[p.name] = val;
      } else if (p.type === 'number' && val !== '' && val !== undefined) {
        params[p.name] = Number(val);
      } else if (val !== '' && val !== undefined && val !== null) {
        params[p.name] = val;
      }
    }

    submitting = true;
    onLoading?.(true);
    try {
      const result = await apiCall(config.endpoint, params, config.method);
      onResult?.(result, config.resultType, params);
    } catch (err) {
      onError?.(err.message);
    } finally {
      submitting = false;
      onLoading?.(false);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    await submit();
  }
</script>

{#if config}
  {#if config.autoRun}
    <div class="tool-form">
      <h2 class="heading">{config.label}</h2>
      <button type="button" class="submit-btn" onclick={() => onRefresh?.(toolId)}>
        {config.cta}
      </button>
    </div>
  {:else}
    <form class="tool-form" onsubmit={handleSubmit}>
      <h2 class="heading">{config.label}</h2>
      <div class="form-fields">
        {#each config.params as param}
          {#if param.hidden}<!-- skip hidden params (e.g. limit/offset on paginated tools — managed by Pagination component) -->{:else}
          <div class="field">
            <label class="label" for={param.name}>{param.label}</label>
            {#if param.type === 'textarea'}
              <textarea
                id={param.name}
                bind:value={formValues[param.name]}
                placeholder={param.placeholder || ''}
                required={param.required}
                rows="4"
              ></textarea>
            {:else if param.type === 'select'}
              <select id={param.name} bind:value={formValues[param.name]}>
                {#each param.options as opt}
                  <option value={opt}>{opt || param.defaultLabel || '(any)'}</option>
                {/each}
              </select>
            {:else if param.type === 'checkbox'}
              <label class="checkbox-label">
                <input type="checkbox" bind:checked={formValues[param.name]} />
                {param.label}
              </label>
            {:else}
              <input
                id={param.name}
                type={param.type}
                bind:value={formValues[param.name]}
                placeholder={param.placeholder || ''}
                required={param.required}
              />
            {/if}
          </div>
          {/if}
        {/each}
      </div>
      <button type="submit" class="submit-btn" disabled={submitting}>
        {submitting ? 'Loading...' : config.cta}
      </button>
    </form>
  {/if}
{/if}

<style>
  .tool-form {
    margin-bottom: 24px;
  }
  .tool-form .heading {
    margin-bottom: 16px;
  }
  .form-fields {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
    gap: 16px;
    margin-bottom: 16px;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .field .label {
    color: var(--color-text-secondary);
  }
  input, select, textarea {
    padding: 8px 12px;
    border: 1px solid var(--color-border);
    border-radius: 4px;
    background: var(--color-dominant);
    color: var(--color-text-primary);
    font-size: 14px;
    font-family: inherit;
  }
  input:focus, select:focus, textarea:focus {
    outline: none;
    border-color: var(--color-accent);
  }
  textarea {
    resize: vertical;
    font-family: monospace;
  }
  .checkbox-label {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    cursor: pointer;
  }
  .checkbox-label input[type="checkbox"] {
    width: 16px;
    height: 16px;
  }
  .submit-btn {
    padding: 8px 24px;
    background: var(--color-accent);
    color: white;
    border: none;
    border-radius: 4px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
  }
  .submit-btn:hover:not(:disabled) {
    opacity: 0.9;
  }
  .submit-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
</style>
