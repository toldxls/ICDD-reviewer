// Drives the GUI's Tables ▸ EPMA flows in jsdom against a live test server (tests/test_gui_js.py starts it).
//   node tests/js/tb_flows.mjs http://127.0.0.1:PORT
// Prints one JSON object: {flow: {ok, detail}}. Every flow is a state bug a review found in the page scripts, which no
// Python test reaches: a block / range / sheet picked for one file carried to the next, the sheet panel left on the last
// file, a typed sheet keeping a block number of the whole-file list, a folder switch keeping the hidden picks.
import { JSDOM } from 'jsdom';

const base = process.argv[2];
const sleep = ms => new Promise(r => setTimeout(r, ms));
const dom = await JSDOM.fromURL(base + '/', {
  runScripts: 'dangerously', resources: 'usable', pretendToBeVisual: true,
  beforeParse(w) {
    w.matchMedia = w.matchMedia || (() => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} }));
    w.ResizeObserver = w.ResizeObserver || class { observe() {} unobserve() {} disconnect() {} };
    w.navigator.sendBeacon = () => true;
    w.fetch = (u, o) => fetch(new URL(u, base).href, o);                   // node's fetch, relative URLs against the server
    w.scrollTo = () => {}; w.HTMLElement.prototype.scrollIntoView = function () {};
  },
});
const w = dom.window;
await new Promise(r => (w.document.readyState === 'complete' ? r() : w.addEventListener('load', r)));
await sleep(300);
const E = s => w.eval(s);
const opt = k => E(`tbOpt('epma', '${k}')`);
const out = {};
const check = (name, ok, detail) => { out[name] = { ok: !!ok, detail }; };

try {
  E("setMode('tables', { quiet: true })"); await E('tbLoad()'); await sleep(200);
  E("tbSetTab('epma')");

  // 1. another probe file from the sidebar starts from its own default: block, range and sheet cleared
  E("tbPickData('probe.csv', 'probe')");
  E("tbSetOpt('epma', 'block', '2'); tbSetOpt('epma', 'region', 'A1:C3'); tbSetOpt('epma', 'sheet', 'probe.csv')");
  E("tbPickData('probe2.csv', 'probe')");
  check('sidebar_file_change_clears_picks', opt('file') === 'probe2.csv' && opt('block') === '' && opt('region') === '' && opt('sheet') === '',
        { file: opt('file'), block: opt('block'), region: opt('region'), sheet: opt('sheet') });

  // 2. picking the SAME file again keeps the picks (only a change of file resets them)
  E("tbSetOpt('epma', 'block', '1')"); E("tbPickData('probe2.csv', 'probe')");
  check('same_file_keeps_picks', opt('block') === '1', { block: opt('block') });

  // 3. a typed sheet drops a block number of the whole-file list (and a range of another sheet)
  E("tbSetOpt('epma', 'block', '1'); tbSetOpt('epma', 'region', 'A1:C3')");
  E(`(() => { const i = tbPane('epma').querySelector('[data-opt="sheet"]'); i.value = 'probe2.csv'; i.dispatchEvent(new Event('change', { bubbles: true })); })()`);
  check('typed_sheet_clears_block_and_range', opt('block') === '' && opt('region') === '', { block: opt('block'), region: opt('region') });

  // 4. the sheet panel follows a change of file: opened on probe.csv, it is refetched for probe2.csv
  E("tbEpmaFileSet('probe.csv')"); await E('tbSheetOpen()'); await sleep(150);
  const before = E('TBSH.data && TBSH.data.sheet');
  E("tbPickData('probe2.csv', 'probe')"); await sleep(400);
  const after = E('TBSH.data && TBSH.data.sheet');
  check('sheet_panel_follows_the_file', before === 'probe.csv' && after === 'probe2.csv', { before, after });

  // 5. a late sheet reply never draws over a newer one: two opens in a row, the second file's wins
  E("tbEpmaFileSet('probe.csv')"); const p1 = E('tbSheetOpen()'); E("tbEpmaFileSet('probe2.csv')"); const p2 = E('tbSheetOpen()');
  await Promise.all([p1, p2]); await sleep(100);
  check('late_sheet_reply_ignored', E('TBSH.data && TBSH.data.sheet') === 'probe2.csv', { sheet: E('TBSH.data && TBSH.data.sheet') });

  // 6. another folder: the hidden picks of the last one do not carry over
  E("tbSetOpt('epma', 'block', '3'); tbSetOpt('epma', 'region', 'B2:C4')");
  E("TBS.folder = '/somewhere/else'"); await E('tbLoad()'); await sleep(100);
  check('folder_switch_clears_hidden_picks', opt('block') === '' && opt('region') === '', { block: opt('block'), region: opt('region') });

  // 7. options are saved per tab: two tabs set in one go are both saved (one shared timer had saved only the last)
  E("TBS.saveTimers = {}; tbSaveOpts('epma'); tbSaveOpts('gd')");
  check('per_tab_save_timers', E("Object.keys(TBS.saveTimers).sort().join(',')") === 'epma,gd', { timers: E("Object.keys(TBS.saveTimers).join(',')") });

} catch (ex) {
  out._error = { ok: false, detail: String(ex && ex.stack || ex) };
}
process.stdout.write(JSON.stringify(out));
w.close();
process.exit(0);
