const $ = (id) => document.getElementById(id);
let periods = [];
let selectedIndex = -1;

function money(value) {
  return value == null ? '—' : Number(value).toLocaleString('zh-CN', {maximumFractionDigits: 2});
}
function percent(value) { return value == null ? '—' : `${Number(value).toFixed(2)}%`; }
function escapeHTML(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
}
function showNotice(message) { $('notice').textContent = message; $('notice').classList.remove('hidden'); }
function clearNotice() { $('notice').classList.add('hidden'); }
function asTimestamp(value) { return value.length === 16 ? `${value}:00` : value; }

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
    input.min = periods[0].slice(0, 16);
    input.max = periods[periods.length - 1].slice(0, 16);
    if (!input.value || selectedIndex < 0) input.value = periods[periods.length - 1].slice(0, 16);
    selectedIndex = periods.indexOf(`${input.value}:00`);
    if (selectedIndex < 0) selectedIndex = periods.length - 1;
    await loadRanking();
  }
  $('health').textContent = `已载入 ${periods.length.toLocaleString()} 个小时点`;
}

async function loadRanking() {
  if (!periods.length) return;
  const inputValue = $('timestamp').value;
  if (!inputValue) return showNotice('请选择观察时点');
  const timestamp = asTimestamp(inputValue);
  selectedIndex = periods.findIndex(period => period >= timestamp);
  if (selectedIndex < 0) selectedIndex = periods.length - 1;
  const topK = Math.max(1, Number($('topK').value) || 10);
  clearNotice();
  try {
    const strategy = encodeURIComponent($('strategy').value || 'sar_long');
    const data = await getJSON(`/api/rankings?strategy=${strategy}&timestamp=${encodeURIComponent(timestamp)}&top_k=${topK}`);
    render(data);
  } catch (error) { showNotice(error.message); }
}

function render(data) {
  const priceMode = data.ranking_mode === 'price';
  $('bestLabel').textContent = priceMode ? '榜首五日价格涨幅' : '榜首五日保证金收益率';
  $('subtitle').textContent = priceMode
    ? '按各合约在该观察时点前五个交易日的价格涨幅排序。'
    : '按各品种前五个交易日净盈亏除以五日前一手保证金的收益率排序。';
  $('rankingTitle').textContent = priceMode ? '纯价格近五日涨幅排名' : '策略近五日保证金收益率排名';
  $('startValueHeading').textContent = priceMode ? '五日前价格' : '五日前一手保证金';
  $('returnRateHeading').textContent = priceMode ? '五日价格涨幅' : '五日保证金收益率';
  $('timestamp').value = data.timestamp.slice(0, 16);
  $('asOf').textContent = data.timestamp.replace('T', ' ');
  $('total').textContent = data.total;
  $('best').textContent = data.items.length ? percent(data.items[0].return_rate) : '—';
  $('updated').textContent = `${data.total} 个品种 · Top ${data.top_k}`;

  const body = $('rows');
  body.innerHTML = '';
  data.items.forEach(item => {
    const tr = document.createElement('tr');
    tr.className = `ranking-row${item.in_top_k ? ' top' : ''}`;
    tr.dataset.lookbackTimestamp = item.lookback_timestamp;
    tr.dataset.dataTimestamp = item.data_time;
    const returnClass = item.return_rate >= 0 ? 'profit' : 'loss';
    const prefix = priceMode ? '' : '¥';
    const instrumentCell = priceMode
      ? `<strong>${escapeHTML(item.instrument)}</strong>`
      : `<button class="instrument-toggle" type="button" aria-expanded="false" data-instrument="${escapeHTML(item.instrument)}">${escapeHTML(item.instrument)} <span>＋</span></button>`;
    tr.innerHTML = `<td class="rank">${item.rank}${item.in_top_k ? ' ★' : ''}</td>
      <td>${instrumentCell}</td>
      <td>${escapeHTML(item.contract || '—')}</td>
      <td>${prefix}${money(priceMode ? item.starting_equity : item.starting_margin)}</td>
      <td>${prefix}${money(item.ending_equity ?? item.equity)}</td>
      <td class="${returnClass}">${prefix}${money(item.return_amount)}</td>
      <td class="${returnClass}">${percent(item.return_rate)}</td>
      <td>${item.lookback_timestamp.replace('T', ' ')}</td>
      <td>${item.data_time.replace('T', ' ')}${item.stale ? ' ⚠' : ''}</td>`;
    body.appendChild(tr);
    if (!priceMode) {
      const detail = document.createElement('tr');
      detail.className = 'trade-detail hidden';
      detail.innerHTML = '<td colspan="9"><div class="trade-detail-content"></div></td>';
      body.appendChild(detail);
      tr.querySelector('.instrument-toggle').addEventListener('click', () => toggleTradeDetails(tr, detail));
    }
  });

  const bars = $('bars');
  bars.innerHTML = '';
  const top = data.items.slice(0, Math.min(20, data.items.length));
  const max = Math.max(...top.map(item => Math.abs(item.return_rate)), 0.01);
  top.forEach(item => {
    const value = item.return_rate;
    const wrapper = document.createElement('div');
    wrapper.className = `bar-item ${value >= 0 ? 'positive' : 'negative'}`;
    const height = Math.max(4, Math.round(Math.abs(value) / max * 68));
    const title = `${item.instrument} ${percent(value)}`;
    wrapper.innerHTML = `<div title="${escapeHTML(title)}" class="bar" style="height:${height}px"></div><span>${escapeHTML(item.instrument.slice(0,5))}</span>`;
    bars.appendChild(wrapper);
  });
}

