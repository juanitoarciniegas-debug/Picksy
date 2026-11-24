
"use strict";

// ============================================
// PICKSY - CENTRO DE SOPORTE
// Roles permitidos: soporte y admin
// ============================================

const $ = (selector) => document.querySelector(selector);

const LIMITE_PAGINA = 20;

let usuarioSesion = null;
let paginaActual = 1;
let totalUsuarios = 0;
let consultaActual = "";
let usuarioSeleccionado = null;

const formulario = $("#soporteSearchForm");
const campoBusqueda = $("#soporteQuery");
const tablaUsuarios = $("#soporteUsuarios");
const feedback = $("#soporteFeedback");
const feedbackAccion = $("#soporteAccionFeedback");

const modal = $("#soporteModal");
const ficha = $("#soporteFicha");

const botonAnterior = $("#soporteAnterior");
const botonSiguiente = $("#soporteSiguiente");

// --------------------------------------------
// Utilidades
// --------------------------------------------

function escaparHTML(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, (caracter) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[caracter]);
}

function mostrarFeedback(mensaje, error = false) {
  feedback.textContent = mensaje;
  feedback.classList.toggle("error", error);
}

function mostrarFeedbackAccion(mensaje, error = false) {
  feedbackAccion.textContent = mensaje;
  feedbackAccion.classList.toggle("error", error);
}

function formatearFecha(fechaISO) {
  if (!fechaISO) return "No disponible";

  const fecha = new Date(fechaISO);

  if (Number.isNaN(fecha.getTime())) {
    return "No disponible";
  }

  return fecha.toLocaleString("es-CO", {
    dateStyle: "medium",
    timeStyle: "short"
  });
}

// --------------------------------------------
// Validación del rol
// --------------------------------------------

async function verificarAccesoSoporte() {
  if (!PicksyAPI.exigirSesion()) return false;

  try {
    usuarioSesion = await PicksyAPI.usuarioActual();

    if (!usuarioSesion) {
      location.replace("login.html");
      return false;
    }

    const rolesPermitidos = ["soporte", "admin"];

    if (!rolesPermitidos.includes(usuarioSesion.rol)) {
      mostrarFeedback("No tienes permisos para acceder al centro de soporte.", true);

      setTimeout(() => {
        location.replace("index.html");
      }, 1800);

      return false;
    }

    return true;

  } catch (error) {
    mostrarFeedback(error.message || "No se pudo verificar tu sesión.", true);
    return false;
  }
}

// --------------------------------------------
// Listado y paginación
// --------------------------------------------

function actualizarPaginacion() {
  const paginas = Math.max(1, Math.ceil(totalUsuarios / LIMITE_PAGINA));

  $("#soportePagina").textContent = `Página ${paginaActual} de ${paginas}`;

  botonAnterior.disabled = paginaActual <= 1;
  botonSiguiente.disabled = paginaActual >= paginas;

  $("#soporteTotal").textContent =
    `${totalUsuarios} usuario${totalUsuarios === 1 ? "" : "s"} encontrado${totalUsuarios === 1 ? "" : "s"}.`;
}

function mostrarCargandoTabla(mensaje = "Cargando usuarios...") {
  tablaUsuarios.replaceChildren();

  const fila = document.createElement("tr");
  const celda = document.createElement("td");

  celda.colSpan = 5;
  celda.textContent = mensaje;

  fila.appendChild(celda);
  tablaUsuarios.appendChild(fila);
}

