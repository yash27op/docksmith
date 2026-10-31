let output = null;
let active = 'dockerfile';
const $ = id => document.getElementById(id);
function showFile() { $('code').textContent = output[active]; }
async function request(path, body) {
  const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  if (!response.ok) { const error = await response.json(); throw new Error(error.error || 'Request failed'); }
  return response;
}
async function generate(demo) {
  $('generate').disabled = $('demo').disabled = true;
  $('result').hidden = true;
  output = null;
  $('source').textContent = demo ? 'STATIC DEMO' : 'LOCAL INFERENCE';
  $('status').textContent = demo ? 'Loading example…' : 'Generating locally… This can take up to three minutes on CPU.';
  try {
    output = await (await request(demo ? '/api/demo' : '/api/generate', {description:$('description').value,manifest:$('manifest').value})).json();
    $('source').textContent = output.demo ? 'STATIC DEMO' : 'OLLAMA';
    $('status').textContent = output.model;
    $('warnings').replaceChildren();
    for (const warning of output.warnings) { const p = document.createElement('p'); p.textContent = warning; $('warnings').append(p); }
    if (!output.warnings.length) { const p = document.createElement('p'); p.textContent = 'No issues found by basic heuristic checks. Build validation has not been performed.'; $('warnings').append(p); }
    showFile(); $('result').hidden = false;
  } catch (error) { $('status').textContent = error.message; }
  finally { $('generate').disabled = $('demo').disabled = false; }
}
$('form').addEventListener('submit', event => { event.preventDefault(); generate(false); });
$('demo').addEventListener('click', () => generate(true));
document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => {
  active = button.dataset.tab;
  document.querySelectorAll('[data-tab]').forEach(b => b.setAttribute('aria-pressed', String(b === button)));
  if (output) showFile();
}));
$('copy').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText(output[active]); $('status').textContent = 'Copied ' + active; }
  catch { $('status').textContent = 'Clipboard unavailable. Select and copy the file text.'; }
});
$('download').addEventListener('click', async () => {
  try {
    const blob = await (await request('/api/download', output)).blob();
    const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = 'docksmith.zip'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { $('status').textContent = error.message; }
});
