// 신청 도우미 오른쪽 패널(assist.html)에만 붙는다. 민원 사이트(왼쪽 창)에는 아무것도 내주지 않는다.
const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('assist', {
  onState: fn => ipcRenderer.on('assist:state', (e, s) => fn(s)),
  go: url => ipcRenderer.invoke('assist:go', url),
  start: () => ipcRenderer.invoke('assist:start'),
  pause: p => ipcRenderer.invoke('assist:pause', p),
  back: () => ipcRenderer.invoke('assist:back'),
});
