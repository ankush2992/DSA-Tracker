document.addEventListener('DOMContentLoaded', () => {
  const THEME_KEY = 'dsa-theme';
  const themeToggle = document.getElementById('theme-toggle');
  const setTheme = theme => {
    document.documentElement.setAttribute('data-bs-theme', theme);
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(THEME_KEY, theme);
    if (themeToggle) {
      const isDark = theme === 'dark';
      themeToggle.textContent = isDark ? 'Light Mode' : 'Dark Mode';
      themeToggle.setAttribute('aria-pressed', String(isDark));
      themeToggle.classList.toggle('btn-outline-light', !isDark);
      themeToggle.classList.toggle('btn-outline-secondary', isDark);
    }
  };

  const getPreferredTheme = () => {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored) return stored;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  };

  let currentTheme = getPreferredTheme();
  setTheme(currentTheme);

  if (themeToggle) {
    themeToggle.addEventListener('click', () => {
      currentTheme = currentTheme === 'dark' ? 'light' : 'dark';
      setTheme(currentTheme);
    });
  }

  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', event => {
      if (!localStorage.getItem(THEME_KEY)) {
        currentTheme = event.matches ? 'dark' : 'light';
        setTheme(currentTheme);
      }
    });
  }

  const problemSelect = document.getElementById('resolve-problem');
  const dateInput = document.getElementById('resolve-date');
  const minutesInput = document.getElementById('resolve-minutes');
  const resolveSection = document.getElementById('resolve-section');
  const addProblemDateInput = document.getElementById('add-problem-date');
  const addProblemMinutesInput = document.getElementById('add-problem-minutes');

  document.querySelectorAll('.resolve-fill-problem').forEach(button => {
    button.addEventListener('click', () => {
      if (problemSelect) {
        problemSelect.value = button.dataset.problemId || '';
        problemSelect.focus();
      }
      if (resolveSection) {
        resolveSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
      if (dateInput && !dateInput.value) {
        dateInput.value = new Date().toISOString().slice(0, 10);
      }
    });
  });

  const dateTodayBtn = document.getElementById('resolve-date-today');
  if (dateTodayBtn && dateInput) {
    dateTodayBtn.addEventListener('click', () => {
      dateInput.value = new Date().toISOString().slice(0, 10);
      dateInput.focus();
    });
  }

  const minutesFillBtn = document.getElementById('resolve-minutes-fill');
  if (minutesFillBtn && minutesInput) {
    minutesFillBtn.addEventListener('click', () => {
      const current = minutesInput.value || '30';
      const value = prompt('Minutes spent on this resolve?', current);
      if (value !== null) {
        const trimmed = value.trim();
        if (trimmed && !Number.isNaN(Number(trimmed))) {
          minutesInput.value = trimmed;
        }
      }
      minutesInput.focus();
    });
  }

  const addProblemTodayBtn = document.getElementById('add-problem-date-today');
  if (addProblemTodayBtn && addProblemDateInput) {
    addProblemTodayBtn.addEventListener('click', () => {
      addProblemDateInput.value = new Date().toISOString().slice(0, 10);
      addProblemDateInput.focus();
    });
  }

  const addProblemMinutesBtn = document.getElementById('add-problem-minutes-fill');
  if (addProblemMinutesBtn && addProblemMinutesInput) {
    addProblemMinutesBtn.addEventListener('click', () => {
      const current = addProblemMinutesInput.value || '25';
      const value = prompt('Minutes spent when first tackling this problem?', current);
      if (value !== null) {
        const trimmed = value.trim();
        if (trimmed && !Number.isNaN(Number(trimmed))) {
          addProblemMinutesInput.value = trimmed;
        }
      }
      addProblemMinutesInput.focus();
    });
  }
});
