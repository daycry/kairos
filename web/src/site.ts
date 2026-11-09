import './site.css';

// Public pages do not initialize the private client or query memory.
for (const menu of document.querySelectorAll<HTMLDetailsElement>('.mobile-navigation')) {
  menu.addEventListener('click', event => {
    if ((event.target as Element).closest('a')) menu.open = false;
  });
  menu.addEventListener('keydown', event => {
    if (event.key === 'Escape' && menu.open) {
      menu.open = false;
      menu.querySelector<HTMLElement>('summary')?.focus();
    }
  });
}
