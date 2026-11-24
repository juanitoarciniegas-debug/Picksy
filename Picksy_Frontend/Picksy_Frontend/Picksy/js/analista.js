
"use strict";

// ============================================
// PICKSY - PANEL DE ANALÍTICA
// Roles permitidos: analista y admin
// ============================================

const $ = (selector) => document.querySelector(selector);

const ROLES = [
  { id: "usuario", nombre: "Usuario", color: "#263D2B" },
  { id: "premium", nombre: "Premium", color: "#ECE99B" },
  { id: "soporte", nombre: "Soporte", color: "#91A98B" },
  { id: "analista", nombre: "Analista", color: "#B9C8A9" },
  { id: "moderador_tiendas", nombre: "Moderador de tiendas", color: "#D4DCCB" },
  { id: "admin", nombre: "Administrador", color: "#778075" }
];

const formatoNumero = new Intl.NumberFormat("es-CO");

const formatoPesos = new Intl.NumberFormat("es-CO", {
  style: "currency",
  currency: "COP",
  maximumFractionDigits: 0
});

const feedback = $("#analistaFeedback");
const selectorPeriodo = $("#periodoAnalista");

let resumenActual = null;

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

function mostrarMensaje(mensaje, error = false) {
  feedback.textContent = mensaje;
  feedback.classList.toggle("error", error);
}

function numero(valor) {
  const resultado = Number(valor ?? 0);
  return Number.isFinite(resultado) ? resultado : 0;
}

// --------------------------------------------
// Acceso por rol
// --------------------------------------------

