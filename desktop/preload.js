// 화면에 window.h2app 을 내준다. 서버 화면과 안내 화면(offline.html)에서만.
// 서버 화면이면 앱 전용 화면 코드(/app-ui.js)를 서버에서 받아 붙인다.
const { contextBridge, ipcRenderer, webUtils } = require('electron');

const call = (ch, ...a) => ipcRenderer.invoke(ch, ...a);
const ok = location.protocol === 'file:' || location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1';

if (ok) {
  contextBridge.exposeInMainWorld('h2app', {
    info: () => call('app:info'),
    retry: () => call('app:retry'),
    notify: (title, body) => call('app:notify', title, body),
    projects: {
      list: () => call('proj:list'),
      create: name => call('proj:create', name),
      get: id => call('proj:get', id),
      save: (id, patch) => call('proj:save', id, patch),
      open: id => call('proj:open', id),
      close: () => call('proj:close'),
      current: () => call('proj:current'),
      remove: id => call('proj:remove', id),
      folder: id => call('proj:folder', id),
      dates: () => call('proj:dates'),
    },
    files: {
      open: p => call('file:open', p),
      show: p => call('file:show', p),
      save: (name, b64) => call('file:save', name, b64),
    },
    review: {
      pick: () => call('review:pick'),
      drop: file => call('review:drop', webUtils.getPathForFile(file)),
      read: rels => call('review:read', rels),
    },
    on: (name, fn) => {
      const ch = { downloaded: 'h2:downloaded', noticeClick: 'h2:notice-click' }[name];
      if (ch) ipcRenderer.on(ch, (e, d) => fn(d));
    },
  });
}

if (location.protocol !== 'file:') {
  window.addEventListener('DOMContentLoaded', () => {
    const s = document.createElement('script');
    s.src = '/app-ui.js?v=' + Date.now().toString(36).slice(0, -3);   // 몇 분마다 새로 받는다
    document.head.appendChild(s);
  });
}
