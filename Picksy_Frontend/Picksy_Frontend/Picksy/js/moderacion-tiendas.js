
"use strict";

// ============================================
// PICKSY - MODERACIÓN DE TIENDAS
// Roles permitidos: moderador_tiendas y admin
// ============================================

const $ = (selector) => document.querySelector(selector);

const contenedor = $("#tiendasLista");
const feedback = $("#moderacionFeedback");

let tiendas = [];

function mostrarMensaje(mensaje, error = false) {
  feedback.textContent = mensaje;
  feedback.classList.toggle("error", error);
}

// --------------------------------------------
// Validación de acceso
// --------------------------------------------

async function verificarAccesoModeracion() {
  if (!PicksyAPI.exigirSesion()) return false;

  try {
    const usuario = await PicksyAPI.usuarioActual();

    if (!usuario) {
      location.replace("login.html");
      return false;
    }

    if (!["moderador_tiendas", "admin"].includes(usuario.rol)) {
      mostrarMensaje("No tienes permisos para moderar tiendas.", true);

      setTimeout(() => {
        location.replace("index.html");
      }, 1800);

      return false;
    }

    return true;

  } catch (error) {
    mostrarMensaje(error.message || "No se pudo verificar tu sesión.", true);
    return false;
  }
}

// --------------------------------------------
// Utilidades
// --------------------------------------------

function crearEnlaceSeguro(url) {
  try {
    const direccion = new URL(url);

    if (!["https:", "http:"].includes(direccion.protocol)) {
      return null;
    }

    return direccion.href;

  } catch {
    return null;
  }
}

// --------------------------------------------
// Renderizado de tiendas
// --------------------------------------------

function crearTarjeta(tienda) {
  const tarjeta = document.createElement("article");
  tarjeta.className = "tienda-card";

  const titulo = document.createElement("h3");
  titulo.textContent = tienda.nombre;

  const enlace = document.createElement("a");
  const url = crearEnlaceSeguro(tienda.sitio_web);

  if (url) {
    enlace.href = url;
    enlace.target = "_blank";
    enlace.rel = "noopener noreferrer";
    enlace.textContent = tienda.sitio_web;
  } else {
    enlace.textContent = "Sitio web no disponible";
  }

  const estado = document.createElement("div");
  estado.className = "tienda-estado";

  const textoEstado = document.createElement("span");
  textoEstado.className = "tienda-estado-texto";
  textoEstado.textContent = tienda.activa ? "Activa" : "Inactiva";

  const etiqueta = document.createElement("label");
  etiqueta.className = "tienda-switch";

  const interruptor = document.createElement("input");
  interruptor.type = "checkbox";
  interruptor.checked = tienda.activa === true;
  interruptor.setAttribute(
    "aria-label",
    `Activar o desactivar ${tienda.nombre}`
  );

  const textoInterruptor = document.createElement("span");
  textoInterruptor.textContent = "Activa";

  interruptor.addEventListener("change", () => {
    cambiarEstadoTienda(tienda, interruptor, textoEstado);
  });

  etiqueta.append(interruptor, textoInterruptor);
  estado.append(textoEstado, etiqueta);

  tarjeta.append(titulo, enlace, estado);

  return tarjeta;
}

function renderizarTiendas() {
  contenedor.replaceChildren();

  if (!tiendas.length) {
    const mensaje = document.createElement("p");
    mensaje.textContent = "No hay tiendas registradas.";
    contenedor.appendChild(mensaje);
    return;
  }

  tiendas.forEach((tienda) => {
    contenedor.appendChild(crearTarjeta(tienda));
  });
}

// --------------------------------------------
// Cargar tiendas
// --------------------------------------------

async function cargarTiendas() {
  contenedor.textContent = "Cargando tiendas...";
  mostrarMensaje("");

  try {
    const respuesta = await PicksyAPI.listarTiendasModeracion();

    tiendas = Array.isArray(respuesta) ? respuesta : [];

    renderizarTiendas();

    mostrarMensaje(`${tiendas.length} tiendas encontradas.`);

  } catch (error) {
    contenedor.textContent = "No fue posible cargar las tiendas.";
    mostrarMensaje(
      error.message || "Error al consultar las tiendas.",
      true
    );
  }
}

// --------------------------------------------
// Cambiar estado
// --------------------------------------------

async function cambiarEstadoTienda(tienda, interruptor, textoEstado) {
  const estadoAnterior = tienda.activa;
  const nuevoEstado = interruptor.checked;

  interruptor.disabled = true;
  mostrarMensaje(`Actualizando ${tienda.nombre}...`);

  try {
    const respuesta = await PicksyAPI.actualizarTiendaModeracion(
      tienda.id,
      nuevoEstado
    );

    // Actualizar el estado local con la respuesta del backend.
    tienda.activa = respuesta.activa;

    interruptor.checked = respuesta.activa;
    textoEstado.textContent = respuesta.activa ? "Activa" : "Inactiva";

    mostrarMensaje(
      `${respuesta.nombre || tienda.nombre} ${
        respuesta.activa ? "activada" : "desactivada"
      } correctamente.`
    );

  } catch (error) {
    // Si falla el backend, restaurar el estado original.
    interruptor.checked = estadoAnterior;
    tienda.activa = estadoAnterior;

    textoEstado.textContent = estadoAnterior ? "Activa" : "Inactiva";

    mostrarMensaje(
      error.message || "No se pudo actualizar el estado de la tienda.",
      true
    );

  } finally {
    interruptor.disabled = false;
  }
}

// --------------------------------------------
// Inicio
// --------------------------------------------

(async function iniciarModeracion() {
  const autorizado = await verificarAccesoModeracion();

  if (!autorizado) return;

  await cargarTiendas();
})();
