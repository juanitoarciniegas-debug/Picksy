const form = document.querySelector("#twoFactorForm");
const authCode = document.querySelector("#authCode");
const authCodeError = document.querySelector("#authCodeError");
const feedback = document.querySelector("#twoFactorFeedback");

const useRecoveryCode = document.querySelector("#useRecoveryCode");
const recoveryCodeSection = document.querySelector("#recoveryCodeSection");
const recoveryCodeForm = document.querySelector("#recoveryCodeForm");

// Recuperamos el identificador temporal creado durante el login.
const challengeId = sessionStorage.getItem("picksy2FAChallenge");

// Si no existe una verificación pendiente, regresamos al login.
if (!challengeId) {
    window.location.replace("login.html");
}

// Permitir únicamente seis números.
authCode?.addEventListener("input", () => {
    authCode.value = authCode.value.replace(/\D/g, "").slice(0, 6);

    authCodeError.textContent = "";
    authCode.classList.remove("invalid");
});

// Verificación del código de Google Authenticator.
form?.addEventListener("submit", async (event) => {
    event.preventDefault();

    const code = authCode.value.trim();

    if (!/^\d{6}$/.test(code)) {
        authCodeError.textContent =
            "Introduce un código válido de seis dígitos.";

        authCode.classList.add("invalid");
        return;
    }

    feedback.textContent = "Verificando código...";
    feedback.style.color = "#65854C";

    /*
      CAMBIO (2FA): conexión con el backend.
      Se envía token_2fa (guardado en el login) + code a POST /auth/2fa/login.
      Si es válido, api.js guarda la sesión y se entra a index.html.
    */
    if (typeof PicksyAPI === "undefined") {
        feedback.textContent = "No se pudo cargar la conexión con el servidor.";
        feedback.style.color = "#B54E51";
        return;
    }

    const boton = form.querySelector('button[type="submit"]');
    boton.disabled = true;

    try {
        await PicksyAPI.completarLogin2FA(
            challengeId,
            code,
            sessionStorage.getItem("picksy2FARecordar") === "1"
        );

        sessionStorage.removeItem("picksy2FAChallenge");
        sessionStorage.removeItem("picksy2FARecordar");
        window.location.href = "index.html";

    } catch (error) {
        feedback.textContent = error.message || "No fue posible verificar el código.";
        feedback.style.color = "#B54E51";

        // Si el inicio de sesión venció o se agotaron los intentos, hay que empezar de nuevo.
        if (/Vuelve a escribir/.test(error.message || "")) {
            sessionStorage.removeItem("picksy2FAChallenge");
            sessionStorage.removeItem("picksy2FARecordar");
            window.setTimeout(() => window.location.replace("login.html"), 2500);
        }
        authCode.select();

    } finally {
        boton.disabled = false;
    }
});

// Mostrar el formulario de recuperación.
useRecoveryCode?.addEventListener("click", (event) => {
    event.preventDefault();
    recoveryCodeSection.hidden = false;
});

// Envío del código de recuperación.
recoveryCodeForm?.addEventListener("submit", (event) => {
    event.preventDefault();

    const recoveryCode = document.querySelector("#recoveryCode").value.trim();

    if (!recoveryCode) {
        feedback.textContent = "Introduce tu código de recuperación.";
        feedback.style.color = "#B54E51";
        return;
    }

    /*
      BACKEND:
      Enviar challengeId y recoveryCode.
      El servidor comprobará que el código sea válido
      y que todavía no haya sido utilizado.
    */

    feedback.textContent =
        "La validación del código de recuperación está pendiente del backend.";

    feedback.style.color = "#65854C";
});