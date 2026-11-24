
/* ==========================================
   PICKSY - ADMINISTRACIÓN DE USUARIOS
   ========================================== */

/*
    Roles disponibles en el sistema.

    Los valores de "value" son los que se envían
    al backend. Los textos son los que ve el usuario.
*/

const ROLES = [
    { value: "usuario", label: "Usuario" },
    { value: "premium", label: "Premium" },
    { value: "soporte", label: "Soporte" },
    { value: "analista", label: "Analista" },
    { value: "moderador_tiendas", label: "Moderador de tiendas" },
    { value: "admin", label: "Administrador" }
];


/* ==========================================
   ELEMENTOS DEL DOM
========================================== */

const cuerpo = document.querySelector("#cuerpoUsuarios");
const feedback = document.querySelector("#adminFeedback");
const total = document.querySelector("#totalUsuarios");

let yo = null;


/* ==========================================
   MENSAJES
========================================== */

function mensaje(texto, esError = false) {
    feedback.textContent = texto;
    feedback.style.color = esError ? "#B54E51" : "#65854C";
}


/* ==========================================
   CREACIÓN DE ELEMENTOS
========================================== */

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

    if (contenido instanceof Node) {
        td.appendChild(contenido);
    } else {
        td.textContent = contenido ?? "";
    }

    fila.appendChild(td);

    return td;
}


/* ==========================================
   ETIQUETA DEL ROL
========================================== */

function crearEtiquetaRol(rol) {
    const etiqueta = document.createElement("span");

    etiqueta.className = "etiqueta-rol";

    const nombres = {
        usuario: "Usuario",
        premium: "Premium",
        soporte: "Soporte",
        analista: "Analista",
        moderador_tiendas: "Moderador de tiendas",
        admin: "Administrador"
    };

    etiqueta.textContent = nombres[rol] || rol;

    if (rol === "admin") {
        etiqueta.classList.add("admin");
    }

    if (rol === "premium") {
        etiqueta.classList.add("premium");
    }

    return etiqueta;
}


/* ==========================================
   SELECTOR DE ROLES
========================================== */

function crearSelectorRol(usuario) {
    const selector = document.createElement("select");

    selector.className = "admin-selector-rol";
    selector.setAttribute(
        "aria-label",
        `Cambiar rol de ${usuario.correo}`
    );

    for (const rol of ROLES) {
        const opcion = document.createElement("option");

        opcion.value = rol.value;
        opcion.textContent = rol.label;

        if (rol.value === usuario.rol) {
            opcion.selected = true;
        }

        selector.appendChild(opcion);
    }

    // Un administrador no puede cambiar su propio rol.
    selector.disabled = usuario.id === yo.id;

    return selector;
}


/* ==========================================
   CARGAR USUARIOS
========================================== */

async function cargar() {
    cuerpo.replaceChildren();

    const filaCarga = document.createElement("tr");
    const celdaCarga = document.createElement("td");

    celdaCarga.colSpan = 6;
    celdaCarga.textContent = "Cargando usuarios...";

    filaCarga.appendChild(celdaCarga);
    cuerpo.appendChild(filaCarga);

    const usuarios = await PicksyAPI.listarUsuarios();

    cuerpo.replaceChildren();

    if (!Array.isArray(usuarios)) {
        throw new Error("El servidor devolvió una lista de usuarios inválida.");
    }

    if (usuarios.length === 0) {
        const filaVacia = document.createElement("tr");
        const celdaVacia = document.createElement("td");

        celdaVacia.colSpan = 6;
        celdaVacia.textContent = "No hay usuarios registrados.";

        filaVacia.appendChild(celdaVacia);
        cuerpo.appendChild(filaVacia);

        total.textContent = "0 cuentas en total.";

        return;
    }

    for (const u of usuarios) {
        const fila = document.createElement("tr");

        const esYo = u.id === yo.id;

        // Correo
        celda(
            fila,
            esYo ? `${u.correo} (tú)` : u.correo
        );

        // Rol actual
        celda(fila, crearEtiquetaRol(u.rol));

        // Selector para elegir el nuevo rol
        const selector = crearSelectorRol(u);
        celda(fila, selector);

        // Verificación en dos pasos
        celda(
            fila,
            u.dos_factores ? "Activada" : "Pendiente"
        );

        // Fecha de creación
        const fecha = u.creado_en
            ? new Date(u.creado_en).toLocaleDateString("es-CO")
            : "No disponible";

        celda(fila, fecha);

        // Acciones
        const acciones = document.createElement("div");
        acciones.className = "acciones";

        const botonGuardar = boton(
            "Guardar rol",
            "boton-guardar-rol",
            () => cambiarRol(u, selector.value, botonGuardar, selector),
            esYo
        );

        const botonEliminar = boton(
            "Eliminar",
            "boton-peligro",
            () => eliminar(u, botonEliminar),
            esYo
        );

        // Evitar guardar si no se ha seleccionado un rol diferente.
        selector.addEventListener("change", () => {
            botonGuardar.disabled =
                esYo || selector.value === u.rol;
        });

        botonGuardar.disabled = true;

        acciones.appendChild(botonGuardar);
        acciones.appendChild(botonEliminar);

        celda(fila, acciones);

        cuerpo.appendChild(fila);
    }

    total.textContent = `${usuarios.length} cuenta(s) en total.`;
}


