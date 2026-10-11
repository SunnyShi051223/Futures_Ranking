const $ = (id) => document.getElementById(id);
let periods = [];
let selectedIndex = -1;

function money(value) { return value == null ? '—' : Number(value).toLocaleString('zh-CN', {maximumFractionDigits: 2}); }
function percent(value) { return value == null ? '—' : `${Number(value).toFixed(2)}%`; }
function showNotice(message) { $('notice').textContent = message; $('notice').classList.remove('hidden'); }
function clearNotice() { $('notice').classList.add('hidden'); }

async function getJSON(url) {
  const response = await fetch(url);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '请求失败');
  return data;
}

async function loadPeriods() {
  const strategy = $('strategy').value || 'sar_long';
  const data = await getJSON(`/api/periods?strategy=${encodeURIComponent(strategy)}&limit=20000`);
  periods = data.items || [];
  const select = $('timestamp'); select.innerHTML = '';
  periods.forEach((period, index) => { const option = new Option(period.replace('T', ' '), period); option.dataset.index = index; select.appendChild(option); });
  if (periods.length) { selectedIndex = periods.length - 1; select.value = periods[selectedIndex]; await loadRanking(); }
  $('health').textContent = `已载入 ${periods.length.toLocaleString()} 个小时点`;
}

async function loadRanking() {
  if (!periods.length) return;
  selectedIndex = periods.indexOf($('timestamp').value);
  if (selectedIndex < 0) selectedIndex = periods.length - 1;
  const topK = Math.max(1, Number($('topK').value) || 10);
  clearNotice();
  try {
    const strategy = encodeURIComponent($('strategy').value || 'sar_long');
    const data = await getJSON(`/api/rankings?strategy=${strategy}&timestamp=${encodeURIComponent(periods[selectedIndex])}&top_k=${topK}`);
    render(data);
  } catch (error) { showNotice(error.message); }
}

function render(data) {
  $('timestamp').value = data.timestamp; $('asOf').textContent = data.timestamp.replace('T', ' '); $('total').textContent = data.total; $('capital').textContent = `¥${money(data.initial_capital)}`;
  $('best').textContent = data.items.length ? percent(data.items[0].return_rate) : '—'; $('updated').textContent = `${data.total} 个品种 · Top ${data.top_k}`;
  const body = $('rows'); body.innerHTML = '';
  data.items.forEach(item => {
    const tr = document.createElement('tr'); if (item.in_top_k) tr.className = 'top';
    const returnClass = item.return_rate >= 0 ? 'profit' : 'loss';
    tr.innerHTML = `<td class="rank">${item.rank}${item.in_top_k ? ' ★' : ''}</td><td><strong>${item.instrument}</strong></td><td>${item.contract || '—'}</td><td>¥${money(item.equity)}</td><td class="${returnClass}">¥${money(item.return_amount)}</td><td class="${returnClass}">${percent(item.return_rate)}</td><td>${money(item.price)}</td><td>${item.data_time.replace('T', ' ')}${item.stale ? ' ⚠' : ''}</td>`;
    body.appendChild(tr);
  });
  const bars = $('bars'); bars.innerHTML = ''; const top = data.items.slice(0, Math.min(20, data.items.length)); const max = Math.max(...top.map(item => Math.abs(item.return_rate)), 1);
  top.forEach(item => { const wrapper = document.createElement('div'); wrapper.className = 'bar-item'; const height = Math.max(4, Math.round(Math.abs(item.return_rate) / max * 68)); wrapper.innerHTML = `<div title="${item.instrument} ${percent(item.return_rate)}" class="bar" style="height:${height}px"></div><span>${item.instrument.slice(0,5)}</span>`; bars.appendChild(wrapper); });
}

$('timestamp').addEventListener('change', loadRanking); $('refresh').addEventListener('click', loadRanking);
$('prev').addEventListener('click', () => { if (selectedIndex > 0) { selectedIndex -= 1; $('timestamp').value = periods[selectedIndex]; loadRanking(); } });
$('next').addEventListener('click', () => { if (selectedIndex < periods.length - 1) { selectedIndex += 1; $('timestamp').value = periods[selectedIndex]; loadRanking(); } });
$('strategy').addEventListener('change', () => {
  selectedIndex = -1;
  loadPeriods().catch(error => showNotice(`数据加载失败：${error.message}`));
});

async function init() {
  const response = await getJSON('/api/strategies');
  $('strategy').replaceChildren(...response.items.map(item => new Option(item.name, item.id)));
  await loadPeriods();
}

init().catch(error => showNotice(`数据加载失败：${error.message}`));
