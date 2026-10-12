const $ = (id) => document.getElementById(id);
let periods = [];
let selectedIndex = -1;

function money(value) { return value == null ? '—' : Number(value).toLocaleString('zh-CN', {maximumFractionDigits: 2}); }
function percent(value) { return value == null ? '—' : `${Number(value).toFixed(2)}%`; }
function escapeHTML(value) { return String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char])); }
function showNotice(message) { $('notice').textContent = message; $('notice').classList.remove('hidden'); }
function clearNotice() { $('notice').classList.add('hidden'); }

async function getJSON(url) {
  const response = await fetch(url);
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) {
    throw new Error(response.ok ? '服务器返回了非 JSON 数据' : `接口暂时不可用（HTTP ${response.status}）`);
  }
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '请求失败');
  return data;
}

async function loadPeriods() {
  const strategy = $('strategy').value || 'sar_long';
  const data = await getJSON(`/api/periods?strategy=${encodeURIComponent(strategy)}&limit=20000`);
  periods = data.items || [];
  const input = $('timestamp');
  if (periods.length) {
    $('startTimestamp').min = periods[0].slice(0, 16);
    $('startTimestamp').max = periods[periods.length - 1].slice(0, 16);
    input.min = periods[0].slice(0, 16);
    input.max = periods[periods.length - 1].slice(0, 16);
    if (!input.value || selectedIndex < 0) input.value = periods[periods.length - 1].slice(0, 16);
    if (!$('startTimestamp').value) $('startTimestamp').value = periods[0].slice(0, 16);
    selectedIndex = periods.indexOf(`${input.value}:00`);
    if (selectedIndex < 0) selectedIndex = periods.length - 1;
    await loadRanking();
  }
  $('health').textContent = `已载入 ${periods.length.toLocaleString()} 个小时点`;
}

async function loadRanking() {
  if (!periods.length) return;
  const inputValue = $('timestamp').value;
  const startValue = $('startTimestamp').value;
  if (!inputValue || !startValue) return showNotice('请选择起始和结束观察时点');
  const timestamp = inputValue.length === 16 ? `${inputValue}:00` : inputValue;
  const startTimestamp = startValue.length === 16 ? `${startValue}:00` : startValue;
  if (startTimestamp >= timestamp) return showNotice('起始观察时点必须早于结束观察时点');
  selectedIndex = periods.findIndex(period => period >= timestamp);
  if (selectedIndex < 0) selectedIndex = periods.length - 1;
  const topK = Math.max(1, Number($('topK').value) || 10);
  clearNotice();
  try {
    const strategy = encodeURIComponent($('strategy').value || 'sar_long');
    const data = await getJSON(`/api/rankings?strategy=${strategy}&timestamp=${encodeURIComponent(timestamp)}&start_timestamp=${encodeURIComponent(startTimestamp)}&top_k=${topK}`);
    render(data);
  } catch (error) { showNotice(error.message); }
}

function render(data) {
  const priceMode = data.ranking_mode === 'price';
  $('bestLabel').textContent = priceMode ? '榜首价格涨跌幅' : '榜首区间收益';
  $('subtitle').textContent = priceMode ? '按各合约起止价格的区间涨跌幅排序，不使用策略权益。' : '按所选策略下各期货合约的区间收益金额排序。';
  $('rankingTitle').textContent = priceMode ? '纯价格涨跌幅排名' : '策略收益排名';
  $('capitalLabel').textContent = priceMode ? '排序口径' : '初始资金';
  $('capital').textContent = priceMode ? '纯价格' : `¥${money(data.initial_capital)}`;
  $('startValueLabel').textContent = priceMode ? '起始价格' : '起始权益';
  $('endValueLabel').textContent = priceMode ? '结束价格' : '结束权益';
  $('returnValueLabel').textContent = priceMode ? '价格涨跌' : '区间收益';
  $('returnRateLabel').textContent = priceMode ? '价格涨跌幅' : '区间收益率';
  $('startTimestamp').value = data.start_timestamp ? data.start_timestamp.slice(0, 16) : $('startTimestamp').value; $('timestamp').value = data.timestamp.slice(0, 16); $('asOf').textContent = `${data.start_timestamp ? data.start_timestamp.replace('T', ' ') : '起始'} 至 ${data.timestamp.replace('T', ' ')}`; $('total').textContent = data.total;
  if (!priceMode) $('capital').textContent = `¥${money(data.initial_capital)}`;
  $('best').textContent = data.items.length ? percent(data.items[0].return_rate) : '—'; $('updated').textContent = `${data.total} 个品种 · Top ${data.top_k}`;
  const body = $('rows'); body.innerHTML = '';
  data.items.forEach(item => {
    const tr = document.createElement('tr'); tr.className = `ranking-row${item.in_top_k ? ' top' : ''}`;
    const returnClass = item.return_rate >= 0 ? 'profit' : 'loss';
    const prefix = priceMode ? '' : '¥';
    const instrumentCell = priceMode ? `<strong>${escapeHTML(item.instrument)}</strong>` : `<button class="instrument-toggle" type="button" aria-expanded="false" data-instrument="${escapeHTML(item.instrument)}">${escapeHTML(item.instrument)} <span>＋</span></button>`;
    tr.innerHTML = `<td class="rank">${item.rank}${item.in_top_k ? ' ★' : ''}</td><td>${instrumentCell}</td><td>${escapeHTML(item.contract || '—')}</td><td>${prefix}${money(item.starting_equity)}</td><td>${prefix}${money(item.ending_equity ?? item.equity)}</td><td class="${returnClass}">${prefix}${money(item.return_amount)}</td><td class="${returnClass}">${percent(item.return_rate)}</td><td>${item.data_time.replace('T', ' ')}${item.stale ? ' ⚠' : ''}</td>`;
    body.appendChild(tr);
    if (!priceMode) {
      const detail = document.createElement('tr'); detail.className = 'trade-detail hidden';
      detail.innerHTML = '<td colspan="8"><div class="trade-detail-content"></div></td>';
      body.appendChild(detail);
      tr.querySelector('.instrument-toggle').addEventListener('click', () => toggleTradeDetails(tr, detail));
    }
  });
  const bars = $('bars'); bars.innerHTML = ''; const top = data.items.slice(0, Math.min(20, data.items.length)); const barValue = item => priceMode ? item.return_rate : item.return_amount; const max = Math.max(...top.map(item => Math.abs(barValue(item))), 1);
  top.forEach(item => { const value = barValue(item); const wrapper = document.createElement('div'); wrapper.className = 'bar-item'; const height = Math.max(4, Math.round(Math.abs(value) / max * 68)); const title = priceMode ? `${item.instrument} ${percent(value)}` : `${item.instrument} ¥${money(value)}`; wrapper.innerHTML = `<div title="${escapeHTML(title)}" class="bar" style="height:${height}px"></div><span>${escapeHTML(item.instrument.slice(0,5))}</span>`; bars.appendChild(wrapper); });
}

