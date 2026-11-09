// CAMBIO (backend): página nueva. Se abre desde el enlace del correo: restablecer.html?token=...
// Llama a POST /auth/recuperar/restablecer con { token, contrasena_nueva, codigo }.

const form = document.querySelector("#resetForm");
const clave1 = document.querySelector("#newPassword");
const clave2 = document.querySelector("#newPassword2");
const codigo = document.querySelector("#resetCode");
const errorClave1 = document.querySelector("#newPasswordError");
const errorClave2 = document.querySelector("#newPassword2Error");
const errorCodigo = document.querySelector("#resetCodeError");
const feedback = document.querySelector("#resetFeedback");
const boton = document.querySelector("#resetBoton");

// El token viaja en la dirección; se lee y se quita de la barra para que no quede a la vista ni en el historial.
const token = new URLSearchParams(window.location.search).get("token");
if (token) window.history.replaceState(null, "", window.location.pathname);

function mensaje(texto, esError = false) {
    feedback.textContent = texto;
    feedback.style.color = esError ? "#B54E51" : "#65854C";
}

if (!token) {
    mensaje("Este enlace no es válido. Pide uno nuevo desde «¿La olvidaste?».", true);
    boton.disabled = true;
}

form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorClave1.textContent = errorClave2.textContent = errorCodigo.textContent = "";

    let hayError = false;
    if (clave1.value.length < 8 || clave1.value.length > 50) {
        errorClave1.textContent = "La contraseña debe tener entre 8 y 50 caracteres.";
        hayError = true;
    }
    if (clave1.value !== clave2.value) {
        errorClave2.textContent = "Las contraseñas no coinciden.";
        hayError = true;
    }
    const codigoLimpio = codigo.value.trim();
    if (codigoLimpio.length < 6) {
        errorCodigo.textContent = "Escribe el código de Google Authenticator o un código de recuperación.";
        hayError = true;
    }
    if (hayError) return;

    if (typeof PicksyAPI === "undefined") {
        mensaje("No se pudo cargar la conexión con el servidor.", true);
        return;
    }

    boton.disabled = true;
    mensaje("Cambiando la contraseña...");
    try {
        await PicksyAPI.restablecerContrasena(token, clave1.value, codigoLimpio);
        mensaje("¡Listo! Tu contraseña cambió. Te llevamos al inicio de sesión...");
        window.setTimeout(() => window.location.replace("login.html"), 2200);
    } catch (error) {
        mensaje(error.message || "No fue posible cambiar la contraseña.", true);
        // Si el enlace venció no sirve intentar de nuevo.
        if (!/venci|no es v/.test(error.message || "")) boton.disabled = false;
    }
});
