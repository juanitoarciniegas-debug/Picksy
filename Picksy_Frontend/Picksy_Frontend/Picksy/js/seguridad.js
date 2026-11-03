// CAMBIO (2FA): este archivo ahora está conectado al backend (api.js debe cargarse antes).

const startSetupButton = document.querySelector("#startSetupButton");
const startDisableButton = document.querySelector("#startDisableButton");
const setupSection = document.querySelector("#setupSection");
const setupForm = document.querySelector("#setupVerificationForm");
const setupCode = document.querySelector("#setupCode");
const setupCodeError = document.querySelector("#setupCodeError");
const disableSection = document.querySelector("#disableSection");
const disableForm = document.querySelector("#disableForm");
const disablePassword = document.querySelector("#disablePassword");
const disableCode = document.querySelector("#disableCode");
const disableError = document.querySelector("#disableError");
const recoverySection = document.querySelector("#recoverySection");
const securityFeedback = document.querySelector("#securityFeedback");
const twoFactorStatus = document.querySelector("#twoFactorStatus");
const qrPlaceholder = document.querySelector("#qrPlaceholder");
const secretPlaceholder = document.querySelector("#secretPlaceholder");

function mostrarMensaje(texto, esError = false) {
    securityFeedback.textContent = texto;
    securityFeedback.style.color = esError ? "#B54E51" : "#65854C";
}

// La app muestra el código como "123 456": se quitan los espacios antes de validar.
function limpiarCodigo(valor) {
    return valor.replace(/\s/g, "");
}

// Cambia la pantalla según el 2FA esté activado o no.
function mostrarEstado(activo) {
    twoFactorStatus.textContent = activo ? "Activada" : "Desactivada";
    twoFactorStatus.classList.toggle("active", activo);   // clase .active ya existe en styles.css
    startSetupButton.hidden = activo;
    startDisableButton.hidden = !activo;
    setupSection.hidden = true;
    disableSection.hidden = true;
    qrPlaceholder.innerHTML = "<span>QR</span><small>El código QR aparecerá aquí</small>";
    secretPlaceholder.textContent = "Pendiente de conexión con backend";
}

// Al abrir la página: solo para usuarios con sesión.
async function iniciar() {
    if (typeof PicksyAPI === "undefined") {
        mostrarMensaje("No se pudo cargar la conexión con el servidor.", true);
        return;
    }
    let usuario;
    try {
        usuario = await PicksyAPI.usuarioActual();
    } catch {
        mostrarMensaje("No se pudo conectar con el servidor. Inténtalo de nuevo.", true);
        return;
    }
    if (!usuario) {
        window.location.href = "login.html";
        return;
    }
    mostrarEstado(Boolean(usuario.dos_factores));
}

startSetupButton?.addEventListener("click", async () => {
    startSetupButton.disabled = true;
    mostrarMensaje("Generando el código QR...");

    try {
        // El servidor devuelve { secreto, uri, qr } (qr = imagen lista para <img>).
        const datos = await PicksyAPI.configurar2FA();

        if (!String(datos.qr || "").startsWith("data:image/svg+xml;base64,")) {
            throw new Error("El servidor devolvió un QR no válido.");
        }

        const imagen = document.createElement("img");
        imagen.src = datos.qr;
        imagen.alt = "Código QR para Google Authenticator";
        imagen.width = 170;
        imagen.height = 170;
        qrPlaceholder.replaceChildren(imagen);
        secretPlaceholder.textContent = datos.secreto;

        setupSection.hidden = false;
        setupCode.value = "";
        mostrarMensaje("Escanea el QR con Google Authenticator y escribe el código de 6 dígitos.");
        setupSection.scrollIntoView({ behavior: "smooth", block: "start" });

    } catch (error) {
        mostrarMensaje(error.message || "No fue posible generar el QR.", true);
    } finally {
        startSetupButton.disabled = false;
    }
});

setupCode?.addEventListener("input", () => {
    setupCode.value = setupCode.value.replace(/\D/g, "").slice(0, 6);
    setupCodeError.textContent = "";
    setupCode.classList.remove("invalid");
});

setupForm?.addEventListener("submit", async (event) => {
    event.preventDefault();

    const code = setupCode.value.trim();

    if (!/^\d{6}$/.test(code)) {
        setupCodeError.textContent =
            "Introduce un código de seis dígitos.";

        setupCode.classList.add("invalid");
        return;
    }

    const boton = setupForm.querySelector('button[type="submit"]');
    boton.disabled = true;

    try {
        await PicksyAPI.activar2FA(code);
        mostrarEstado(true);
        mostrarMensaje("¡Listo! La verificación en dos pasos quedó activada.");
    } catch (error) {
        setupCodeError.textContent = error.message || "No fue posible verificar el código.";
        setupCode.classList.add("invalid");
    } finally {
        boton.disabled = false;
    }
});

// ---- Desactivar ----
startDisableButton?.addEventListener("click", () => {
    disableSection.hidden = false;
    disablePassword.focus();
});

disableCode?.addEventListener("input", () => {
    disableError.textContent = "";
    disableCode.classList.remove("invalid");
});

disableForm?.addEventListener("submit", async (event) => {
    event.preventDefault();

    const codigo = limpiarCodigo(disableCode.value);

    if (!disablePassword.value) {
        disableError.textContent = "Escribe tu contraseña.";
        return;
    }
    if (!/^\d{6}$/.test(codigo)) {
        disableError.textContent = "Introduce un código de seis dígitos.";
        disableCode.classList.add("invalid");
        return;
    }

    const boton = disableForm.querySelector('button[type="submit"]');
    boton.disabled = true;

    try {
        await PicksyAPI.desactivar2FA(disablePassword.value, codigo);
        disablePassword.value = "";
        disableCode.value = "";
        mostrarEstado(false);
        mostrarMensaje("La verificación en dos pasos fue desactivada.");
    } catch (error) {
        disableError.textContent = error.message || "No fue posible desactivar el 2FA.";
    } finally {
        boton.disabled = false;
    }
});

iniciar();

/*
  Códigos de recuperación (#recoverySection): el backend todavía no los genera,
  por eso esa sección sigue oculta.
*/