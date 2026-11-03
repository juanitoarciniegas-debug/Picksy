// ==========================================
// ELEMENTOS DEL FORMULARIO
// ==========================================

const form = document.querySelector("#loginForm");
const email = document.querySelector("#email");
const password = document.querySelector("#password");
const remember = document.querySelector("#remember");

const feedback = document.querySelector("#formFeedback");
const togglePassword = document.querySelector("#togglePassword");


// ==========================================
// VALIDACIONES Y MENSAJES
// ==========================================

function validarEmail(valor) {
  const expresion = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return expresion.test(valor);
}

function setError(input, targetId, message) {
  const target = document.querySelector(`#${targetId}`);

  target.textContent = message;
  input.classList.toggle("invalid", Boolean(message));
  input.setAttribute("aria-invalid", message ? "true" : "false");
}

function mostrarFeedback(message, type = "success") {
  feedback.textContent = message;

  const colors = {
    success: "#65854C",
    error: "#B54E51",
    info: "#778075"
  };

  feedback.style.color = colors[type] || colors.info;
}

function limpiarFeedback() {
  feedback.textContent = "";
}


// ==========================================
// VALIDACIÓN EN TIEMPO REAL
// ==========================================

email?.addEventListener("input", () => {
  const valor = email.value.trim();

  if (valor === "") {
    setError(email, "emailError", "");
  } else if (!validarEmail(valor)) {
    setError(
      email,
      "emailError",
      "El formato del correo electrónico no es válido."
    );
  } else {
    setError(email, "emailError", "");
  }

  limpiarFeedback();
});

password?.addEventListener("input", () => {
  setError(password, "passwordError", "");
  limpiarFeedback();
});


// ==========================================
// MOSTRAR U OCULTAR CONTRASEÑA
// ==========================================

togglePassword?.addEventListener("click", () => {
  const mostrar = password.type === "password";

  password.type = mostrar ? "text" : "password";
  togglePassword.textContent = mostrar ? "Ocultar" : "Ver";

  togglePassword.setAttribute(
    "aria-label",
    mostrar ? "Ocultar contraseña" : "Mostrar contraseña"
  );
});


// ==========================================
// INICIO DE SESIÓN
// ==========================================

form?.addEventListener("submit", async (event) => {
  event.preventDefault();

  const emailValue = email.value.trim();
  const passwordValue = password.value;

  const emailValido = validarEmail(emailValue);
  const passwordValida = passwordValue.length > 0;

  // Validar correo.
  setError(
    email,
    "emailError",
    emailValue.length === 0
      ? "Escribe tu correo electrónico."
      : !emailValido
        ? "Ingresa un correo electrónico válido."
        : ""
  );

  // Validar contraseña.
  setError(
    password,
    "passwordError",
    passwordValida ? "" : "Escribe tu contraseña."
  );

  if (!emailValido || !passwordValida) {
    mostrarFeedback(
      "Revisa los campos marcados para continuar.",
      "error"
    );
    return;
  }

  // Comprobar que la API esté disponible.
  if (typeof PicksyAPI === "undefined") {
    mostrarFeedback(
      "No se pudo cargar la conexión con el servidor.",
      "error"
    );
    return;
  }

  const boton = form.querySelector('button[type="submit"]');

  boton.disabled = true;
  mostrarFeedback("Iniciando sesión...", "info");

  try {
    const respuesta = await PicksyAPI.iniciarSesion(
      emailValue,
      passwordValue,
      remember.checked
    );

    // CAMBIO (2FA): el backend responde { requiere_2fa: true, token_2fa } cuando la cuenta
    // tiene Google Authenticator activado (antes decía requiere2FA / challengeId).
    // En ese caso todavía NO hay sesión: se guarda el token temporal (dura 5 min) y se pide el código.
    if (respuesta?.requiere_2fa) {

      if (!respuesta.token_2fa) {
        throw new Error(
          "El servidor no proporcionó el identificador de verificación."
        );
      }

      // Guardar el identificador temporal para el siguiente paso.
      sessionStorage.setItem(
        "picksy2FAChallenge",
        respuesta.token_2fa
      );
      // CAMBIO (2FA): recordar si marcó "Recordar mi sesión", para usarlo al completar el segundo paso.
      sessionStorage.setItem(
        "picksy2FARecordar",
        remember.checked ? "1" : "0"
      );

      window.location.href = "verificar-2fa.html";
      return;
    }

    // Si no requiere 2FA, continuar al inicio.
    window.location.href = "index.html";

  } catch (error) {
    mostrarFeedback(
      error.message || "No fue posible iniciar sesión.",
      "error"
    );

  } finally {
    boton.disabled = false;
  }
});