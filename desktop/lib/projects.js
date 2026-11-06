// 사업장별 프로젝트. 내 문서\수소시설 인허가 가이드\<사업장 이름>\ 에
//   project.json  이름·허가 종류·사업 정보·일정(예정일·마감일)·저장한 대화·서류 목록
//   서류\         앱에서 만든 신청서·꾸러미, 내려받은 파일
// 서버에는 아무것도 보내지 않는다.
const { app, shell } = require('electron');
const path = require('path');
const fs = require('fs');

let currentId = null;

function root() {
  const r = path.join(app.getPath('documents'), app.getName());
  fs.mkdirSync(r, { recursive: true });
  return r;
}
// 윈도우 폴더 이름에 못 쓰는 글자를 뺀다. 폴더 이름이 곧 id 다.
const safe = s => String(s || '').replace(/[\\/:*?"<>|\x00-\x1f]/g, ' ').replace(/\s+/g, ' ').trim().replace(/[. ]+$/, '').slice(0, 60);
const dir = id => path.join(root(), safe(id));
const file = id => path.join(dir(id), 'project.json');

function read(id) {
  try { return JSON.parse(fs.readFileSync(file(id), 'utf8')); } catch (e) { return null; }
}
function write(id, p) {
  fs.mkdirSync(path.join(dir(id), '서류'), { recursive: true });
  p.updated = new Date().toISOString();
  const tmp = file(id) + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(p, null, 1), 'utf8');
  fs.renameSync(tmp, file(id));                          // 쓰다 끊겨도 원래 파일이 남게
  return p;
}

function list() {
  return fs.readdirSync(root(), { withFileTypes: true })
    .filter(d => d.isDirectory() && fs.existsSync(path.join(root(), d.name, 'project.json')))
    .map(d => {
      const p = read(d.name) || {};
      return { id: d.name, name: p.name || d.name, kind: p.kind || '', updated: p.updated || '',
        dates: (p.dates || []).filter(x => !x.done).length, files: (p.files || []).length };
    })
    .sort((a, b) => b.updated.localeCompare(a.updated));
}

function create(name) {
  const id = safe(name);
  if (!id) throw new Error('사업장 이름을 적어 주세요');
  if (fs.existsSync(file(id))) return get(id);
  return { id, ...write(id, { name: name.trim(), created: new Date().toISOString(), kind: '', profile: null,
    dates: [], convs: [], files: [], notes: '' }) };
}

// 서류 폴더에 있는 실제 파일과 목록을 맞춘다(탐색기에서 지우거나 넣어도 맞게).
function syncFiles(id, p) {
  const d = path.join(dir(id), '서류');
  let names = [];
  try { names = fs.readdirSync(d).filter(n => fs.statSync(path.join(d, n)).isFile()); } catch (e) {}
  const old = new Map((p.files || []).map(f => [f.name, f]));
  p.files = names.map(n => old.get(n) || { name: n, added: fs.statSync(path.join(d, n)).mtime.toISOString() })
    .map(f => ({ ...f, path: path.join(d, f.name) }))
    .sort((a, b) => (b.added || '').localeCompare(a.added || ''));
  return p;
}

function get(id) {
  const p = read(id);
  return p ? { id: safe(id), ...syncFiles(id, p) } : null;
}

const KEYS = ['name', 'kind', 'profile', 'dates', 'convs', 'notes'];
function save(id, patch) {
  const p = read(id);
  if (!p) throw new Error('없는 사업장');
  for (const k of KEYS) if (patch && k in patch) p[k] = patch[k];
  if (Array.isArray(p.convs)) p.convs = p.convs.slice(0, 50);
  write(id, p);
  return get(id);
}

function addFile(id, full) {
  const p = read(id);
  if (!p) return;
  const name = path.basename(full);
  p.files = (p.files || []).filter(f => f.name !== name);
  p.files.unshift({ name, added: new Date().toISOString() });
  write(id, p);
}

function setCurrent(id) {
  currentId = id && read(id) ? safe(id) : null;
  return currentId ? get(currentId) : null;
}
const current = () => (currentId && read(currentId) ? currentId : null);

async function remove(id) {
  if (!read(id)) return false;
  if (currentId === safe(id)) currentId = null;
  await shell.trashItem(dir(id));
  return true;
}

// 알림용: 모든 사업장의 끝나지 않은 일정
function allDates() {
  return list().flatMap(s => (read(s.id).dates || []).filter(x => !x.done && x.date)
    .map(x => ({ project: s.id, name: s.name, title: x.title, date: x.date, id: x.id })));
}

module.exports = { root, dir, list, create, get, save, addFile, setCurrent, current, remove, allDates };