async function toggleTradeDetails(row, detailRow) {
  const button = row.querySelector('.instrument-toggle');
  const content = detailRow.querySelector('.trade-detail-content');
  const isOpen = button.getAttribute('aria-expanded') === 'true';
  if (isOpen) {
    button.setAttribute('aria-expanded', 'false');
    button.querySelector('span').textContent = '＋';
    detailRow.classList.add('hidden');
    return;
  }
  button.setAttribute('aria-expanded', 'true');
  button.querySelector('span').textContent = '－';
  detailRow.classList.remove('hidden');
  if (content.dataset.loaded === 'true') return;
  content.innerHTML = '<div class="trade-loading">正在读取近五个交易日的成交信号…</div>';
  const instrument = button.dataset.instrument;
  const params = new URLSearchParams({
    strategy: $('strategy').value,
    start_timestamp: row.dataset.lookbackTimestamp,
    end_timestamp: row.dataset.dataTimestamp,
  });
  try {
    const data = await getJSON(`/api/contracts/${encodeURIComponent(instrument)}/trades?${params}`);
    content.dataset.loaded = 'true';
    if (!data.items.length) {
      content.innerHTML = '<div class="trade-empty">近五个交易日内没有买入或卖出信号。</div>';
      return;
    }
    content.innerHTML = `<div class="trade-detail-heading">${escapeHTML(instrument)} · ${data.total} 笔交易信号</div>
      <div class="trade-table-wrap"><table class="trade-table"><thead><tr><th>时间</th><th>操作</th><th>合约</th><th>价格</th><th>手数</th><th>成交额</th><th>手续费</th><th>平仓盈亏</th><th>权益</th></tr></thead><tbody>${data.items.map(trade => {
        const pnlClass = (trade.realized_pnl ?? 0) >= 0 ? 'profit' : 'loss';
        return `<tr><td>${escapeHTML(trade.timestamp.replace('T', ' '))}</td><td class="${trade.action.includes('买入') ? 'profit' : 'loss'}">${escapeHTML(trade.action)}</td><td>${escapeHTML(trade.contract || '—')}</td><td>${money(trade.price)}</td><td>${money(trade.volume)}</td><td>¥${money(trade.turnover)}</td><td>¥${money(trade.fee)}</td><td class="${pnlClass}">¥${money(trade.realized_pnl)}</td><td>¥${money(trade.equity)}</td></tr>`;
      }).join('')}</tbody></table></div>`;
  } catch (error) {
    content.innerHTML = `<div class="trade-error">交易明细加载失败：${escapeHTML(error.message)} <button class="trade-retry" type="button">重试</button></div>`;
    content.querySelector('.trade-retry').addEventListener('click', () => {
      delete content.dataset.loaded;
      toggleTradeDetails(row, detailRow);
    });
  }
}

$('timestamp').addEventListener('change', loadRanking);
$('refresh').addEventListener('click', loadRanking);
$('topK').addEventListener('change', loadRanking);
$('prev').addEventListener('click', () => {
  if (selectedIndex > 0) {
    selectedIndex -= 1;
    $('timestamp').value = periods[selectedIndex].slice(0, 16);
    loadRanking();
  }
});
$('next').addEventListener('click', () => {
  if (selectedIndex < periods.length - 1) {
    selectedIndex += 1;
    $('timestamp').value = periods[selectedIndex].slice(0, 16);
    loadRanking();
  }
});
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