/* ==========================================
   CAMBIAR ROL
========================================== */

async function cambiarRol(usuario, nuevoRol, botonGuardar, selector) {
    if (!ROLES.some(rol => rol.value === nuevoRol)) {
        mensaje("El rol seleccionado no es válido.", true);
        return;
    }

    if (nuevoRol === usuario.rol) {
        mensaje("El usuario ya tiene ese rol.", true);
        return;
    }

    const nombreRol = ROLES.find(
        rol => rol.value === nuevoRol
    ).label;

    const confirmar = window.confirm(
        `¿Cambiar el rol de ${usuario.correo} a ${nombreRol}?`
    );

    if (!confirmar) {
        selector.value = usuario.rol;
        botonGuardar.disabled = true;
        return;
    }

    try {
        botonGuardar.disabled = true;
        botonGuardar.textContent = "Guardando...";

        await PicksyAPI.cambiarRol(usuario.id, nuevoRol);

        mensaje(`El rol de ${usuario.correo} ahora es ${nombreRol}.`);

        await cargar();

    } catch (error) {
        mensaje(
            error.mensaje || error.message ||
            "No se pudo actualizar el rol.",
            true
        );

        botonGuardar.disabled = false;
        botonGuardar.textContent = "Guardar rol";
    }
}


/* ==========================================
   ELIMINAR USUARIO
========================================== */

async function eliminar(usuario, botonEliminar) {
    if (usuario.id === yo.id) {
        mensaje("No puedes eliminar tu propia cuenta desde aquí.", true);
        return;
    }

    const confirmar = window.confirm(
        `¿Eliminar la cuenta ${usuario.correo}?\n\n` +
        "También se eliminará su historial. Esta acción no se puede deshacer."
    );

    if (!confirmar) return;

    try {
        botonEliminar.disabled = true;
        botonEliminar.textContent = "Eliminando...";

        await PicksyAPI.eliminarUsuario(usuario.id);

        mensaje(`La cuenta ${usuario.correo} fue eliminada.`);

        await cargar();

    } catch (error) {
        mensaje(
            error.mensaje || error.message ||
            "No se pudo eliminar la cuenta.",
            true
        );

        botonEliminar.disabled = false;
        botonEliminar.textContent = "Eliminar";
    }
}


/* ==========================================
   INICIALIZACIÓN
========================================== */

async function iniciar() {
    if (typeof PicksyAPI === "undefined") {
        mensaje("No se pudo cargar la conexión con el servidor.", true);
        return;
    }

    try {
        yo = await PicksyAPI.usuarioActual();

        if (!yo) {
            // api.js debe gestionar la redirección al login.
            return;
        }

        if (yo.rol !== "admin") {
            window.location.replace("index.html");
            return;
        }

        await cargar();

    } catch (error) {
        mensaje(
            error.mensaje || error.message ||
            "No se pudo cargar la lista de usuarios.",
            true
        );
    }
}

iniciar();