function renderizarUsuarios(usuarios) {
  tablaUsuarios.replaceChildren();

  if (!Array.isArray(usuarios) || usuarios.length === 0) {
    mostrarCargandoTabla("No se encontraron usuarios.");
    return;
  }

  usuarios.forEach((usuario) => {
    const fila = document.createElement("tr");

    fila.dataset.id = String(usuario.id);
    fila.tabIndex = 0;
    fila.setAttribute("role", "button");
    fila.setAttribute("aria-label", `Consultar usuario ${usuario.correo}`);
    fila.classList.add("soporte-fila");

    const valores = [
      usuario.correo,
      usuario.rol,
      usuario.dos_factores ? "Activado" : "Desactivado",
      usuario.membresia_activa ? "Activa" : "Inactiva",
      formatearFecha(usuario.creado_en)
    ];

    valores.forEach((valor) => {
      const celda = document.createElement("td");
      celda.textContent = valor;
      fila.appendChild(celda);
    });

    fila.addEventListener("click", () => abrirFicha(usuario.id));

    fila.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        abrirFicha(usuario.id);
      }
    });

    tablaUsuarios.appendChild(fila);
  });
}

async function cargarUsuarios() {
  mostrarFeedback("");
  mostrarCargandoTabla();

  try {
    const respuesta = await PicksyAPI.listarUsuariosSoporte(
      consultaActual,
      paginaActual,
      LIMITE_PAGINA
    );

    const usuarios = Array.isArray(respuesta) ? respuesta : [];

    // api.js agrega .total a los arreglos cuando recibe X-Total-Count.
    totalUsuarios = Number(respuesta.total ?? usuarios.length);

    renderizarUsuarios(usuarios);
    actualizarPaginacion();

  } catch (error) {
    mostrarCargandoTabla("No fue posible cargar los usuarios.");
    mostrarFeedback(error.message || "Error al consultar usuarios.", true);
    totalUsuarios = 0;
    actualizarPaginacion();
  }
}

// --------------------------------------------
// Ficha del usuario
// --------------------------------------------

function abrirModal() {
  modal.classList.remove("hidden");
  document.body.classList.add("modal-open");
}

function cerrarModal() {
  modal.classList.add("hidden");
  document.body.classList.remove("modal-open");

  usuarioSeleccionado = null;
  ficha.replaceChildren();
  mostrarFeedbackAccion("");
}

function renderizarFicha(usuario) {
  const membresia = usuario.membresia || {};

  ficha.innerHTML = `
    <div class="soporte-ficha-grid">
      <div>
        <span class="muted">Correo</span>
        <strong>${escaparHTML(usuario.correo)}</strong>
      </div>

      <div>
        <span class="muted">Rol</span>
        <strong>${escaparHTML(usuario.rol)}</strong>
      </div>

      <div>
        <span class="muted">Verificación 2FA</span>
        <strong>${usuario.dos_factores ? "Activada" : "Desactivada"}</strong>
      </div>

      <div>
        <span class="muted">Cuenta creada</span>
        <strong>${escaparHTML(formatearFecha(usuario.creado_en))}</strong>
      </div>

      <div>
        <span class="muted">Membresía</span>
        <strong>${membresia.activa ? "Activa" : "Inactiva"}</strong>
      </div>

      <div>
        <span class="muted">Plan</span>
        <strong>${escaparHTML(membresia.plan || "Sin plan")}</strong>
      </div>

      <div>
        <span class="muted">Vencimiento</span>
        <strong>${escaparHTML(formatearFecha(membresia.vence_en))}</strong>
      </div>

      <div>
        <span class="muted">Búsquedas de hoy</span>
        <strong>${Number(usuario.busquedas_hoy || 0)}</strong>
      </div>

      <div>
        <span class="muted">Sesiones abiertas</span>
        <strong>${Number(usuario.sesiones_abiertas || 0)}</strong>
      </div>
    </div>
  `;

  const botones = [
    $("#soporteDesbloquear"),
    $("#soporteCerrarSesiones")
  ];

  // Soporte no puede gestionar cuentas de administradores.
  // El administrador sí puede consultar y gestionar esas cuentas.
  const esAdministrador = usuario.rol === "admin";
  const esSoporte = usuarioSesion.rol === "soporte";

  botones.forEach((boton) => {
    boton.classList.toggle("hidden", esAdministrador && esSoporte);
    boton.disabled = false;
  });

  if (esAdministrador && esSoporte) {
    mostrarFeedbackAccion(
      "No puedes gestionar cuentas de administrador.",
      true
    );
  } else {
    mostrarFeedbackAccion("");
  }
}

