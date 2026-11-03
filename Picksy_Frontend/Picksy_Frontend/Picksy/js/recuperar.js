
const recoveryForm = document.querySelector("#recoveryForm");
const recoveryEmail = document.querySelector("#recoveryEmail");
const recoveryEmailError = document.querySelector("#recoveryEmailError");
const recoveryFeedback = document.querySelector("#recoveryFeedback");

function validarCorreo(valor) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(valor);
}

// Validación mientras el usuario escribe.
recoveryEmail?.addEventListener("input", () => {
    const valor = recoveryEmail.value.trim();

    if (valor === "") {
        recoveryEmailError.textContent = "";
        recoveryEmail.classList.remove("invalid");
        return;
    }

    if (!validarCorreo(valor)) {
        recoveryEmailError.textContent =
            "Escribe un correo electrónico válido.";

        recoveryEmail.classList.add("invalid");
    } else {
        recoveryEmailError.textContent = "";
        recoveryEmail.classList.remove("invalid");
    }
});

// Envío de la solicitud de recuperación.
recoveryForm?.addEventListener("submit", async (event) => {
    event.preventDefault();

    const correo = recoveryEmail.value.trim();

    if (!validarCorreo(correo)) {
        recoveryEmailError.textContent =
            "Ingresa un correo electrónico válido.";

        recoveryEmail.classList.add("invalid");
        recoveryFeedback.textContent =
            "Revisa el correo antes de continuar.";

        recoveryFeedback.style.color = "#B54E51";
        return;
    }

    recoveryEmailError.textContent = "";
    recoveryEmail.classList.remove("invalid");

    recoveryFeedback.textContent =
        "El formulario está validado, pero la recuperación todavía no está conectada al backend.";

    recoveryFeedback.style.color = "#65854C";

    // ==============================================
    // PENDIENTE DE CONEXIÓN CON EL BACKEND
    //
    // Aquí se enviará el correo al servidor.
    // El servidor deberá:
    // 1. Generar un token temporal y seguro.
    // 2. Enviar un enlace de recuperación al correo.
    // 3. Validar el token cuando el usuario abra el enlace.
    // 4. Permitir establecer una nueva contraseña.
    //
    // No debemos cambiar la contraseña directamente
    // desde este formulario del frontend.
    // ==============================================
});
