
async function attemptLogin() {
  const pass = document.getElementById('login-password').value;
  const btn = document.getElementById('login-btn');
  const err = document.getElementById('login-err');
  
  btn.disabled = true;
  btn.textContent = 'Verificando...';
  err.style.display = 'none';
  
  try {
    const res = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: pass })
    });
    
    if (res.ok) {
      document.getElementById('login-overlay').style.display = 'none';
      loadPortfolio();
    } else {
      err.style.display = 'block';
    }
  } catch (e) {
    alert("Error de conexión");
  } finally {
    btn.disabled = false;
    btn.textContent = 'Entrar';
  }
}

// Permitir Login con la tecla Enter
document.getElementById('login-password')?.addEventListener('keypress', (e) => {
  if (e.key === 'Enter') attemptLogin();
});