async function verificarAccesoAnalista() {
  if (!PicksyAPI.exigirSesion()) return false;

  try {
    const usuario = await PicksyAPI.usuarioActual();

    if (!usuario) {
      location.replace("login.html");
      return false;
    }

    if (!["analista", "admin"].includes(usuario.rol)) {
      mostrarMensaje("No tienes permisos para acceder al panel de analítica.", true);

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
// Tarjetas de indicadores
// --------------------------------------------

function renderizarResumen(datos) {
  $("#kpiUsuarios").textContent =
    formatoNumero.format(numero(datos.usuarios_total));

  $("#kpiNuevos").textContent =
    formatoNumero.format(numero(datos.usuarios_nuevos_7_dias));

  $("#kpiMembresias").textContent =
    formatoNumero.format(numero(datos.membresias_activas));

  $("#kpiPagos").textContent =
    formatoNumero.format(numero(datos.pagos_confirmados));

  $("#kpiBusquedasHoy").textContent =
    formatoNumero.format(numero(datos.busquedas_hoy));

  $("#kpiBusquedasSemana").textContent =
    formatoNumero.format(numero(datos.busquedas_7_dias));

  $("#kpiIngresos").textContent =
    formatoPesos.format(numero(datos.ingresos_simulados));
}

// --------------------------------------------
// Gráfica de barras: búsquedas por día
// --------------------------------------------

function renderizarGraficaBusquedas(registros) {
  const contenedor = $("#graficaBusquedas");
  contenedor.replaceChildren();

  if (!Array.isArray(registros) || registros.length === 0) {
    contenedor.textContent = "No hay datos disponibles.";
    return;
  }

  const maximo = Math.max(
    1,
    ...registros.map((registro) => numero(registro.busquedas))
  );

  registros.forEach((registro) => {
    const cantidad = numero(registro.busquedas);
    const porcentaje = Math.max(0, (cantidad / maximo) * 100);

    const fecha = new Date(`${registro.dia}T12:00:00`);

    const etiqueta = Number.isNaN(fecha.getTime())
      ? registro.dia
      : fecha.toLocaleDateString("es-CO", {
          day: "2-digit",
          month: "short"
        });

    const columna = document.createElement("div");
    columna.className = "barra-dia";

    const valor = document.createElement("span");
    valor.className = "barra-valor";
    valor.textContent = formatoNumero.format(cantidad);

    const barra = document.createElement("div");
    barra.className = "barra-visual";
    barra.style.height = `${Math.max(3, porcentaje)}%`;
    barra.setAttribute("aria-label", `${cantidad} búsquedas`);

    const dia = document.createElement("span");
    dia.className = "barra-fecha";
    dia.textContent = etiqueta;

    columna.append(valor, barra, dia);
    contenedor.appendChild(columna);
  });
}

// --------------------------------------------
// Gráfica de dona: usuarios por rol
// --------------------------------------------

function renderizarGraficaRoles(datos) {
  const contenedor = $("#graficaRoles");
  const leyenda = $("#leyendaRoles");

  contenedor.style.background = "conic-gradient(#E7E9DF 0deg 360deg)";
  leyenda.replaceChildren();

  const cantidades = ROLES.map((rol) => ({
    ...rol,
    cantidad: numero(datos?.[rol.id])
  }));

  const total = cantidades.reduce(
    (suma, rol) => suma + rol.cantidad,
    0
  );

  $("#totalDona").textContent = formatoNumero.format(total);

  if (total === 0) {
    contenedor.style.background = "#E7E9DF";
  } else {
    let acumulado = 0;

    const segmentos = cantidades.map((rol) => {
      const inicio = acumulado;
      acumulado += (rol.cantidad / total) * 360;

      return `${rol.color} ${inicio}deg ${acumulado}deg`;
    });

    contenedor.style.background =
      `conic-gradient(${segmentos.join(", ")})`;
  }

  cantidades.forEach((rol) => {
    const elemento = document.createElement("div");
    elemento.className = "leyenda-rol";

    const punto = document.createElement("span");
    punto.className = "leyenda-color";
    punto.style.backgroundColor = rol.color;

    const nombre = document.createElement("span");
    nombre.textContent = rol.nombre;

    const cantidad = document.createElement("strong");
    cantidad.textContent = formatoNumero.format(rol.cantidad);

    elemento.append(punto, nombre, cantidad);
    leyenda.appendChild(elemento);
  });
}

// --------------------------------------------
// Rankings
// --------------------------------------------

function renderizarRanking(contenedor, elementos, campoNombre, campoValor, sufijo) {
  contenedor.replaceChildren();

  if (!Array.isArray(elementos) || elementos.length === 0) {
    const vacio = document.createElement("p");
    vacio.className = "muted";
    vacio.textContent = "No hay resultados para este periodo.";
    contenedor.appendChild(vacio);
    return;
  }

  elementos.forEach((elemento, indice) => {
    const fila = document.createElement("div");
    fila.className = "analista-ranking-item";

    const nombre = document.createElement("span");
    nombre.textContent =
      `${indice + 1}. ${elemento[campoNombre] ?? "Sin nombre"}`;

    const cantidad = document.createElement("strong");
    cantidad.textContent =
      `${formatoNumero.format(numero(elemento[campoValor]))} ${sufijo}`;

    fila.append(nombre, cantidad);
    contenedor.appendChild(fila);
  });
}

// --------------------------------------------
// Consultas a la API
// --------------------------------------------

async function cargarResumen() {
  mostrarMensaje("Cargando estadísticas...");

  try {
    const datos = await PicksyAPI.resumenAnalista();

    resumenActual = datos;

    renderizarResumen(datos);
    renderizarGraficaBusquedas(datos.busquedas_por_dia);
    renderizarGraficaRoles(datos.usuarios_por_rol);

    mostrarMensaje("");

  } catch (error) {
    mostrarMensaje(
      error.message || "No se pudo cargar el resumen.",
      true
    );
  }
}

async function cargarRankings(dias = 30) {
  const contenedorBusquedas = $("#rankingBusquedas");
  const contenedorTiendas = $("#rankingTiendas");

  contenedorBusquedas.textContent = "Cargando búsquedas...";
  contenedorTiendas.textContent = "Cargando tiendas...";

  try {
    const [populares, ganadoras] = await Promise.all([
      PicksyAPI.busquedasPopulares(dias, 10),
      PicksyAPI.tiendasGanadoras(dias, 10)
    ]);

    renderizarRanking(
      contenedorBusquedas,
      populares.busquedas,
      "termino",
      "veces",
      "búsquedas"
    );

    renderizarRanking(
      contenedorTiendas,
      ganadoras.tiendas,
      "tienda",
      "veces",
      "veces"
    );

    mostrarMensaje("");

  } catch (error) {
    contenedorBusquedas.textContent = "No fue posible cargar el ranking.";
    contenedorTiendas.textContent = "No fue posible cargar el ranking.";

    mostrarMensaje(
      error.message || "No se pudieron cargar los rankings.",
      true
    );
  }
}

// --------------------------------------------
// Eventos
// --------------------------------------------

selectorPeriodo.addEventListener("change", () => {
  const dias = Number(selectorPeriodo.value);

  if (![7, 30, 90].includes(dias)) {
    mostrarMensaje("Selecciona un periodo válido.", true);
    return;
  }

  cargarRankings(dias);
});

// --------------------------------------------
// Inicio
// --------------------------------------------

(async function iniciarAnalista() {
  const autorizado = await verificarAccesoAnalista();

  if (!autorizado) return;

  await Promise.all([
    cargarResumen(),
    cargarRankings(Number(selectorPeriodo.value))
  ]);
})();
