
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

    // CAMBIO (backend): conexión real. El servidor responde siempre lo mismo (exista o no el correo)
    // y, si la cuenta existe, envía un enlace válido 30 minutos que abre restablecer.html.
    if (typeof PicksyAPI === "undefined") {
        recoveryFeedback.textContent = "No se pudo cargar la conexión con el servidor.";
        recoveryFeedback.style.color = "#B54E51";
        return;
    }

    const boton = recoveryForm.querySelector('button[type="submit"]');
    boton.disabled = true;
    recoveryFeedback.textContent = "Enviando...";
    recoveryFeedback.style.color = "#65854C";

    try {
        const respuesta = await PicksyAPI.solicitarRecuperacion(correo);
        recoveryFeedback.textContent = respuesta.mensaje;
        recoveryFeedback.style.color = "#65854C";
    } catch (error) {
        recoveryFeedback.textContent = error.message || "No fue posible enviar las instrucciones.";
        recoveryFeedback.style.color = "#B54E51";
    } finally {
        boton.disabled = false;
    }
});
