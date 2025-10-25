document.addEventListener('DOMContentLoaded', () => {
  const THEME_KEY = 'dsa-theme';
  const BACKGROUND_KEY = 'dsa-theme-bg-index';
  const backgroundPalette = [
    '#9FC088',
    '#91C4C3',
    '#9B5DE0',
    '#5D866C',
    '#BF092F',
    '#B0CE88',
    '#2F5755',
    '#5C3E94',
    '#FF3F7F',
    '#C2E2FA',
    '#E9D484'
  ];

  const applyBackground = index => {
    if (index >= 0 && index < backgroundPalette.length) {
      document.documentElement.style.setProperty('--dynamic-surface', backgroundPalette[index]);
    }
  };

  const themeToggle = document.getElementById('theme-toggle');
  const setTheme = (theme, advancePalette = false) => {
    document.documentElement.setAttribute('data-bs-theme', theme);
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(THEME_KEY, theme);

    if (theme === 'dark') {
      let index = Number.parseInt(localStorage.getItem(BACKGROUND_KEY), 10);
      if (Number.isNaN(index) || index < 0) {
        index = -1;
      }
      if (advancePalette || index === -1) {
        index = (index + 1) % backgroundPalette.length;
        localStorage.setItem(BACKGROUND_KEY, index);
      }
      applyBackground(index);
    } else {
      document.documentElement.style.removeProperty('--dynamic-surface');
    }

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
      const advancePalette = currentTheme === 'dark';
      setTheme(currentTheme, advancePalette);
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

  const formatDateForInput = (date = new Date()) => {
    const tzOffset = date.getTimezoneOffset() * 60000;
    const localISO = new Date(date.getTime() - tzOffset).toISOString();
    return localISO.split('T')[0];
  };

  const problemSelect = document.getElementById('resolve-problem');
  const dateInput = document.getElementById('resolve-date');
  const minutesInput = document.getElementById('resolve-minutes');
  const resolveSection = document.getElementById('resolve-section');
  const addProblemDateInput = document.getElementById('add-problem-date');
  const addProblemMinutesInput = document.getElementById('add-problem-minutes');

  if (dateInput && !dateInput.value) {
    dateInput.value = formatDateForInput();
  }

  const params = new URLSearchParams(window.location.search);
  const focusProblemId = params.get('problem_id');
  if (focusProblemId && problemSelect) {
    problemSelect.value = focusProblemId;
    if (resolveSection) {
      resolveSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

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
        dateInput.value = formatDateForInput();
      }
    });
  });

  const dateTodayBtn = document.getElementById('resolve-date-today');
  if (dateTodayBtn && dateInput) {
    dateTodayBtn.addEventListener('click', () => {
      dateInput.value = formatDateForInput();
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
      addProblemDateInput.value = formatDateForInput();
      addProblemDateInput.focus();
    });
  } else if (addProblemDateInput && !addProblemDateInput.value) {
    addProblemDateInput.value = formatDateForInput();
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
