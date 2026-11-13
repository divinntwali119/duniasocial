(() => {
  const initializeMessaging = () => {
    const content = document.querySelector('[data-messaging-content]');
    if (!content) return;

    const search = document.querySelector('[data-conversation-search]');
    const filterButtons = [...document.querySelectorAll('[data-conversation-filter]')];
    const rows = [...content.querySelectorAll('[data-conversation-link]')];
    const noResults = content.querySelector('[data-conversation-no-results]');
    let activeFilter = 'all';

    const updateRows = () => {
      const query = search?.value.trim().toLocaleLowerCase() || '';
      let visibleCount = 0;
      rows.forEach((row) => {
        const matchesSearch = (row.dataset.search || '').includes(query);
        const matchesFilter = activeFilter !== 'unread' || row.dataset.unread === 'true';
        const visible = matchesSearch && matchesFilter;
        row.classList.toggle('hidden', !visible);
        if (visible) visibleCount += 1;
      });
      if (noResults) noResults.classList.toggle('hidden', visibleCount > 0 || rows.length === 0);
    };

    search?.addEventListener('input', updateRows);
    filterButtons.forEach((button) => {
      button.addEventListener('click', () => {
        activeFilter = button.dataset.conversationFilter || 'all';
        filterButtons.forEach((filterButton) => {
          const selected = filterButton === button;
          filterButton.setAttribute('aria-pressed', String(selected));
          filterButton.classList.toggle('btn-primary', selected);
          filterButton.classList.toggle('btn-ghost', !selected);
        });
        updateRows();
      });
    });

  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeMessaging, { once: true });
  } else {
    initializeMessaging();
  }
})();
