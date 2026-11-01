(() => {
  const languageButtons = document.querySelectorAll('[data-set-lang]');
  const status = document.getElementById('copy-status');
  const isEnglish = () => document.documentElement.lang === 'en';

  function setLanguage(language) {
    const english = language === 'en';
    document.documentElement.lang = english ? 'en' : 'zh-CN';
    languageButtons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.setLang === language)));
    document.querySelectorAll('[data-readme-link]').forEach(link => {
      link.href = 'https://github.com/alvin20062006-beep/Claude-Sentry-Skill' + (english ? '/blob/main/README.en.md' : '#readme');
    });
    document.querySelector('meta[name="description"]').content = english
      ? 'Your conversation comes first. A heads-up when it matters. Claude Code Plugin and standalone Skill. Advisory only, no scoring.'
      : '让 Claude 专注回答，让哨兵轻声提醒。Claude Code Plugin 与独立 Skill，正常回答优先，只提醒，不评分。';
    status.textContent = '';
    try { localStorage.setItem('sentry-language', language); } catch {}
  }

  let savedLanguage;
  try { savedLanguage = localStorage.getItem('sentry-language'); } catch {}
  const requestedLanguage = new URLSearchParams(location.search).get('lang');
  setLanguage((requestedLanguage || savedLanguage) === 'en' ? 'en' : 'zh');
  languageButtons.forEach(button => button.addEventListener('click', () => {
    const language = button.dataset.setLang;
    setLanguage(language);
    const url = new URL(location.href);
    url.searchParams.set('lang', language);
    try { history.replaceState(null, '', url); } catch {}
  }));

  document.querySelectorAll('[data-scenario]').forEach(button => button.addEventListener('click', () => {
    document.getElementById('demo-notice').hidden = button.dataset.scenario !== 'ip';
    document.querySelectorAll('[data-scenario]').forEach(option => option.setAttribute('aria-pressed', String(option === button)));
  }));

  function setInstallation(method) {
    document.querySelectorAll('[data-install]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.install === method)));
    document.getElementById('install-plugin').hidden = method !== 'plugin';
    document.getElementById('install-skill').hidden = method !== 'skill';
    status.textContent = '';
  }
  document.querySelectorAll('[data-install]').forEach(button => button.addEventListener('click', () => setInstallation(button.dataset.install)));
  document.querySelectorAll('[data-open-install]').forEach(link => link.addEventListener('click', () => setInstallation(link.dataset.openInstall)));

  document.querySelectorAll('[data-copy]').forEach(button => button.addEventListener('click', async () => {
    const code = document.getElementById(button.dataset.copy);
    try {
      await navigator.clipboard.writeText(code.textContent.trim());
      status.textContent = isEnglish() ? 'Copied. Paste into your terminal when ready.' : '已复制，可粘贴到终端中使用。';
    } catch {
      const range = document.createRange();
      range.selectNodeContents(code);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      status.textContent = isEnglish() ? 'Text selected. Use your keyboard or copy menu to copy it.' : '已选中文字，请使用快捷键或复制菜单复制。';
    }
  }));
})();
