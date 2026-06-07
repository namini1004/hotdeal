(function () {
  const KEY = 'gaji_theme_mode_v1';
  const DARK_CSS = `
    html[data-theme="dark"]{color-scheme:dark}
    html[data-theme="dark"] body{background:#111827!important;color:#f9fafb!important}
    html[data-theme="dark"] .app,
    html[data-theme="dark"] .shell,
    html[data-theme="dark"] .top,
    html[data-theme="dark"] .topbar,
    html[data-theme="dark"] .content,
    html[data-theme="dark"] .comments-panel,
    html[data-theme="dark"] .bottom,
    html[data-theme="dark"] .bottom-cta{background:#111827!important;color:#f9fafb!important}
    html[data-theme="dark"] .item,
    html[data-theme="dark"] .menu-card,
    html[data-theme="dark"] .setting-card,
    html[data-theme="dark"] .nick-modal,
    html[data-theme="dark"] .sort-sheet,
    html[data-theme="dark"] .temp-modal,
    html[data-theme="dark"] .action-sheet,
    html[data-theme="dark"] .settings-sheet,
    html[data-theme="dark"] input,
    html[data-theme="dark"] textarea,
    html[data-theme="dark"] select{background:#1f2937!important;color:#f9fafb!important;border-color:#374151!important}
    html[data-theme="dark"] .item.viewed{background:#263241!important}
    html[data-theme="dark"] .list.view-list .item{background:#111827!important}
    html[data-theme="dark"] .list.view-list .item.viewed{background:#263241!important}
    html[data-theme="dark"] .list.view-list .price{color:#e5e7eb!important}
    html[data-theme="dark"] .source-bottom{background:#312e81!important;color:#f5f3ff!important;border-color:#8b5cf6!important}
    html[data-theme="dark"] .comment-composer,
    html[data-theme="dark"] .reply-composer{background:#111827!important;border:1px solid rgba(249,250,251,.78)!important;border-radius:18px!important;padding:10px!important;align-items:center!important}
    html[data-theme="dark"] .comment-input{background:#111827!important;color:#f9fafb!important;border-color:rgba(249,250,251,.55)!important}
    html[data-theme="dark"] .comment-send{background:#1f2937!important;color:#ddd6fe!important;border-color:rgba(249,250,251,.55)!important}
    html[data-theme="dark"] .meta,
    html[data-theme="dark"] .card-sub,
    html[data-theme="dark"] .hint,
    html[data-theme="dark"] .fav-card-desc,
    html[data-theme="dark"] .nickname-card-help,
    html[data-theme="dark"] .read-toggle-help,
    html[data-theme="dark"] .comment-note{color:#9ca3af!important}
    html[data-theme="dark"] .icon-btn,
    html[data-theme="dark"] .profile-chip,
    html[data-theme="dark"] .view-toggle,
    html[data-theme="dark"] .web-tabs,
    html[data-theme="dark"] .mobile-tabs,
    html[data-theme="dark"] .sheet-btn,
    html[data-theme="dark"] .sort-x-btn{background:#1f2937!important;color:#f9fafb!important;border-color:#374151!important}
    html[data-theme="dark"] .settings-item,
    html[data-theme="dark"] .settings-label,
    html[data-theme="dark"] .settings-arrow{color:#f9fafb!important}
    html[data-theme="dark"] .settings-item:hover,
    html[data-theme="dark"] .settings-item:focus-visible{background:#374151!important}
    html[data-theme="dark"] .settings-icon{background:#312e81!important;color:#ddd6fe!important}
    html[data-theme="dark"] .back,
    html[data-theme="dark"] .back-btn{background:#1f2937!important;color:#f9fafb!important;border-color:#374151!important}
    html[data-theme="dark"] .back:active,
    html[data-theme="dark"] .back-btn:active{background:#374151!important}
    html[data-theme="dark"] .chip{background:#312e81!important;color:#ddd6fe!important}
    html[data-theme="dark"] .chip.active,
    html[data-theme="dark"] .web-tab.active,
    html[data-theme="dark"] .mobile-tab.active{background:#7c3aed!important;color:#fff!important}
    html[data-theme="dark"] a{color:inherit}
  `;

  function getMode() {
    try {
      return localStorage.getItem(KEY) === 'dark' ? 'dark' : 'light';
    } catch (_) {
      return 'light';
    }
  }

  function ensureStyle() {
    if (document.getElementById('gajiThemeStyle')) return;
    const style = document.createElement('style');
    style.id = 'gajiThemeStyle';
    style.textContent = DARK_CSS;
    document.head.appendChild(style);
  }

  function apply(mode) {
    const next = mode === 'dark' ? 'dark' : 'light';
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem(KEY, next);
    } catch (_) {}
    ensureStyle();
    window.dispatchEvent(new CustomEvent('gaji:theme-change', { detail: { mode: next } }));
  }

  ensureStyle();
  apply(getMode());
  window.GajiTheme = { key: KEY, getMode, apply, toggle: () => apply(getMode() === 'dark' ? 'light' : 'dark') };
})();