async function toggleTradeDetails(row, detailRow) {
  const button = row.querySelector('.instrument-toggle');
  const content = detailRow.querySelector('.trade-detail-content');
  const isOpen = button.getAttribute('aria-expanded') === 'true';
  if (isOpen) {
    button.setAttribute('aria-expanded', 'false'); button.querySelector('span').textContent = '＋';
    detailRow.classList.add('hidden'); return;
  }
  button.setAttribute('aria-expanded', 'true'); button.querySelector('span').textContent = '－';
  detailRow.classList.remove('hidden');
  if (content.dataset.loaded === 'true') return;
  content.innerHTML = '<div class="trade-loading">正在读取该区间的成交信号…</div>';
  const instrument = button.dataset.instrument;
  const params = new URLSearchParams({
    strategy: $('strategy').value,
    start_timestamp: `${$('startTimestamp').value}:00`,
    end_timestamp: `${$('timestamp').value}:00`,
  });
  try {
    const data = await getJSON(`/api/contracts/${encodeURIComponent(instrument)}/trades?${params}`);
    content.dataset.loaded = 'true';
    if (!data.items.length) {
      content.innerHTML = '<div class="trade-empty">所选区间内没有买入或卖出信号。</div>';
      return;
    }
    content.innerHTML = `<div class="trade-detail-heading">${escapeHTML(instrument)} · ${data.total} 笔交易信号</div>
      <div class="trade-table-wrap"><table class="trade-table"><thead><tr><th>时间</th><th>操作</th><th>合约</th><th>价格</th><th>手数</th><th>成交额</th><th>手续费</th><th>平仓盈亏</th><th>权益</th></tr></thead><tbody>${data.items.map(trade => {
        const pnlClass = (trade.realized_pnl ?? 0) >= 0 ? 'profit' : 'loss';
        return `<tr><td>${escapeHTML(trade.timestamp.replace('T', ' '))}</td><td class="${trade.action.includes('买入') ? 'profit' : 'loss'}">${escapeHTML(trade.action)}</td><td>${escapeHTML(trade.contract || '—')}</td><td>${money(trade.price)}</td><td>${money(trade.volume)}</td><td>¥${money(trade.turnover)}</td><td>¥${money(trade.fee)}</td><td class="${pnlClass}">¥${money(trade.realized_pnl)}</td><td>¥${money(trade.equity)}</td></tr>`;
      }).join('')}</tbody></table></div>`;
  } catch (error) {
    content.innerHTML = `<div class="trade-error">交易明细加载失败：${escapeHTML(error.message)} <button class="trade-retry" type="button">重试</button></div>`;
    content.querySelector('.trade-retry').addEventListener('click', () => { delete content.dataset.loaded; toggleTradeDetails(row, detailRow); });
  }
}

$('timestamp').addEventListener('change', loadRanking); $('refresh').addEventListener('click', loadRanking);
$('startTimestamp').addEventListener('change', loadRanking);
$('prev').addEventListener('click', () => { if (selectedIndex > 0) { selectedIndex -= 1; $('timestamp').value = periods[selectedIndex].slice(0, 16); loadRanking(); } });
$('next').addEventListener('click', () => { if (selectedIndex < periods.length - 1) { selectedIndex += 1; $('timestamp').value = periods[selectedIndex].slice(0, 16); loadRanking(); } });
$('strategy').addEventListener('change', () => {
  selectedIndex = -1;
  $('startTimestamp').value = '';
  loadPeriods().catch(error => showNotice(`数据加载失败：${error.message}`));
});

async function init() {
  const response = await getJSON('/api/strategies');
  $('strategy').replaceChildren(...response.items.map(item => new Option(item.name, item.id)));
  await loadPeriods();
}

init().catch(error => showNotice(`数据加载失败：${error.message}`));
