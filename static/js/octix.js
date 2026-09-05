(() => {
  const menuButton = document.querySelector('[data-menu-toggle]');
  const menu = document.querySelector('[data-menu]');
  if (menuButton && menu) {
    menuButton.addEventListener('click', () => {
      const open = menu.classList.toggle('open');
      menuButton.setAttribute('aria-expanded', String(open));
    });
    menu.querySelectorAll('a').forEach(a => a.addEventListener('click', () => {
      menu.classList.remove('open');
      menuButton.setAttribute('aria-expanded', 'false');
    }));
  }

  document.querySelectorAll('[data-dismiss-flash]').forEach(button => {
    button.addEventListener('click', () => button.closest('.flash')?.remove());
  });

  document.querySelectorAll('[data-toggle-password]').forEach(button => {
    button.addEventListener('click', () => {
      const input = document.getElementById(button.dataset.togglePassword);
      if (!input) return;
      const hidden = input.type === 'password';
      input.type = hidden ? 'text' : 'password';
      button.textContent = hidden ? 'Masquer' : 'Voir';
    });
  });

  const password = document.getElementById('password');
  const password2 = document.getElementById('password2');
  const meter = document.querySelector('[data-password-meter]');
  const label = document.querySelector('[data-password-label]');
  if (password && meter && label) {
    const updateMeter = () => {
      const value = password.value;
      let score = 0;
      if (value.length >= 6) score++;
      if (value.length >= 10) score++;
      if (/[A-Z]/.test(value) && /[a-z]/.test(value)) score++;
      if (/\d/.test(value) || /[^A-Za-z0-9]/.test(value)) score++;
      meter.style.width = `${score * 25}%`;
      label.textContent = score <= 1 ? 'Mot de passe faible.' : score === 2 ? 'Mot de passe correct.' : score === 3 ? 'Bon mot de passe.' : 'Très bon mot de passe.';
    };
    password.addEventListener('input', updateMeter);
  }

  document.querySelectorAll('[data-password-form]').forEach(form => {
    form.addEventListener('submit', event => {
      const p1 = form.querySelector('#password');
      const p2 = form.querySelector('#password2');
      if (p1 && p2 && p1.value !== p2.value) {
        event.preventDefault();
        p2.setCustomValidity('Les deux mots de passe ne correspondent pas.');
        p2.reportValidity();
      }
    });
  });
  if (password2) password2.addEventListener('input', () => password2.setCustomValidity(''));
})();
