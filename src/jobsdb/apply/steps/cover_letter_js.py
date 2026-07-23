"""
cover_letter_js — 求职信单选页的 DOM 探测/点击 JS

e2e(2026-07-22)实测:JobsDB 一键申请的求职信步骤是一页式单选表单
(https://hk.jobsdb.com/job/{id}/apply),选项为 label 文本:
    "Upload a cover letter" / "Write a cover letter" / "Don't include a cover letter"

label[for] 指向的 radio id 是动态的(如 id-_r_2d_),不能用固定选择器,
故用 JS 按 label 文本直接匹配,再点击 label(点 label 会切换关联 radio)。

Continue 按钮在真实 DOM 中由 React 渲染,实测只有 Playwright 原生的
ElementHandle.click() 能触发它的提交逻辑;JS 里 dispatchEvent+click() 无法跳转。
因此本文件只负责"选 Don't include a cover letter",Continue 点击交给 Playwright。

供 CoverLetterStep(detect)与 detectors.detect_current_step 共用,
确保"是否在求职信步骤"用同一套文本判定。
"""

# 命中关键词(转小写后子串匹配),覆盖中英文变体。
_HAS_COVER_LETTER_JS = r"""() => {
  const markers = ['cover letter', '求職信', '求职信'];
  const cands = Array.from(document.querySelectorAll('label, [role="radio"], [role="checkbox"]'));
  return cands.some(el => {
    const t = ((el.textContent || '') + ' ' + (el.getAttribute('aria-label') || '')).toLowerCase();
    return markers.some(k => t.includes(k));
  });
}"""

# 点 "Don't include a cover letter"(及中英文变体),返回 {selected: bool}。
# 不在这里点 Continue:真实 React 按钮需要 Playwright 原生 click() 才能触发跳转。
_CLICK_NO_COVER_LETTER_JS = r"""() => {
  const norm = s => (s || '').toLowerCase()
    .replace(/['‘’`´]/g, '')  // 移除 ASCII/Unicode 撇号变体
    .replace(/[^\p{L}\p{N}]/gu, ' ')                   // 其余非字母数字变空格
    .replace(/\s+/g, ' ')
    .trim();
  const noMarkers = [
    'dont include a cover letter', 'do not include a cover letter', 'no cover letter',
    '不附求職信', '不附上求職信', '不包含求職信', '不需要求職信',
    '不附求职信', '不附上求职信', '不包含求职信'
  ];
  const cands = Array.from(document.querySelectorAll(
    'label, [role="radio"], [role="checkbox"], input[type="radio"]'
  ));
  for (const el of cands) {
    const t = norm((el.textContent || '') + ' ' + (el.getAttribute('aria-label') || ''));
    if (noMarkers.some(k => t.includes(k))) {
      el.click();
      return { selected: true };
    }
  }
  return { selected: false };
}"""
