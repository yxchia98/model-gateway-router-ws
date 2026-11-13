const $ = (selector, parent = document) => parent.querySelector(selector);
const state = { routes: [], route: 'direct', busy: false, results: [], history: [] };
const examples = {
  simple: { route: 'auto', prompt: 'Explain why the sky is blue in one sentence.' },
  reasoning: { route: 'auto', prompt: 'A fair coin is flipped until two heads appear in a row. Derive the expected number of flips, explain your reasoning, and check the result with a different method.' },
  coding: { route: 'coding', prompt: 'Write a Python function that merges overlapping intervals. Explain its time complexity and include tests for empty input, nested intervals, and touching boundaries.' }
};
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const shortModel = (model) => (model || '').split('/').slice(1).join('/').replace(':free', '') || model || 'Unknown';
const duration = (ms) => ms == null ? '—' : ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${Math.round(ms)} ms`;
const routeInfo = () => state.routes.find(route => route.id === state.route);
function errorMessage(body, status) {
  const error = body?.error;
  let message = typeof error === 'string' ? error : error?.message || error?.error?.message || `Request failed${status ? ` (HTTP ${status})` : ''}.`;
  if (status === 429) message += ' The free provider is rate limited. Wait before retrying.';
  return message;
}
async function api(path, options) {
  const response = await fetch(path, options);
  let body;
  try { body = await response.json(); } catch { throw new Error(`Unexpected server response (HTTP ${response.status}).`); }
  if (!response.ok) throw new Error(errorMessage(body, response.status));
  return body;
}
async function health() {
  $('#connection-label').textContent = 'Checking gateway…';
  try {
    await api('/api/health');
    $('#connection').className = 'connection online';
    $('#connection-label').textContent = 'Gateway connected';
  } catch {
    $('#connection').className = 'connection offline';
    $('#connection-label').textContent = 'Gateway unavailable';
  }
}
function setRoute(id) {
  const route = state.routes.find(route => route.id === id);
  if (!route) return;
  state.route = id;
  $('#routing-method').value = id;
  $$('#method-gallery button').forEach(button => { button.classList.toggle('active', button.dataset.method === id); button.setAttribute('aria-pressed', String(button.dataset.method === id)); });
  $('#active-route').textContent = route.label;
  $('#route-description').textContent = route.description;
  $('#general-model').textContent = route.general.model;
  $('#general-target small').textContent = route.routing_type === 'direct' ? 'Every request goes to this model' : route.routing_type === 'random' ? '70% configured sampling weight' : 'General-purpose candidate';
  $('#first-target-label').textContent = route.routing_type === 'direct' ? 'Fixed destination' : route.routing_type === 'random' ? 'Pool model A' : 'General purpose';
  $('#second-target-label').textContent = route.routing_type === 'random' ? 'Pool model B' : 'Specialist';
  $('#specialist-target').classList.toggle('hidden', !route.specialist);
  $('.target-branch').classList.toggle('hidden', !route.specialist);
  if (route.specialist) $('#specialist-model').textContent = route.specialist.model;
  $('#second-target-label').textContent = route.routing_type === 'custom' ? 'Other group targets' : $('#second-target-label').textContent;
  if (route.routing_type === 'custom') $('#specialist-model').textContent = route.candidates.slice(1).map(candidate => candidate.model).join(' · ');
  $('#general-target small').textContent = route.routing_type === 'advisor' ? 'Executor — the advisor reviews but does not serve' : $('#general-target small').textContent;
  $('#specialist-description').textContent = route.routing_type === 'random' ? '30% configured sampling weight' : 'For demanding reasoning tasks';
  $('#policy-label').textContent = route.policy;
  $('#judge-label').textContent = route.label;
  $('#judge-detail').textContent = route.judge ? shortModel(route.judge) : route.routing_type === 'direct' ? 'Fixed target · no judge call' : 'Weighted selection · no judge call';
  $('#general-target').classList.remove('is-selected');
  $('#specialist-target').classList.remove('is-selected');
  updateRequest();
}
function $$(selector, parent = document) { return [...parent.querySelectorAll(selector)]; }
function updateRequest() {
  const prompt = $('#prompt').value;
  $('#character-count').textContent = `${prompt.length.toLocaleString()} / 16,000 characters`;
  $('#run').disabled = state.busy || !prompt.trim() || !state.routes.length;
  $('#compare').disabled = state.busy || !prompt.trim() || state.routes.length < 2;
  $$('#method-gallery button, #routing-method, #mode, #max-tokens, #session-id, #new-session, [data-example]').forEach(element => element.disabled = state.busy);
  const request = { model: state.route, messages: [{ role: 'user', content: prompt }], max_tokens: Number($('#max-tokens').value), stream: false };
  $('#request-json pre').textContent = JSON.stringify($('#mode').value === 'preview' ? { input_format: 'openai_chat', request } : request, null, 2);
  $('#run-hint').textContent = $('#mode').value === 'preview' ? (routeInfo()?.preview_runs_completion ? 'Advisor preview may generate and review an executor answer. Preview is not inference-free.' : 'Preview selects only. Classifiers call a judge; direct and random do not.') : '⌘ / Ctrl + Enter to run · Compare sends seven independent requests, including executor/review calls.';
}
function selectView(view) {
  $$('.view').forEach(element => element.classList.toggle('hidden', element.id !== `view-${view}`));
  $$('.nav-item').forEach(element => element.classList.toggle('active', element.dataset.view === view));
  $('#page-name').textContent = { playground: 'Playground', routes: 'Route explorer', history: 'Request history' }[view];
}
function renderRoutes() {
  $('#routing-method').innerHTML = state.routes.map(route => `<option value="${esc(route.id)}">${esc(route.label)}</option>`).join('');
  const symbols = {custom:'{↗}',session:'◷',advisor:'✓',direct:'→',random:'⤨',system_one:'⑂',llm:'{ }'};
  $('#method-gallery').innerHTML = state.routes.map(route => `<button class="method-card" data-method="${esc(route.id)}" aria-pressed="false"><span class="method-symbol">${symbols[route.routing_type] || '⑂'}</span><strong>${esc(route.label)}</strong><small>${esc(route.description)}</small></button>`).join('');
  $$('[data-method]').forEach(button => button.onclick = () => setRoute(button.dataset.method));
  $('#route-count').textContent = state.routes.length;
  $('#route-cards').innerHTML = state.routes.map(route => `<article class="panel explorer-card"><div class="eyebrow">RUNNABLE NATIVE METHOD</div><h2>${esc(route.label)}</h2><p>${esc(route.description)}</p>${route.candidates.map(candidate => `<div class="target-card"><span class="target-dot general-dot"></span><div><div class="target-heading">${esc(candidate.name)}</div><strong>${esc(candidate.model)}</strong></div></div>`).join('')}<p>${route.judge ? `Judge: <code>${esc(route.judge)}</code>` : 'No classifier call'}<br>Policy: <strong>${esc(route.policy)}</strong></p><button class="secondary-button" data-use-route="${esc(route.id)}">Try this method →</button></article>`).join('');
  $('#advanced-cards').innerHTML = (state.advanced || []).map(method => `<article class="panel explorer-card advanced-card"><span class="neutral-label">Not configured</span><h2>${esc(method.label)}</h2><p>${esc(method.description)}</p></article>`).join('');
  $$('[data-use-route]').forEach(button => button.onclick = () => { setRoute(button.dataset.useRoute); selectView('playground'); $('#prompt').focus(); });
}
function renderDecision(result) {
  const decision = result.routing_decision;
  if (!decision) return '';
  const target = decision.selected_label || (decision.selected_tier === 'general' ? 'General purpose' : decision.selected_tier === 'specialist' ? 'Specialist' : 'Reported target');
  return `<section class="decision-card"><div class="decision-heading"><h3>Routing decision</h3><span class="route-tag">${esc(decision.classifier_label)}</span></div><div class="decision-outcome">${esc(target)} selected <span>→</span> <strong>${esc(shortModel(decision.selected_model))}</strong></div><dl><dt>Judge / classifier</dt><dd>${esc(decision.judge || "None — local routing policy")}</dd><dt>Candidates</dt><dd>${decision.candidates.map(candidate => esc(candidate.model)).join('<br>')}</dd><dt>Configured policy</dt><dd>${esc(decision.configured_policy)}</dd><dt>Session</dt><dd>${esc(decision.session_id || "Not reported")}</dd><dt>Decision source</dt><dd>${esc(decision.source)}</dd></dl><p>Selection is reported by Switchyard. ${decision.judge ? "The judge’s score, raw verdict, and rationale are not exposed by this version; selection alone does not establish verdict validity." : "This method makes no content-based judgement. The configured policy determines the destination."}</p></section>`;
}
function renderResult(result) {
  if (result.error) return `<article class="result-card"><div class="result-route">${esc(result.route)}</div><div class="error-box"><strong>Request could not complete</strong>${esc(result.error)}</div></article>`;
  const data = result.data;
  const selected = result.selected_model || data.selected?.model || data.model || 'Not reported';
  const usage = data.usage;
  const message = data.choices?.[0]?.message;
  let content = message?.content;
  if (Array.isArray(content)) content = content.map(part => part.text || '').join('');
  const note = result.mode === 'preview' && result.routing_decision?.preview_runs_completion ? `<div class="preview-note">Advisor preview runs executor/reviewer work during routing. ${data.response ? 'A buffered answer is included in the raw response.' : 'Check the raw response for the routing result.'}</div>` : result.mode === 'preview' ? `<div class="preview-note">Switchyard selected <strong>${esc(shortModel(selected))}</strong>. Preview stopped before the completion call; no answer was generated.</div>` : `<div class="answer">${esc(content || (message?.tool_calls?.length ? 'The model returned tool calls. Inspect the raw response below.' : 'The provider returned no answer text. Reasoning or a token limit may have consumed the output budget. Inspect the raw response.'))}</div>`;
  return `<article class="result-card"><div class="result-summary"><div><span class="result-route">${esc(result.route)}</span><div class="result-model">${esc(selected)}</div></div><span class="outline-badge"><span class="green-dot"></span>${result.mode === 'preview' ? 'Route preview' : 'Request completed'}</span></div><div class="metric-row"><div><small>TOTAL LATENCY</small><strong>${duration(result.latency_ms)}</strong></div><div><small>INPUT TOKENS</small><strong>${esc(usage?.prompt_tokens ?? '—')}</strong></div><div><small>OUTPUT TOKENS</small><strong>${esc(usage?.completion_tokens ?? '—')}</strong></div><div><small>FINISH REASON</small><strong>${esc(data.choices?.[0]?.finish_reason || '—')}</strong></div></div>${renderDecision(result)}${note}<details><summary>Inspect raw response</summary><pre>${esc(JSON.stringify(data, null, 2))}</pre></details></article>`;
}
function renderHistory() {
  $('#history-count').textContent = state.history.length;
  $('#history-list').innerHTML = state.history.length ? state.history.map((result, index) => `<div class="history-item"><div><span class="result-route">${esc(result.route)}</span><p>${esc(result.prompt.slice(0, 180))}</p><small>${esc(result.error ? 'Failed' : result.selected_model || result.data?.selected?.model || result.data?.model || 'Completed')} · ${duration(result.latency_ms)} · ${esc(result.mode)}</small></div><button class="quiet-button" data-history="${index}">View result ↗</button></div>`).join('') : '<div class="history-empty">No requests yet. Run a prompt in the playground to get started.</div>';
  $$('[data-history]').forEach(button => button.onclick = () => {
    const result = state.history[Number(button.dataset.history)];
    $('#prompt').value = result.prompt;
    setRoute(result.route);
    $('#mode').value = result.mode;
    state.results = [result];
    $('#results').innerHTML = renderResult(result);
    $('#result-state').textContent = 'From history';
    selectView('playground');
    updateRequest();
    updateSelected([result]);
    $('#copy-response').classList.toggle('hidden', !!result.error);
  });
}
function updateSelected(results) {
  $('#general-target').classList.remove('is-selected'); $('#specialist-target').classList.remove('is-selected');
  $('#destination-node').classList.remove('selected');
  const valid = results.filter(result => !result.error);
  if (valid.length === 1) {
    const result = valid[0];
    const model = result.selected_model || result.data?.selected?.model || result.data?.model;
    const route = routeInfo();
    $('#flow-destination').textContent = shortModel(model);
    $('#flow-detail').textContent = 'Selected by Switchyard';
    $('#destination-node').classList.add('selected');
    if (route?.general.model === model) $('#general-target').classList.add('is-selected');
    if (route?.specialist?.model === model) $('#specialist-target').classList.add('is-selected');
  } else {
    $('#flow-destination').textContent = valid.length > 1 ? 'Methods compared' : 'Best-fit model';
    $('#flow-detail').textContent = valid.length > 1 ? 'See each result below' : 'General purpose or specialist';
  }
}
async function run(compare = false) {
  if (state.busy || !$('#prompt').value.trim() || !state.routes.length) return;
  const prompt = $('#prompt').value.trim();
  const mode = $('#mode').value;
  const routeIds = compare ? state.routes.map(route => route.id) : [state.route];
  state.busy = true;
  updateRequest();
  $('#run').textContent = 'Running…';
  $('#response-panel').setAttribute('aria-busy', 'true');
  $('#result-state').textContent = 'In progress';
  $('#copy-response').classList.add('hidden');
  $('.pipeline').classList.add('running');
  updateSelected([]);
  $('#results').innerHTML = `<div class="loading"><span class="spinner"></span><div>Waiting for Switchyard…<small>${compare ? `${routeIds.length} requests in parallel` : mode === 'preview' ? (routeInfo()?.preview_runs_completion ? 'Running executor and advisor work for the routing preview' : 'Applying the routing policy without generating an answer') : 'Applying the routing policy and generating an answer'}. Free providers may take a moment.</small></div></div>`;
  const results = await Promise.all(routeIds.map(async route => {
    const start = performance.now();
    try {
      const response = await api('/api/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ route, prompt, mode, session_id: $('#session-id').value.trim(), max_tokens: Number($('#max-tokens').value) }) });
      return { ...response, prompt, route, mode, browser_latency_ms: Math.round(performance.now() - start) };
    } catch (error) { return { error: error.message || 'Network request failed', prompt, route, mode, latency_ms: Math.round(performance.now() - start) }; }
  }));
  state.results = results;
  state.history.unshift(...results);
  state.history = state.history.slice(0, 50);
  $('#results').innerHTML = results.map(renderResult).join('');
  $('#result-state').textContent = results.every(result => result.error) ? 'Failed' : results.some(result => result.error) ? 'Partial result' : 'Complete';
  updateSelected(results);
  renderHistory();
  state.busy = false;
  $('.pipeline').classList.remove('running');
  $('#response-panel').setAttribute('aria-busy', 'false');
  $('#run').innerHTML = 'Run request <span>↗</span>';
  $('#copy-response').classList.toggle('hidden', results.every(result => result.error));
  updateRequest();
}
const newSession = () => { $('#session-id').value = `lab-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,8)}`; };
newSession();
$('#new-session').onclick = newSession;
$('#prompt').addEventListener('input', updateRequest);
$('#mode').onchange = updateRequest;
$('#routing-method').onchange = () => setRoute($('#routing-method').value);
$('#max-tokens').onchange = updateRequest;
$('#clear-prompt').onclick = () => { $('#prompt').value = ''; updateRequest(); $('#prompt').focus(); };
$$('[data-example]').forEach(button => button.onclick = () => { const example = examples[button.dataset.example]; $('#prompt').value = example.prompt; updateRequest(); $('#prompt').focus(); });
$('#run').onclick = () => run();
$('#compare').onclick = () => run(true);
$('#connection').onclick = health;
$('#raw-toggle').onclick = () => { $('#request-json').classList.toggle('hidden'); updateRequest(); };
$$('[data-view]').forEach(button => button.onclick = () => selectView(button.dataset.view));
$('#explore-routes').onclick = () => selectView('routes');
$('#clear-history').onclick = () => { state.history = []; renderHistory(); };
$('#guide-button').onclick = () => $('#guide').showModal();
$('#close-guide').onclick = () => $('#guide').close();
$('#guide').onclick = event => { if (event.target === $('#guide')) $('#guide').close(); };
$('#copy-response').onclick = async () => {
  const text = state.results.filter(result => !result.error).map(result => result.data.choices?.[0]?.message?.content || JSON.stringify(result.data, null, 2)).join('\n\n');
  try { await navigator.clipboard.writeText(text); $('#copy-response').textContent = 'Copied'; setTimeout(() => $('#copy-response').textContent = 'Copy response', 1500); }
  catch { $('#copy-response').textContent = 'Use raw response to copy'; }
};
document.addEventListener('keydown', event => { if ((event.metaKey || event.ctrlKey) && event.key === 'Enter' && !$('#view-playground').classList.contains('hidden')) { event.preventDefault(); run(); } });
async function init() {
  renderHistory();
  health();
  try { const config = await api('/api/config'); state.routes = config.routes; state.advanced = config.advanced_methods; renderRoutes(); setRoute(state.routes[0]?.id); updateRequest(); }
  catch (error) { $('#results').innerHTML = `<div class="error-box"><strong>Could not load routing configuration</strong>${esc(error.message)}</div>`; }
}
init();
