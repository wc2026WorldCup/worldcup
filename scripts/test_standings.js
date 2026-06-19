#!/usr/bin/env node
/*
 * 单元测试:积分榜与晋级 32 强逻辑(严格按 FIFA 规则)。
 * 直接从 src/template.html 的 STD_START..STD_END 区块提取 computeStandings,
 * 保证测试的就是线上跑的同一份代码。纯 Node、零依赖。
 *   运行:  node scripts/test_standings.js
 */
const fs = require('fs'), path = require('path');
const ROOT = path.resolve(__dirname, '..');

const html = fs.readFileSync(path.join(ROOT, 'src', 'template.html'), 'utf8');
const m = html.match(/\/\/ === STD_START[\s\S]*?\n([\s\S]*?)\/\/ === STD_END ===/);
if (!m) { console.error('找不到 STD_START / STD_END 标记'); process.exit(1); }
const computeStandings = new Function(m[1] + '; return computeStandings;')();

let fail = 0;
const ok = (c, msg) => c ? console.log('  ✓ ' + msg)
                         : (console.error('  ✗ ' + msg), fail++);
const eq = (a, b, msg) =>
  ok(JSON.stringify(a) === JSON.stringify(b), msg + '  (得到 ' + JSON.stringify(a) + ',期望 ' + JSON.stringify(b) + ')');

const gmA = (n, h, a) => ({ n, sk: 'group-stage', g: 'A', h, a, hz: h, az: a, hf: '', af: '' });

// ── 测试 1:净胜球/进球排序 + 同分相互战绩 ──────────────────────────
// A-B 1-0, A-C 0-1, A-D 1-1, B-C 2-1, B-D 0-0, C-D 1-1
// 总:A(4分,净0,进2) B(4,0,2) C(4,0,3) D(3,0,2)
// → C 进球多排第1;A、B 三项全平,A 相互战绩胜 B(1-0)→ A 第2、B 第3 → [C,A,B,D]
console.log('测试 1 · 排序规则(进球数 + 相互战绩):');
(function () {
  const DATA = [gmA(1,'A','B'),gmA(2,'A','C'),gmA(3,'A','D'),gmA(4,'B','C'),gmA(5,'B','D'),gmA(6,'C','D')];
  const R = {1:{hs:1,as:0},2:{hs:0,as:1},3:{hs:1,as:1},4:{hs:2,as:1},5:{hs:0,as:0},6:{hs:1,as:1}};
  Object.values(R).forEach(r => r.live = false);
  const S = computeStandings(DATA, R);
  eq(S.groups.A.map(t => t.eng), ['C','A','B','D'], 'A 组排序 = C > A > B > D');
  eq(S.groups.A[0].GF, 3, 'C 队进球 = 3(靠进球数压过 A/B)');
  eq(S.groups.A[1].eng, 'A', '第 2 名 = A(相互战绩胜 B)');
  eq(S.groups.A[2].eng, 'B', '第 3 名 = B');
})();

// ── 测试 2:只统计已完赛,进行中的比赛不计 ─────────────────────────
console.log('测试 2 · 只算已完赛:');
(function () {
  const DATA = [gmA(1,'A','B'), gmA(2,'C','D')];
  const R = { 1:{hs:3,as:0,live:true}, 2:{hs:1,as:0,live:false} };
  const S = computeStandings(DATA, R);
  eq(S.groups.A.find(t=>t.eng==='A').P, 0, '进行中比赛不计场次(A 仍 0 场)');
  eq(S.groups.A.find(t=>t.eng==='C').Pts, 3, '已完赛正常计分(C 得 3 分)');
})();

// ── 测试 3:真实 104 场数据 + 全部小组赛完赛 → 12 组、晋级 32 ───────
console.log('测试 3 · 真实赛程 + 全完赛(结构与 32 强):');
(function () {
  const DATA = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'matches.json'), 'utf8'));
  const R = {};
  DATA.forEach(mm => {
    if (mm.g && mm.sk === 'group-stage') {
      const mod = mm.n % 3;                         // 制造确定性比分
      const sc = mod === 0 ? [1,1] : mod === 1 ? [2,0] : [0,1];
      R[mm.n] = { hs: sc[0], as: sc[1], live: false };
    }
  });
  const S = computeStandings(DATA, R);
  eq(Object.keys(S.groups).length, 12, '共 12 个小组');
  ok(Object.keys(S.groups).every(g => S.groups[g].length === 4), '每组 4 支球队');
  eq(S.winners.length, 12, '12 个小组第 1');
  eq(S.runners.length, 12, '12 个小组第 2');
  eq(S.thirds.length, 12, '12 个小组第 3');
  eq(S.thirds.filter(x => x.qualified).length, 8, '最佳第 3 名取 8 个晋级');
  eq(S.winners.length + S.runners.length + S.thirds.filter(x => x.qualified).length, 32, '晋级总数 = 32');
  ok(Object.keys(S.groups).every(g => {
    const a = S.groups[g];
    return a[0].Pts >= a[1].Pts && a[1].Pts >= a[2].Pts && a[2].Pts >= a[3].Pts;
  }), '各组按积分降序');
  ok(S.thirds.every((x, i) => i === 0 || S.thirds[i-1].t.Pts >= x.t.Pts), '最佳第三名按积分降序');
})();

// ── 测试 4:淘汰赛胜者判定 koWinner(含点球 1:1 靠 winner 标志) ──
console.log('测试 4 · 淘汰赛胜者(含点球):');
(function () {
  const mko = html.match(/function koWinner\(m\)\{[\s\S]*?\n\}/);
  ok(!!mko, '从 template.html 提取到 koWinner');
  const RESULTS = { 1:{hs:2,as:1}, 2:{hs:1,as:2}, 3:{hs:1,as:1,w:'h'}, 4:{hs:1,as:1}, 5:{hs:0,as:0,live:true} };
  const koWinner = new Function('RESULTS', mko[0] + '; return koWinner;')(RESULTS);
  eq(koWinner({n:1}), 'h', '2:1 → 主胜');
  eq(koWinner({n:2}), 'a', '1:2 → 客胜');
  eq(koWinner({n:3}), 'h', '1:1 但 ESPN winner=主 → 主胜(点球判得准)');
  eq(koWinner({n:4}), null, '1:1 无胜者标志 → 未定(不乱判)');
  eq(koWinner({n:5}), null, '进行中 → 未定');
})();

if (fail) { console.error('\n❌ ' + fail + ' 个断言失败'); process.exit(1); }
console.log('\n✅ 全部通过');