async function abrirFicha(id) {
  usuarioSeleccionado = { id };

  ficha.textContent = "Cargando información...";
  mostrarFeedbackAccion("");

  $("#soporteDesbloquear").disabled = true;
  $("#soporteCerrarSesiones").disabled = true;

  abrirModal();

  try {
    const usuario = await PicksyAPI.verUsuarioSoporte(id);

    usuarioSeleccionado = usuario;

    renderizarFicha(usuario);

  } catch (error) {
    ficha.textContent = "No fue posible cargar la ficha del usuario.";
    mostrarFeedbackAccion(error.message, true);
  }
}

// --------------------------------------------
// Acciones de soporte
// --------------------------------------------

async function ejecutarAccion(tipo) {
  if (!usuarioSeleccionado?.id) return;

  const id = usuarioSeleccionado.id;

  const esDesbloqueo = tipo === "desbloquear";

  const pregunta = esDesbloqueo
    ? "¿Deseas desbloquear esta cuenta?"
    : "¿Deseas cerrar todas las sesiones abiertas de esta cuenta?";

  if (!confirm(pregunta)) return;

  const botones = [
    $("#soporteDesbloquear"),
    $("#soporteCerrarSesiones")
  ];

  botones.forEach((boton) => {
    boton.disabled = true;
  });

  mostrarFeedbackAccion("Procesando solicitud...");

  try {
    let respuesta;

    if (esDesbloqueo) {
      respuesta = await PicksyAPI.desbloquearUsuarioSoporte(id);
    } else {
      respuesta = await PicksyAPI.cerrarSesionesSoporte(id);
    }

    const mensaje = esDesbloqueo
      ? (respuesta.desbloqueado
          ? "La cuenta fue desbloqueada correctamente."
          : "La solicitud fue procesada.")
      : `Sesiones cerradas: ${Number(respuesta.sesiones_cerradas || 0)}.`;

    mostrarFeedbackAccion(mensaje);

    // Actualizar la ficha para mostrar el estado más reciente.
    const usuarioActualizado = await PicksyAPI.verUsuarioSoporte(id);

    usuarioSeleccionado = usuarioActualizado;
    renderizarFicha(usuarioActualizado);

    mostrarFeedbackAccion(mensaje);

    await cargarUsuarios();

  } catch (error) {
    mostrarFeedbackAccion(
      error.message || "No fue posible completar la operación.",
      true
    );

    botones.forEach((boton) => {
      boton.disabled = false;
    });
  }
}

// --------------------------------------------
// Eventos
// --------------------------------------------

formulario.addEventListener("submit", async (event) => {
  event.preventDefault();

  consultaActual = campoBusqueda.value.trim();
  paginaActual = 1;

  await cargarUsuarios();
});

botonAnterior.addEventListener("click", async () => {
  if (paginaActual <= 1) return;

  paginaActual--;
  await cargarUsuarios();
});

botonSiguiente.addEventListener("click", async () => {
  const paginas = Math.max(1, Math.ceil(totalUsuarios / LIMITE_PAGINA));

  if (paginaActual >= paginas) return;

  paginaActual++;
  await cargarUsuarios();
});

$("#soporteCerrarModal").addEventListener("click", cerrarModal);

modal.addEventListener("click", (event) => {
  if (event.target === modal) cerrarModal();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !modal.classList.contains("hidden")) {
    cerrarModal();
  }
});

$("#soporteDesbloquear").addEventListener("click", () => {
  ejecutarAccion("desbloquear");
});

$("#soporteCerrarSesiones").addEventListener("click", () => {
  ejecutarAccion("cerrar-sesiones");
});

// --------------------------------------------
// Inicio
// --------------------------------------------

(async function iniciarSoporte() {
  const autorizado = await verificarAccesoSoporte();

  if (!autorizado) return;

  await cargarUsuarios();
})();
