// Small DOM helpers keep the single-page event wiring compact.
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
// Cached browser state supports instant filtering without repeated API calls.
const state = { user: null, exceptions: [], audit: [] };

function updateClock() { const now = new Date(); $('#today-label').textContent = new Intl.DateTimeFormat(undefined, { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' }).format(now).toUpperCase(); $('#last-sync').textContent = `Current time ${new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(now)}`; }
updateClock();
setInterval(updateClock, 1000);

// Show short success or error feedback in the shared toast component.
function toast(message, error = false) { const element = $('#toast'); element.textContent = message; element.className = `toast show${error ? ' error' : ''}`; setTimeout(() => element.className = 'toast', 3200); }
async function api(path, options = {}) { const response = await fetch(path, options); const data = response.headers.get('content-type')?.includes('application/json') ? await response.json() : null; if (!response.ok) throw new Error(data?.error || 'Something went wrong.'); return data; }
function formData(form) { return Object.fromEntries(new FormData(form).entries()); }
function setUser(user) { state.user = user; $('#user-name').textContent = user.full_name; $('#user-role').textContent = user.role; $('#greeting-name').textContent = user.full_name.split(' ')[0]; $('#user-initials').textContent = user.full_name.split(' ').map(part => part[0]).join('').slice(0, 2).toUpperCase(); }
function showApp(user) { setUser(user); $('#auth-view').classList.add('hidden'); $('#app-view').classList.remove('hidden'); loadDashboard(); }
function showAuth() { $('#app-view').classList.add('hidden'); $('#auth-view').classList.remove('hidden'); }
// Switch views and load data only for sections that need server records.
function showSection(section) { $$('.page-section').forEach(item => item.classList.add('hidden')); $(`#section-${section}`).classList.remove('hidden'); $$('.nav-item').forEach(item => item.classList.toggle('active', item.dataset.section === section)); const titles = { overview: 'Control room', ingest: 'Data ingestion', exceptions: 'Exception desk', audit: 'Activity trail' }; $('#page-title').textContent = titles[section]; if (section === 'exceptions') loadExceptions(); if (section === 'audit') loadAudit(); }
async function loadDashboard() { try { const data = await api('/api/dashboard'); $('#kpi-ledger').textContent = data.ledger_total.toLocaleString(); $('#kpi-bank').textContent = data.bank_total.toLocaleString(); $('#kpi-rate').textContent = `${data.reconciliation_rate}%`; $('#kpi-unresolved').textContent = data.unresolved_total.toLocaleString(); $('#exception-count').textContent = data.unresolved_total; } catch (error) { toast(error.message, true); } }
function renderRun(summary) { const labels = { exact: 'Exact matches', many_to_one: 'Many-to-one', variance: 'Variance breaks', missing: 'Missing ledger', unknown: 'Unknown bank' }; $('#pipeline').innerHTML = `<div class="run-summary">${Object.entries(summary).map(([key, value]) => `<div><strong>${value}</strong><small>${labels[key]}</small></div>`).join('')}</div><a class="text-button report-link" href="/api/report">Download certified report ↓</a>`; }
// Apply search and status filters to the cached exception list, then rebuild the table.
function renderExceptions() { const query = $('#exception-search').value.toLowerCase().trim(); const filter = $('#exception-filter').value; const rows = state.exceptions.filter(row => { const matchesSearch = `${row.transaction_id} ${row.counterparty || ''}`.toLowerCase().includes(query); const matchesFilter = filter === 'all' || (row.recon_status || 'UNRESOLVED') === filter; return matchesSearch && matchesFilter; }); const wrapper = $('#exceptions-list'); $('#exception-result-count').textContent = `${rows.length} of ${state.exceptions.length} items`; if (!rows.length) { wrapper.innerHTML = '<div class="empty-state"><span>✓</span><p>No matching exceptions.</p><small>Try another search or filter.</small></div>'; return; } wrapper.innerHTML = `<table class="data-table"><thead><tr><th>Transaction</th><th>Date</th><th>Amount</th><th>Counterparty</th><th>Status</th><th>Decision</th><th></th></tr></thead><tbody>${rows.map(row => `<tr data-id="${row.transaction_id}"><td>${row.transaction_id}</td><td>${row.booking_date || '—'}</td><td>${Number(row.amount_cents).toLocaleString()}¢</td><td>${row.counterparty || '—'}</td><td><span class="badge status-${(row.recon_status || 'UNRESOLVED').toLowerCase()}">${row.recon_status || 'UNRESOLVED'}</span></td><td><select class="status-select"><option>UNDER_REVIEW</option><option>MANUALLY_APPROVED</option><option>MANUALLY_REJECTED</option></select><input class="reason-input" placeholder="Reason"></td><td><button class="mini-button save-exception">Save</button></td></tr>`).join('')}</tbody></table>`; $$('.save-exception').forEach(button => button.addEventListener('click', saveException)); }
async function loadExceptions() { try { state.exceptions = await api('/api/exceptions'); renderExceptions(); } catch (error) { toast(error.message, true); } }
async function saveException(event) { const row = event.target.closest('tr'); try { await api(`/api/exceptions/${encodeURIComponent(row.dataset.id)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: row.querySelector('.status-select').value, reason: row.querySelector('.reason-input').value }) }); toast('Exception decision saved.'); loadExceptions(); loadDashboard(); } catch (error) { toast(error.message, true); } }
async function loadAudit() { try { state.audit = await api('/api/audit'); $('#audit-list').innerHTML = state.audit.length ? `<table class="data-table"><thead><tr><th>Time</th><th>Operator</th><th>Action</th><th>Details</th></tr></thead><tbody>${state.audit.map(row => `<tr><td>${row.created_at}</td><td>${row.username}</td><td>${row.action}</td><td>${row.details || '—'}</td></tr>`).join('')}</tbody></table>` : '<div class="empty-state"><p>No activity recorded yet.</p></div>'; } catch (error) { toast(error.message, true); } }
setInterval(() => { if ($('.nav-item.active')?.dataset.section === 'audit') loadAudit(); }, 5000);
function downloadCsv(filename, rows) { if (!rows.length) return toast('There is no data to export.', true); const columns = Object.keys(rows[0]); const csv = [columns.join(','), ...rows.map(row => columns.map(column => `"${String(row[column] ?? '').replaceAll('"', '""')}"`).join(','))].join('\n'); const link = document.createElement('a'); link.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' })); link.download = filename; link.click(); URL.revokeObjectURL(link.href); }
$$('[data-auth]').forEach(button => button.addEventListener('click', () => { $$('.auth-tabs button').forEach(item => item.classList.remove('active')); button.classList.add('active'); $('#login-form').classList.toggle('hidden', button.dataset.auth !== 'login'); $('#register-form').classList.toggle('hidden', button.dataset.auth !== 'register'); $('#auth-error').textContent = ''; }));
$$('[data-action]').forEach(form => form.addEventListener('submit', async event => { event.preventDefault(); try { const action = form.dataset.action; const data = await api(`/api/auth/${action}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(formData(form)) }); if (action === 'login') showApp(data.user); else { toast(data.message); form.reset(); $('[data-auth="login"]').click(); } } catch (error) { $('#auth-error').textContent = error.message; } }));
$$('[data-section]').forEach(button => button.addEventListener('click', () => showSection(button.dataset.section))); $$('[data-section-target]').forEach(button => button.addEventListener('click', () => showSection(button.dataset.sectionTarget)));
$('#logout').addEventListener('click', async () => { await api('/api/auth/logout', { method: 'POST' }); showAuth(); });
[['ledger-file', 'ledger-file-name'], ['bank-file', 'bank-file-name']].forEach(([input, label]) => $(`#${input}`).addEventListener('change', event => { const file = event.target.files[0]; if (file) { $(`#${label}`).textContent = file.name; event.target.closest('.dropzone').classList.add('has-file'); } }));
$('#upload-button').addEventListener('click', async () => { const ledger = $('#ledger-file').files[0]; const bank = $('#bank-file').files[0]; if (!ledger || !bank) return toast('Choose both source files first.', true); const body = new FormData(); body.append('ledger', ledger); body.append('bank', bank); try { const data = await api('/api/upload', { method: 'POST', body }); toast(`${data.ledger_rows} ledger and ${data.bank_rows} bank rows staged.`); loadDashboard(); } catch (error) { toast(error.message, true); } });
$('#reconcile-button').addEventListener('click', async () => { const button = $('#reconcile-button'); button.disabled = true; button.firstChild.textContent = 'Processing... '; try { const data = await api('/api/reconcile', { method: 'POST' }); renderRun(data.summary); toast('Reconciliation complete.'); loadDashboard(); showSection('overview'); } catch (error) { toast(error.message, true); } finally { button.disabled = false; button.firstChild.textContent = 'Run engine '; } });
$('#refresh-button').addEventListener('click', async () => { const button = $('#refresh-button'); button.classList.add('spinning'); await loadDashboard(); const active = $('.nav-item.active')?.dataset.section; if (active === 'exceptions') await loadExceptions(); if (active === 'audit') await loadAudit(); button.classList.remove('spinning'); toast('Workspace refreshed.'); });
$('#exception-search').addEventListener('input', renderExceptions); $('#exception-filter').addEventListener('change', renderExceptions);
$('#export-exceptions').addEventListener('click', () => downloadCsv('finrecon-exceptions.csv', state.exceptions)); $('#export-audit').addEventListener('click', () => downloadCsv('finrecon-activity.csv', state.audit));

function initReconCore() {
	if (!window.THREE) return;
	const canvas = $('#recon-canvas');
	$('.core-fallback').classList.add('is-hidden');
	const host = canvas.parentElement;
	const scene = new THREE.Scene();
	const camera = new THREE.PerspectiveCamera(28, host.clientWidth / host.clientHeight, .1, 100);
	camera.position.set(0, 0, 5.4);
	const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
	renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
	renderer.setSize(host.clientWidth, host.clientHeight, false);
	const core = new THREE.Group();
	const shell = new THREE.Mesh(new THREE.IcosahedronGeometry(1.1, 2), new THREE.MeshBasicMaterial({ color: 0x2b765f, wireframe: true, transparent: true, opacity: .42 }));
	const inner = new THREE.Mesh(new THREE.IcosahedronGeometry(.74, 1), new THREE.MeshBasicMaterial({ color: 0xef713d, wireframe: true, transparent: true, opacity: .7 }));
	const ring = new THREE.Mesh(new THREE.TorusGeometry(1.42, .012, 8, 80), new THREE.MeshBasicMaterial({ color: 0xef713d, transparent: true, opacity: .5 }));
	ring.rotation.set(.8, .2, .3);
	core.add(shell, inner, ring);
	scene.add(core);
	const nodes = new THREE.Group();
	const nodeGeometry = new THREE.SphereGeometry(.045, 8, 8);
	for (let index = 0; index < 26; index += 1) {
		const angle = (index / 26) * Math.PI * 2;
		const radius = 1.65 + (index % 3) * .11;
		const node = new THREE.Mesh(nodeGeometry, new THREE.MeshBasicMaterial({ color: index % 4 === 0 ? 0xef713d : 0x2b765f }));
		node.position.set(Math.cos(angle) * radius, Math.sin(angle) * radius * .55, Math.sin(angle * 2) * .18);
		nodes.add(node);
	}
	scene.add(nodes);
	let pointerX = 0;
	let pointerY = 0;
	host.addEventListener('pointermove', event => { const bounds = host.getBoundingClientRect(); pointerX = (event.clientX - bounds.left) / bounds.width - .5; pointerY = (event.clientY - bounds.top) / bounds.height - .5; });
	const resize = () => { camera.aspect = host.clientWidth / host.clientHeight; camera.updateProjectionMatrix(); renderer.setSize(host.clientWidth, host.clientHeight, false); };
	window.addEventListener('resize', resize);
	const animate = () => { core.rotation.y += .003; core.rotation.x += .001; nodes.rotation.z -= .0015; core.rotation.y += (pointerX * .18 - core.rotation.y * .02) * .01; core.rotation.x += (pointerY * .12 - core.rotation.x * .02) * .01; renderer.render(scene, camera); requestAnimationFrame(animate); };
	animate();
}
initReconCore();
api('/api/session').then(data => data.user ? showApp(data.user) : showAuth()).catch(() => showAuth());