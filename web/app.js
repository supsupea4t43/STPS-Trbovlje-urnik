/* STPS Urnik - logika vmesnika (tedenski pogled) */
(() => {
  'use strict';

  const $ = (sel) => document.querySelector(sel);

  // Sirina stolpcev, iz katere izracunamo potrebno sirino okna.
  const HOUR_COL = 78;
  const DAY_COL = 150;
  const SIDE_PAD = 30;      // odmik glavnega dela + obroba okvirja

  const state = {
    meta: null,
    classId: null,
    week: 1,
    grid: null,
    busy: false,
    lastFit: null,
  };

  const STATUS_BADGE = {
    'nadomescanje': ['b-nad', 'NAD'],
    'zaposlitev': ['b-zap', 'ZAP'],
    'odpadla-ura': ['b-odp', 'ODP'],
    'ni-bilo-pouka': ['b-odp', 'ODP'],
    'dogodek': ['b-dog', 'DOG'],
  };
  const OFF = new Set(['odpadla-ura', 'ni-bilo-pouka']);

  const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  // ?datum=YYYY-MM-DD podtakne drug "danes" - za preverjanje vedenja ob koncu tedna.
  const FAKE_TODAY = new URLSearchParams(location.search).get('datum');
  const todayISO = () => FAKE_TODAY || iso(new Date());

  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  // Dan kot celo stevilo (prek UTC, da premik na poletni cas ne moti razlik).
  const dayNum = (isoStr) => {
    const [y, m, d] = isoStr.split('-').map(Number);
    return Date.UTC(y, m - 1, d) / 86400000;
  };

  /**
   * Teden, ki ga aplikacija steje za "zdaj". Cez vikend je to ze naslednji
   * teden - pouka tega tedna ni vec. Racunamo iz datumov prikazanega tedna,
   * zato je odgovor enak ne glede na to, kateri teden je trenutno odprt.
   */
  function homeWeek() {
    const fallback = state.meta?.currentWeek || 1;
    const monday = state.grid?.days?.[0]?.date;
    if (!monday) return fallback;

    const today = todayISO();
    let week = state.grid.week + Math.floor((dayNum(today) - dayNum(monday)) / 7);
    const dow = new Date(`${today}T00:00:00`).getDay();   // 0 = nedelja, 6 = sobota
    if (dow === 0 || dow === 6) week += 1;

    const last = state.meta?.weeks?.length || 53;
    return Math.min(Math.max(week, 1), last);
  }

  async function api(path, params = {}, fresh = false) {
    const q = new URLSearchParams(params);
    if (fresh) q.set('fresh', '1');
    let res;
    try {
      res = await fetch(`${path}?${q}`, { cache: 'no-store' });
    } catch {
      throw new Error('Program ni več dosegljiv — zapri to okno in znova odpri Urnik.');
    }
    const data = await res.json().catch(() => ({ error: 'Neveljaven odgovor.' }));
    if (!res.ok) throw new Error(data.error || `Napaka ${res.status}`);
    return data;
  }

  function showBanner(msg) {
    const el = $('#banner');
    if (!msg) { el.hidden = true; return; }
    el.textContent = msg;
    el.hidden = false;
  }

  function noteStale(meta) {
    if (meta && meta.stale) {
      showBanner(`Ni povezave (${meta.error || 'vir ni dosegljiv'}) — prikazan je zadnji shranjeni urnik.`);
    } else {
      showBanner('');
    }
  }

  // ------------------------------------------------- velikost okna

  /** Velikost, ki jo vsebina dejansko potrebuje (brez drsnikov). */
  function neededSize() {
    const days = state.grid?.days?.length || 5;
    const w = HOUR_COL + days * DAY_COL + SIDE_PAD;
    let h = 0;
    for (const el of [$('.bar'), $('main'), $('.legend')]) h += el.offsetHeight;
    const banner = $('#banner');
    if (!banner.hidden) h += banner.offsetHeight;
    return { w, h };
  }

  /**
   * Okno prilagodimo vsebini. resizeTo v nekaterih razlicicah ni dovoljen,
   * zato mero sporocimo se strezniku - ta jo uporabi ob naslednjem zagonu.
   */
  function fitWindow() {
    const need = neededSize();
    if (state.lastFit
        && Math.abs(state.lastFit.w - need.w) < 8
        && Math.abs(state.lastFit.h - need.h) < 8) return;
    state.lastFit = need;

    // Okvir okna je nekaj deset pik; ce meritev pove kaj drugega (npr. ker
    // stran ne tece v svojem oknu), je ne upostevamo.
    const clamp = (v, hi) => Math.min(Math.max(v, 0), hi);
    const dw = clamp(window.outerWidth - window.innerWidth, 40);
    const dh = clamp(window.outerHeight - window.innerHeight, 160);
    // screen.avail* je v nekaterih okoljih 0; takrat omejitve ne uporabimo.
    const maxW = screen.availWidth > 400 ? screen.availWidth : 4000;
    const maxH = screen.availHeight > 400 ? screen.availHeight : 4000;
    const w = Math.min(need.w + dw, maxW);
    const h = Math.min(need.h + dh, maxH);

    try { window.resizeTo(w, h); } catch { /* zavrnjeno, ostane za naslednjic */ }
    fetch(`/api/size?w=${Math.round(w)}&h=${Math.round(h)}`).catch(() => {});
  }

  // ------------------------------------------------- risanje

  function badge(status, groups) {
    const out = [];
    const b = STATUS_BADGE[status];
    if (b) out.push(`<i class="badge ${b[0]}">${b[1]}</i>`);
    if (groups > 1) out.push(`<i class="badge b-grp" title="Več skupin">${groups}</i>`);
    return out.join(' ');
  }

  /**
   * Zaporedne ure z enako vsebino zdruzimo v en zapis. Tako se dvourni bloki
   * in celodnevni dogodki (npr. "Počitnice") ne ponavljajo pri vsaki uri.
   */
  function runsFor(grid, date, hours) {
    const runs = [];
    let cur = null;
    for (const h of hours) {
      const blocks = grid.cells[`${date}|${h.n}`] || null;
      const sig = blocks ? JSON.stringify(blocks.map(
        (b) => [b.short, b.subject, b.sub, b.status, b.groups])) : null;
      if (cur && sig !== null && cur.sig === sig) { cur.hours.push(h); continue; }
      cur = { sig, blocks, hours: [h] };
      runs.push(cur);
    }
    return runs;
  }

  function renderWeek() {
    const grid = state.grid;
    const table = $('#grid');
    if (!grid) { table.innerHTML = ''; return; }

    $('#weekName').textContent = `Teden ${grid.week}`;
    $('#weekRange').textContent = `${grid.from} – ${grid.to}`;
    $('#weekToday').hidden = grid.week === homeWeek();

    // Nekateri oddelki (npr. kombinirani) urnika nimajo objavljenega.
    if (!grid.days.length || !grid.hours.length) {
      table.innerHTML = '<tbody><tr><td class="empty">Za ta teden ni objavljenega urnika.</td></tr></tbody>';
      fitWindow();
      setTimeout(fitWindow, 150);
      return;
    }

    // Prikazemo samo ure, ki v tem tednu sploh kaj vsebujejo.
    const used = grid.hours.filter((h) => grid.days.some((d) => grid.cells[`${d.date}|${h.n}`]));
    const hours = used.length ? used : grid.hours.slice(0, 8);
    const today = todayISO();

    const head = `<thead><tr><th class="h-cell"></th>${grid.days.map((d) => `
      <th class="${d.date === today ? 'is-today' : ''}">${esc(d.name)}<small>${esc(d.label)}</small></th>`).join('')}</tr></thead>`;

    // Za vsak dan vnaprej razporedimo zdruzene ure na vrstice (rowspan).
    const plan = {};
    for (const d of grid.days) {
      const slots = new Array(hours.length);
      let i = 0;
      for (const run of runsFor(grid, d.date, hours)) {
        slots[i] = { span: run.hours.length, blocks: run.blocks };
        for (let k = 1; k < run.hours.length; k++) slots[i + k] = null; // pokrito z rowspan
        i += run.hours.length;
      }
      plan[d.date] = slots;
    }

    const body = hours.map((h, idx) => `
      <tr>
        <th class="h-cell"><b>${esc(h.name)}</b><span>${esc(h.time)}</span></th>
        ${grid.days.map((d) => {
          const slot = plan[d.date][idx];
          if (slot === null) return '';
          const blocks = slot.blocks || [];
          const inner = blocks.map((b, i) => `
            <div class="blk ${b.status ? 's-' + b.status : ''} ${i ? 'alt' : ''} ${OFF.has(b.status) ? 'is-off' : ''}"
                 title="${esc(b.subject)}${b.teacher ? ' — ' + esc(b.teacher) : ''}${b.statusLabel ? ' (' + esc(b.statusLabel) + ')' : ''}">
              <div class="blk-top"><span class="blk-code">${esc(b.short)}</span>${badge(b.status, i === 0 ? b.groups : null)}</div>
              ${b.sub ? `<div class="blk-sub">${esc(b.sub)}</div>` : ''}
            </div>`).join('');
          return `<td rowspan="${slot.span}" class="${d.date === today ? 'col-today' : ''}"><div class="cell">${inner}</div></td>`;
        }).join('')}
      </tr>`).join('');

    table.innerHTML = head + `<tbody>${body}</tbody>`;
    fitWindow();
    setTimeout(fitWindow, 150);   // po prelomu besedila se visina lahko se spremeni
  }

  // ------------------------------------------------- nalaganje

  async function loadWeek(fresh = false) {
    if (state.busy) return;
    state.busy = true;
    try {
      const data = await api('/api/urnik', { class: state.classId, week: state.week }, fresh);
      state.grid = data;
      state.week = data.week;
      noteStale(data._meta);
      renderWeek();
    } catch (err) {
      showBanner(err.message);
    } finally {
      state.busy = false;
    }
  }

  function shiftWeek(delta) {
    const target = state.week + delta;
    if (target < 1 || target > (state.meta.weeks.length || 53)) return;
    state.week = target;
    loadWeek();
  }

  function goToday() {
    state.week = homeWeek();
    loadWeek();
  }

  function refresh() {
    loadWeek(true);
  }

  function wire() {
    $('#classSelect').addEventListener('change', (e) => {
      state.classId = e.target.value;
      // Izbiro si zapomni streznik - glej /api/prefs.
      fetch(`/api/prefs?class=${encodeURIComponent(state.classId)}`).catch(() => {});
      loadWeek();
    });
    $('#weekPrev').addEventListener('click', () => shiftWeek(-1));
    $('#weekNext').addEventListener('click', () => shiftWeek(1));
    $('#weekToday').addEventListener('click', goToday);

    document.addEventListener('keydown', (e) => {
      if (e.target.matches('input, select, textarea')) return;
      if (e.key === 'ArrowLeft') shiftWeek(-1);
      else if (e.key === 'ArrowRight') shiftWeek(1);
      else if (e.key.toLowerCase() === 't') goToday();
      else if (e.key.toLowerCase() === 'r' && !e.ctrlKey) refresh();
    });

    // Utrip: streznik se ugasne, ko okno ni vec odprto.
    setInterval(() => fetch('/api/ping').catch(() => {}), 20000);
    setInterval(() => { if (!document.hidden) refresh(); }, 5 * 60 * 1000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
    window.addEventListener('resize', () => { state.lastFit = null; });
  }

  // ------------------------------------------------- zagon

  async function boot() {
    try {
      const meta = await api('/api/meta');
      state.meta = meta;
      document.title = `Urnik — ${meta.schoolName}`;

      const saved = meta.prefs?.classId;
      state.classId = meta.classes.some((c) => c.id === saved) ? saved : meta.classes[0].id;
      $('#classSelect').innerHTML = meta.classes
        .map((c) => `<option value="${c.id}"${c.id === state.classId ? ' selected' : ''}>${esc(c.name)}</option>`).join('');

      state.week = meta.currentWeek;
      await loadWeek();
      // Sele iz nalozenega tedna poznamo datume; cez vikend to pomeni skok naprej.
      const home = homeWeek();
      if (home !== state.week) {
        state.week = home;
        await loadWeek();
      }
      wire();
    } catch (err) {
      showBanner('Urnika ni bilo mogoče naložiti: ' + err.message);
      $('#grid').innerHTML = '<tbody><tr><td class="empty">Ni podatkov. Preveri internetno povezavo, nato pritisni R.</td></tr></tbody>';
      document.addEventListener('keydown', (e) => {
        if (e.key.toLowerCase() === 'r') location.reload();
      });
    }
  }

  boot();
})();
