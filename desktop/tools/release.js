// 새 버전 올리기: package.json 의 version 을 올린 뒤 `npm run release`.
// 설치 파일·blockmap·latest.yml 을 설치 파일 전용 공개 저장소의 릴리스로 올린다(gh 로그인 필요).
// 켜져 있는 앱은 다음에 켤 때 latest.yml 을 보고 '업데이트가 있어요!'를 띄운다.
const { execFileSync } = require('child_process');
const path = require('path');
const pkg = require('../package.json');
const repo = `${pkg.build.publish[0].owner}/${pkg.build.publish[0].repo}`;
const v = pkg.version, dist = path.join(__dirname, '..', 'dist');
const files = [`hydrogen-permit-setup-${v}.exe`, `hydrogen-permit-setup-${v}.exe.blockmap`, 'latest.yml'].map(f => path.join(dist, f));
execFileSync('gh', ['release', 'create', `v${v}`, ...files, '-R', repo, '--title', v, '--notes', `수소시설 인허가 가이드 ${v}`], { stdio: 'inherit' });
console.log('올림:', repo, v);
