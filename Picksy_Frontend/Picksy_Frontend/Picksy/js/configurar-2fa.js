// CAMBIO (2FA obligatorio): página nueva. Sirve para dos casos:
//   A) Cuenta NUEVA: registro.js guardó en sessionStorage "picksy2FARegistro" lo que devolvió POST /auth/registro
//      (token_registro, qr, secreto). Aquí se escanea el QR y, con un código correcto, el servidor CREA la cuenta.
//   B) Cuenta ANTIGUA sin Authenticator: login.js guardó "picksy2FAChallenge" (+ "picksy2FAConfigurar").
//      Aquí se pide el QR al servidor, se escanea y, con un código correcto, se entra a la página principal.

const form = document.querySelector("#configForm");
const authCode = document.querySelector("#authCode");
const authCodeError = document.querySelector("#authCodeError");
const feedback = document.querySelector("#configFeedback");
const boton = document.querySelector("#botonConfirmar");
const qrImagen = document.querySelector("#qrImagen");
const qrCargando = document.querySelector("#qrCargando");
const claveManual = document.querySelector("#claveManual");

let registro = null;   // caso A
try { registro = JSON.parse(sessionStorage.getItem("picksy2FARegistro") || "null"); } catch { registro = null; }
const challenge = sessionStorage.getItem("picksy2FAChallenge");
const esCuentaAntigua = !registro && challenge && sessionStorage.getItem("picksy2FAConfigurar") === "1";

function mensaje(texto, esError = false) {
    feedback.textContent = texto;
    feedback.style.color = esError ? "#B54E51" : "#65854C";
}

function mostrarQr(datos) {
    qrImagen.src = datos.qr;
    qrImagen.hidden = false;
    qrCargando.hidden = true;
    claveManual.textContent = datos.secreto;
}

function limpiarEstado() {
    sessionStorage.removeItem("picksy2FARegistro");
    sessionStorage.removeItem("picksy2FAChallenge");
    sessionStorage.removeItem("picksy2FARecordar");
    sessionStorage.removeItem("picksy2FAConfigurar");
}

async function iniciar() {
    if (typeof PicksyAPI === "undefined") {
        mensaje("No se pudo cargar la conexión con el servidor.", true);
        return;
    }
    if (registro) {
        document.querySelector("#etiqueta").textContent = "Último paso del registro";
        mostrarQr(registro);
        boton.textContent = "Crear mi cuenta";
    } else if (esCuentaAntigua) {
        document.querySelector("#etiqueta").textContent = "Protege tu cuenta";
        boton.textContent = "Activar e ingresar";
        try {
            mostrarQr(await PicksyAPI.configurarPendiente2FA(challenge));
        } catch (error) {
            mensaje(error.message, true);
            boton.disabled = true;
            window.setTimeout(() => { limpiarEstado(); window.location.replace("login.html"); }, 3000);
        }
    } else {
        window.location.replace("login.html");   // no hay nada pendiente por configurar
    }
}

// CAMBIO (backend): muestra los códigos de recuperación (solo se ven esta vez) y espera a que la persona confirme.
function mostrarCodigos(codigos, destino) {
    if (!Array.isArray(codigos) || codigos.length === 0) {     // por si el servidor no los envía
        window.location.replace(destino);
        return;
    }
    document.querySelector("#configForm").hidden = true;
    document.querySelector(".pasos").hidden = true;
    document.querySelector(".qr-caja").hidden = true;
    document.querySelector("#volver").hidden = true;
    document.querySelector("#etiqueta").hidden = true;
    document.querySelector("#titulo").hidden = true;
    document.querySelector("#codigosPanel").hidden = false;

    const lista = document.querySelector("#codigosLista");
    lista.replaceChildren(...codigos.map((c) => {
        const li = document.createElement("li");
        li.textContent = c;                   // textContent: nunca se interpreta como HTML
        return li;
    }));
    const texto = "Códigos de recuperación de Picksy (cada uno sirve una sola vez):\n\n" + codigos.join("\n") + "\n";

    document.querySelector("#copiarCodigos").addEventListener("click", async () => {
        try {
            await navigator.clipboard.writeText(codigos.join("\n"));
            document.querySelector("#copiarCodigos").textContent = "¡Copiados!";
        } catch {
            document.querySelector("#copiarCodigos").textContent = "Selecciónalos y cópialos a mano";
        }
    });
    document.querySelector("#descargarCodigos").addEventListener("click", () => {
        const enlace = document.createElement("a");
        enlace.href = URL.createObjectURL(new Blob([texto], { type: "text/plain;charset=utf-8" }));
        enlace.download = "picksy-codigos-de-recuperacion.txt";
        enlace.click();
        URL.revokeObjectURL(enlace.href);
    });
    const guardados = document.querySelector("#codigosGuardados");
    const continuar = document.querySelector("#codigosContinuar");
    guardados.addEventListener("change", () => { continuar.disabled = !guardados.checked; });
    continuar.addEventListener("click", () => window.location.replace(destino));
}

authCode?.addEventListener("input", () => {
    authCode.value = authCode.value.replace(/[^\d\s]/g, "").slice(0, 7);
    authCodeError.textContent = "";
    authCode.classList.remove("invalid");
});

form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const codigo = authCode.value.replace(/\s/g, "");

    if (!/^\d{6}$/.test(codigo)) {
        authCodeError.textContent = "Introduce un código válido de seis dígitos.";
        authCode.classList.add("invalid");
        return;
    }

    boton.disabled = true;
    mensaje("Verificando código...");

    try {
        if (registro) {
            const creada = await PicksyAPI.confirmarRegistro(registro.token_registro, codigo);
            limpiarEstado();
            // CAMBIO (backend): el servidor entrega los códigos de recuperación; se muestran antes de ir al login.
            mostrarCodigos(creada.codigos_recuperacion, "login.html");
        } else {
            const sesion = await PicksyAPI.activarPendiente2FA(challenge, codigo, sessionStorage.getItem("picksy2FARecordar") === "1");
            limpiarEstado();
            mostrarCodigos(sesion.codigos_recuperacion, "index.html");
        }
    } catch (error) {
        mensaje(error.message || "No fue posible verificar el código.", true);
        // Si el registro o el inicio de sesión venció, o se acabaron los intentos, hay que empezar de nuevo.
        if (/venció|Vuelve a/.test(error.message || "")) {
            limpiarEstado();
            window.setTimeout(() => window.location.replace(registro ? "registro.html" : "login.html"), 2500);
        } else {
            boton.disabled = false;
            authCode.select();
        }
    }
});

iniciar();
