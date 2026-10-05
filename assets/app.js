'use strict';
// Content and navigation are rendered at build time. JS only enhances reading.
const filters = document.querySelectorAll('[data-topic]');
const rows = [...document.querySelectorAll('.archive-rows [data-lesson-topic]')];
for (const button of filters) {
  button.addEventListener('click', () => {
    const selected = button.dataset.topic;
    for (const item of filters) item.setAttribute('aria-pressed', String(item === button));
    let count = 0;
    for (const row of rows) {
      row.hidden = selected !== 'all' && row.dataset.lessonTopic !== selected;
      if (!row.hidden) count++;
    }
    document.querySelector('[data-filter-status]').textContent = selected === 'all'
      ? `显示全部 ${count} 篇讲义` : `${selected} · ${count} 篇讲义`;
  });
}
const progress = document.querySelector('[data-reading-progress]');
if (progress) {
  let scheduled = false;
  const update = () => {
    const distance = document.documentElement.scrollHeight - window.innerHeight;
    progress.style.transform = `scaleX(${distance > 0 ? Math.min(1, Math.max(0, window.scrollY / distance)) : 1})`;
    scheduled = false;
  };
  window.addEventListener('scroll', () => {
    if (!scheduled) { scheduled = true; requestAnimationFrame(update); }
  }, {passive:true});
  window.addEventListener('resize', update);
  update();
}
// Keep the five existing README/bookmark hash links working after migration.
if (document.body.classList.contains('home') && /^#\d{4}-\d{2}-\d{2}-[a-z0-9-]+$/.test(location.hash)) {
  const legacy = document.querySelector(`[data-legacy-id="${location.hash.slice(1)}"]`);
  if (legacy) location.replace(legacy.href);
}
