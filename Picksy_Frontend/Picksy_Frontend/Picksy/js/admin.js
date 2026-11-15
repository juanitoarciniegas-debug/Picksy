// CAMBIO (roles): página nueva del panel de administrador. Solo funciona con rol "admin".
// Usa los endpoints GET /admin/usuarios, PATCH /admin/usuarios/{id}/rol y DELETE /admin/usuarios/{id}.

const cuerpo = document.querySelector("#cuerpoUsuarios");
const feedback = document.querySelector("#adminFeedback");
const total = document.querySelector("#totalUsuarios");
let yo = null;   // el administrador que tiene la sesión abierta

function mensaje(texto, esError = false) {
    feedback.textContent = texto;
    feedback.style.color = esError ? "#B54E51" : "#65854C";
}

function boton(texto, clase, accion, desactivado = false) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "button button-secondary " + clase;
    b.textContent = texto;
    b.disabled = desactivado;
    b.addEventListener("click", accion);
    return b;
}

function celda(fila, contenido) {
    const td = document.createElement("td");
    if (contenido instanceof Node) td.appendChild(contenido);
    else td.textContent = contenido;     // textContent: nunca se interpreta como HTML
    fila.appendChild(td);
    return td;
}

async function cargar() {
    const usuarios = await PicksyAPI.listarUsuarios();
    cuerpo.replaceChildren();

    for (const u of usuarios) {
        const fila = document.createElement("tr");
        const esYo = u.id === yo.id;

        celda(fila, esYo ? `${u.correo} (tú)` : u.correo);

        const rol = document.createElement("span");
        rol.className = "etiqueta-rol" + (u.rol === "admin" ? " admin" : "");
        rol.textContent = u.rol === "admin" ? "Administrador" : "Usuario";
        celda(fila, rol);

        celda(fila, u.dos_factores ? "Activada" : "Pendiente");
        celda(fila, new Date(u.creado_en).toLocaleDateString("es-CO"));

        const acciones = document.createElement("div");
        acciones.className = "acciones";
        const nuevoRol = u.rol === "admin" ? "usuario" : "admin";
        acciones.appendChild(boton(
            u.rol === "admin" ? "Quitar admin" : "Hacer admin", "", () => cambiarRol(u, nuevoRol), esYo));
        acciones.appendChild(boton("Eliminar", "boton-peligro", () => eliminar(u), esYo));
        celda(fila, acciones);

        cuerpo.appendChild(fila);
    }
    total.textContent = `${usuarios.length} cuenta(s) en total.`;
}

async function cambiarRol(u, rol) {
    if (!window.confirm(`¿Cambiar el rol de ${u.correo} a ${rol === "admin" ? "administrador" : "usuario"}?`)) return;
    try {
        await PicksyAPI.cambiarRol(u.id, rol);
        mensaje("Rol actualizado.");
        await cargar();
    } catch (error) {
        mensaje(error.message, true);
    }
}

async function eliminar(u) {
    if (!window.confirm(`¿Eliminar la cuenta ${u.correo}? También se borrará su historial. Esto no se puede deshacer.`)) return;
    try {
        await PicksyAPI.eliminarUsuario(u.id);
        mensaje(`Cuenta ${u.correo} eliminada.`);
        await cargar();
    } catch (error) {
        mensaje(error.message, true);
    }
}

(async function iniciar() {
    if (typeof PicksyAPI === "undefined") {
        mensaje("No se pudo cargar la conexión con el servidor.", true);
        return;
    }
    try {
        yo = await PicksyAPI.usuarioActual();
        if (!yo) return;                                   // api.js ya manda al login
        if (yo.rol !== "admin") {                          // un usuario normal no entra aquí
            window.location.replace("index.html");
            return;
        }
        await cargar();
    } catch (error) {
        mensaje(error.message || "No se pudo cargar la lista de usuarios.", true);
    }
})();
