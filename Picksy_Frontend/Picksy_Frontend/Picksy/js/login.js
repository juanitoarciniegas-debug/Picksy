const form = document.querySelector("#loginForm");
const email = document.querySelector("#email");
const password = document.querySelector("#password");
const feedback = document.querySelector("#formFeedback");

function setError(input, targetId, message) {
  const target = document.querySelector(`#${targetId}`);
  target.textContent = message;
  input.classList.toggle("invalid", Boolean(message));
  input.setAttribute("aria-invalid", message ? "true" : "false");
}

// CAMBIO (backend): el envío ahora es "async" y llama al backend con PicksyAPI (js/api.js).
// Requiere que js/api.js esté cargado en login.html ANTES de este archivo.
form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const emailValue = email.value.trim();
  const passwordValue = password.value;
  const validEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(emailValue);
  setError(email, "emailError", emailValue.length === 0 ? "Escribe tu correo electrónico." : (!validEmail ? "Ingresa un correo electrónico válido." : ""));
  // CAMBIO (backend): se quitó el mínimo de 6 caracteres; la contraseña la valida el servidor.
  setError(password, "passwordError", passwordValue.length === 0 ? "Escribe tu contraseña." : "");
  if (!validEmail || passwordValue.length === 0) {
    feedback.textContent = "Revisa los campos marcados para continuar.";
    feedback.style.color = "#B54E51";
    return;
  }

  if (typeof PicksyAPI === "undefined") {
    feedback.textContent = "Falta cargar js/api.js en login.html.";
    feedback.style.color = "#B54E51";
    return;
  }

  const boton = form.querySelector('button[type="submit"]');
  boton.disabled = true;
  feedback.textContent = "Iniciando sesión...";
  feedback.style.color = "#65854C";
  try {
    // "Recordar mi sesión": si está marcado, el token se guarda aunque se cierre el navegador.
    await PicksyAPI.iniciarSesion(emailValue, passwordValue, document.querySelector("#remember").checked);
    window.location.href = "index.html";
  } catch (error) {
    feedback.textContent = error.message;
    feedback.style.color = "#B54E51";
  } finally {
    boton.disabled = false;
  }
});

[email, password].forEach((input) => input?.addEventListener("input", () => {
  input.classList.remove("invalid");
  input.setAttribute("aria-invalid", "false");
  const error = document.querySelector(`#${input.id}Error`);
  if (error) error.textContent = "";
}));

document.querySelector("#togglePassword")?.addEventListener("click", (event) => {
  const button = event.currentTarget;
  const show = password.type === "password";
  password.type = show ? "text" : "password";
  button.textContent = show ? "Ocultar" : "Ver";
  button.setAttribute("aria-label", show ? "Ocultar contraseña" : "Mostrar contraseña");
});

document.querySelector("#forgotPassword")?.addEventListener("click", (event) => {
  event.preventDefault();
  feedback.textContent = "La recuperación de contraseña se implementará cuando se conecte el backend.";
  feedback.style.color = "#65854C";
});
document.querySelector("#signupLink")?.addEventListener("click", (event) => {
  event.preventDefault();
  feedback.textContent = "El registro será una pantalla posterior del proyecto.";
  feedback.style.color = "#65854C";
});
