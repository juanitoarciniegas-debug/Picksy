
const form = document.querySelector("#loginForm");
const email = document.querySelector("#email");
const password = document.querySelector("#password");
const remember = document.querySelector("#remember");
const feedback = document.querySelector("#formFeedback");
const togglePassword = document.querySelector("#togglePassword");

function validarEmail(valor) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(valor);
}

function setError(input, targetId, message) {
  const errorElement = document.getElementById(targetId);

  errorElement.textContent = message;
  input.classList.toggle("invalid", Boolean(message));
  input.setAttribute("aria-invalid", String(Boolean(message)));
}

function mostrarFeedback(message, type = "info") {
  feedback.textContent = message;
  feedback.className = `form-feedback ${type}`;
}

function limpiarFeedback() {
  feedback.textContent = "";
  feedback.className = "form-feedback";
}

// Validación del correo mientras se escribe.
email.addEventListener("input", () => {
  const valor = email.value.trim();

  if (!valor || validarEmail(valor)) {
    setError(email, "emailError", "");
  } else {
    setError(email, "emailError", "Ingresa un correo electrónico válido.");
  }

  limpiarFeedback();
});

// Limpiar el error de contraseña al escribir.
password.addEventListener("input", () => {
  setError(password, "passwordError", "");
  limpiarFeedback();
});

// Mostrar u ocultar contraseña.
togglePassword.addEventListener("click", () => {
  const mostrar = password.type === "password";

  password.type = mostrar ? "text" : "password";
  togglePassword.textContent = mostrar ? "Ocultar" : "Mostrar";
  togglePassword.setAttribute(
    "aria-label",
    mostrar ? "Ocultar contraseña" : "Mostrar contraseña"
  );
  togglePassword.setAttribute("aria-pressed", String(mostrar));
});

// Inicio de sesión.
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  limpiarFeedback();

  const correo = email.value.trim();
  const contrasena = password.value;
  const recordar = remember.checked;

  let formularioValido = true;

  if (!validarEmail(correo)) {
    setError(email, "emailError", "Ingresa un correo electrónico válido.");
    formularioValido = false;
  } else {
    setError(email, "emailError", "");
  }

  if (!contrasena.trim()) {
    setError(password, "passwordError", "Ingresa tu contraseña.");
    formularioValido = false;
  } else {
    setError(password, "passwordError", "");
  }

  if (!formularioValido) return;

  if (!window.PicksyAPI) {
    mostrarFeedback(
      "No se pudo cargar el servicio de autenticación.",
      "error"
    );
    return;
  }

  const submitButton = form.querySelector('button[type="submit"]');
  const textoOriginal = submitButton.textContent;

  submitButton.disabled = true;
  submitButton.textContent = "Iniciando sesión...";

  try {
    const respuesta = await window.PicksyAPI.iniciarSesion(
      correo,
      contrasena,
      recordar
    );

    // El backend solicita el código de autenticación.
    if (respuesta.requiere_2fa) {
      if (!respuesta.token_2fa) {
        throw new Error("No se recibió el token de verificación.");
      }

      sessionStorage.setItem("picksy2FAChallenge", respuesta.token_2fa);
      sessionStorage.setItem("picksy2FARecordar", String(recordar));
      sessionStorage.removeItem("picksy2FAConfigurar");

      location.href = "verificar-2fa.html";
      return;
    }

    // El backend solicita configurar la autenticación en dos pasos.
    if (respuesta.requiere_configuracion_2fa) {
      if (!respuesta.token_2fa) {
        throw new Error("No se recibió el token para configurar 2FA.");
      }

      sessionStorage.setItem("picksy2FAChallenge", respuesta.token_2fa);
      sessionStorage.setItem("picksy2FARecordar", String(recordar));
      sessionStorage.setItem("picksy2FAConfigurar", "1");

      location.href = "configurar-2fa.html";
      return;
    }

    // La API ya guarda el token de sesión en este escenario.
    if (!respuesta.token) {
      throw new Error("El servidor no devolvió un token de sesión.");
    }

    location.href = "index.html";

  } catch (error) {
    mostrarFeedback(
      error.message || "No fue posible iniciar sesión. Inténtalo nuevamente.",
      "error"
    );
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = textoOriginal;
  }
});
