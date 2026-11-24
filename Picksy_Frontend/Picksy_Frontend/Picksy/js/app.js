// Picksy - interacciones iniciales del frontend.

const state = {
  query: "",
  category: "Todos",
  view: "buscar",
  history: []
};

const $ = (selector) => document.querySelector(selector);

function showToast(message) {
  const toast = $("#toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 2400);
}

function recordSearch(query, presupuesto) { // CAMBIO (backend): ahora también guarda el presupuesto
  if (!query.trim()) return;
  state.history.unshift({
    query: query.trim(),
    presupuesto: presupuesto || null,
    date: new Date().toLocaleString("es-CO", { dateStyle: "short", timeStyle: "short" })
  });
  state.history = state.history.slice(0, 15);
  renderHistory();
}

function setView(view) {
  state.view = view;
  $("#searchView")?.classList.toggle("hidden", view !== "buscar");
  $("#hero")?.classList.toggle("hidden", view !== "buscar");
  $("#historyView")?.classList.toggle("hidden", view !== "historial");
  $("#productDetail")?.classList.add("hidden");
  document.querySelectorAll(".nav-link").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  if (view === "historial") renderHistory();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderHistory() {
  const list = $("#historyList");
  if (!list) return;
  list.innerHTML = state.history.map((item) => `
    <div class="history-item">
      <div><strong>${escapeHtml(item.query)}</strong><br><span>${item.presupuesto ? "Presupuesto: " + formatoPesos.format(item.presupuesto) : "Búsqueda realizada"}</span></div>
      <span>${escapeHtml(item.date)}</span>
      <button class="button button-secondary" data-research="${escapeHtml(item.query)}" data-budget="${item.presupuesto || ""}">Buscar otra vez</button>
    </div>`).join("");
  $("#historyEmpty")?.classList.toggle("hidden", state.history.length > 0);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[char]));
}

// ===== CAMBIO (backend): búsqueda conectada con el backend (js/api.js) =====
// Requiere que js/api.js esté cargado en index.html ANTES de este archivo,
// y los elementos #budgetInput, #searchStatus y #searchNotices del index.html.

let ultimosResultados = null; // última respuesta de /buscar; permite reordenar sin volver a consultar
let numeroBusqueda = 0;       // sirve para ignorar respuestas viejas si el usuario busca otra vez
const PRODUCTOS_POR_PAGINA = 12;
let paginaActual = 1;

const formatoPesos = new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 });

// Solo se aceptan enlaces http/https: los datos vienen de páginas de terceros.
function urlSegura(valor) {
  try {
    const url = new URL(valor);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : "";
  } catch {
    return "";
  }
}

function mostrarEstado(mensaje, tipo = "") {
  const estado = $("#searchStatus");
  if (!estado) return;
  estado.textContent = mensaje;
  estado.className = "search-status" + (tipo ? " " + tipo : "") + (mensaje ? "" : " hidden");
}

function mostrarAvisos(avisos) {
  const caja = $("#searchNotices");
  if (!caja) return;
  const hay = Array.isArray(avisos) && avisos.length > 0;
  caja.textContent = hay ? "Aviso: " + avisos.join(" · ") : "";
  caja.classList.toggle("hidden", !hay);
}

// ============================================
// MEMBRESÍA Y LÍMITE DE BÚSQUEDAS
// ============================================

const LIMITE_BUSQUEDAS_NORMAL = 30;

// Actualiza los indicadores del encabezado.

function actualizarIndicadoresCuenta(usuario) {
  const badge = $("#planBadge");
  const contador = $("#searchCounter");
  const enlacePremium = $("#enlacePremium");

  if (!usuario) return;

  const rol = usuario.rol;
  const esPremium = usuario.premium === true || rol === "premium";
  const esUsuarioNormal = rol === "usuario" && !esPremium;

  // Por defecto, ocultamos todos los indicadores.
  badge?.classList.add("hidden");
  contador?.classList.add("hidden");
  enlacePremium?.classList.add("hidden");

  // Usuario normal: insignia, contador y acceso a Premium.
  if (esUsuarioNormal) {
    if (badge) {
      badge.textContent = "Plan normal";
      badge.classList.remove("hidden");
      badge.classList.add("normal");
      badge.classList.remove("premium");
    }

    if (contador) {
      const limite = Number(usuario.limite_diario ?? LIMITE_BUSQUEDAS_NORMAL);
      const usadas = Number(usuario.busquedas_hoy || 0);
      const restantes = Math.max(0, limite - usadas);

      contador.textContent = `${restantes} de ${limite} búsquedas restantes`;
      contador.classList.remove("hidden");
    }

    enlacePremium?.classList.remove("hidden");
  }

  // Premium: solamente insignia, sin contador.
  if (esPremium) {
    if (badge) {
      badge.textContent = "Premium";
      badge.classList.remove("hidden");
      badge.classList.add("premium");
      badge.classList.remove("normal");
    }
  }
}



// Consulta nuevamente /auth/me para actualizar el contador.
async function actualizarContadorBusquedas() {

  try {

    const usuario = await PicksyAPI.usuarioActual();

    if (usuario) {
      actualizarIndicadoresCuenta(usuario);
    }

  } catch (error) {

    console.error("No se pudo actualizar el contador:", error);

  }
}


// Muestra el aviso cuando el usuario alcanza su límite.
function mostrarAvisoPremium(mensaje) {

  const aviso = $("#premiumNotice");
  const texto = $("#premiumNoticeMessage");

  if (!aviso || !texto) return;

  texto.textContent = mensaje;

  aviso.classList.remove("hidden");
}


// Oculta el aviso al iniciar otra búsqueda.
function ocultarAvisoPremium() {

  $("#premiumNotice")?.classList.add("hidden");

}

function opciones(cantidad) {
  return cantidad === 1 ? "1 opción" : `${cantidad} opciones`;
}

function textoEnvio(opcion) {
  if (!opcion.envio_confirmado) return "Envío por calcular";
  return opcion.envio === 0 ? "Envío gratis" : `+ envío ${formatoPesos.format(opcion.envio)}`;
}

function textoFecha(iso) {
  const fecha = new Date(iso);
  if (Number.isNaN(fecha.getTime())) return "";
  return "Act. " + fecha.toLocaleString("es-CO", { dateStyle: "short", timeStyle: "short" });
}

function tarjetaProducto(opcion, esMejor) {
  const imagen = urlSegura(opcion.imagen);
  const enlace = urlSegura(opcion.url);
  const visual = imagen && !imagen.includes("no_image")
    ? `<img src="${escapeHtml(imagen)}" alt="${escapeHtml(opcion.nombre)}" loading="lazy" referrerpolicy="no-referrer">`
    : `<span class="product-emoji">🛍️</span>`;
  const boton = enlace
    ? `<a class="button button-primary" href="${escapeHtml(enlace)}" target="_blank" rel="noopener noreferrer">Ver en ${escapeHtml(opcion.tienda)} →</a>`
    : "";
  // CAMBIO (backend): botones para el carrito (RF-13) y para ver cómo ha cambiado el precio (RF-16).
  const clave = escapeHtml(opcion.tienda + "|" + opcion.url);
  const extras = `
    <button type="button" class="button button-secondary button-mini" data-accion="carrito" data-clave="${clave}">+ Carrito</button>
    <button type="button" class="button button-secondary button-mini" data-accion="precio" data-clave="${clave}">Precio</button>`;
  return `
    <article class="product-card">
      <div class="product-visual">
        ${esMejor ? '<span class="product-badge">Mejor precio</span>' : ""}
        ${visual}
      </div>
      <div class="product-info">
        <span class="product-category">${escapeHtml(opcion.tienda)}</span>
        <h3>${escapeHtml(opcion.nombre)}</h3>
        <div class="product-price">${formatoPesos.format(opcion.total)}</div>
        <div class="product-meta">
          <span>${escapeHtml(textoEnvio(opcion))}</span>
          <span>${escapeHtml(textoFecha(opcion.actualizado_en))}</span>
        </div>
        <div class="card-actions">${boton}${enlace ? extras : ""}</div>
      </div>
    </article>`;
}

function ordenar(lista) {
  const orden = $("#sortSelect")?.value || "recommended";
  const copia = [...lista];
  if (orden === "low") copia.sort((a, b) => a.total - b.total);
  if (orden === "high") copia.sort((a, b) => b.total - a.total);
  return copia; // "recommended" conserva el orden del backend (de menor a mayor total)
}

function renderPagination(totalPaginas) {
  const pagination = $("#pagination");
  const numbers = $("#paginationNumbers");

  if (!pagination || !numbers) return;

  pagination.classList.toggle("hidden", totalPaginas <= 1);

  if (totalPaginas <= 1) {
    numbers.innerHTML = "";
    return;
  }

  const paginas = new Set([
    1,
    totalPaginas
  ]);

  for (
    let i = Math.max(1, paginaActual - 2);
    i <= Math.min(totalPaginas, paginaActual + 2);
    i++
  ) {
    paginas.add(i);
  }

  const ordenadas = [...paginas].sort((a, b) => a - b);
  let contenido = "";
  let anterior = 0;

  ordenadas.forEach((pagina) => {
    if (anterior && pagina - anterior > 1) {
      contenido += `<span class="pagination-ellipsis">…</span>`;
    }

    contenido += `
      <button
        type="button"
        class="pagination-number ${pagina === paginaActual ? "active" : ""}"
        data-page="${pagina}"
        aria-label="Página ${pagina}"
        aria-current="${pagina === paginaActual ? "page" : "false"}">
        ${pagina}
      </button>
    `;

    anterior = pagina;
  });

  numbers.innerHTML = contenido;

  const previousButton = $("#previousPage");
  const nextButton = $("#nextPage");

  if (previousButton) {
    previousButton.disabled = paginaActual === 1;
  }

  if (nextButton) {
    nextButton.disabled = paginaActual === totalPaginas;
  }
}

function cambiarPagina(pagina) {
  if (!ultimosResultados) return;

  const totalProductos = ultimosResultados.viables.length;
  const totalPaginas = Math.ceil(totalProductos / PRODUCTOS_POR_PAGINA);

  if (pagina < 1 || pagina > totalPaginas) return;

  paginaActual = pagina;
  mostrarResultados();

  $("#searchView")?.scrollIntoView({
    behavior: "smooth",
    block: "start"
  });
}

function mostrarResultados() {
  const datos = ultimosResultados;
  const grid = $("#productGrid");
  const vacio = $("#emptyState");

  if (!datos || !grid) return;

  const viables = ordenar(datos.viables);
  const totalProductos = viables.length;
  const totalPaginas = Math.ceil(
    totalProductos / PRODUCTOS_POR_PAGINA
  );

  if (totalPaginas > 0 && paginaActual > totalPaginas) {
    paginaActual = totalPaginas;
  }

  const inicio = (paginaActual - 1) * PRODUCTOS_POR_PAGINA;
  const productosPagina = viables.slice(
    inicio,
    inicio + PRODUCTOS_POR_PAGINA
  );

  const claveMejor = datos.mejor_opcion
    ? datos.mejor_opcion.tienda + "|" + datos.mejor_opcion.url
    : null;

  grid.innerHTML = productosPagina.map((opcion) => {
    return tarjetaProducto(
      opcion,
      claveMejor === opcion.tienda + "|" + opcion.url
    );
  }).join("");

  $("#resultsTitle").textContent =
    `Resultados para «${datos.producto}»`;

  const presupuestoTexto = formatoPesos.format(datos.presupuesto);

  if (totalProductos > 0) {
    const sobran = datos.descartadas.length;

    $("#resultsSubtitle").textContent =
      `${opciones(totalProductos)} dentro de tu presupuesto de ${presupuestoTexto}.` +
      (sobran
        ? ` ${sobran === 1 ? "Otra supera" : `Otras ${sobran} superan`} tu presupuesto.`
        : "");
  } else {
    $("#resultsSubtitle").textContent =
      `Tu presupuesto: ${presupuestoTexto}.`;
  }

  vacio?.classList.toggle("hidden", totalProductos > 0);

  if (totalProductos === 0 && vacio) {
    const titulo = vacio.querySelector("h3");
    const texto = vacio.querySelector("p");

    if (datos.descartadas.length > 0) {
      if (titulo) {
        titulo.textContent = "Ninguna opción cabe en tu presupuesto";
      }

      if (texto) {
        texto.textContent =
          `Encontramos ${opciones(datos.descartadas.length)}, pero la más barata cuesta ${formatoPesos.format(datos.descartadas[0].total)}. Prueba con un presupuesto mayor.`;
      }
    } else {
      if (titulo) {
        titulo.textContent = "No encontramos productos";
      }

      if (texto) {
        texto.textContent =
          `No encontramos «${datos.producto}» en las tiendas consultadas. Prueba con otro nombre.`;
      }
    }
  }

  renderPagination(totalPaginas);
}

$("#paginationNumbers")?.addEventListener("click", (event) => {
  const boton = event.target.closest("[data-page]");

  if (!boton) return;

  cambiarPagina(Number(boton.dataset.page));
});

$("#previousPage")?.addEventListener("click", () => {
  cambiarPagina(paginaActual - 1);
});

$("#nextPage")?.addEventListener("click", () => {
  cambiarPagina(paginaActual + 1);
});

async function buscarEnBackend(producto, presupuesto) {

  if (typeof PicksyAPI === "undefined") {

    mostrarEstado("Falta cargar js/api.js en index.html.", "error");

    return;
  }

  const numero = ++numeroBusqueda;

  paginaActual = 1;

  const boton = $("#searchForm button[type='submit']");

  if (boton) boton.disabled = true;

  ocultarAvisoPremium();

  mostrarAvisos([]);

  $("#productGrid").innerHTML = "";

  $("#emptyState")?.classList.add("hidden");

  $("#pagination")?.classList.add("hidden");

  mostrarEstado(
    `Buscando «${producto}» en las tiendas… la primera búsqueda puede tardar unos segundos.`,
    "loading"
  );

  try {

    const datos = await PicksyAPI.buscarProductos({
      producto,
      presupuesto
    });

    if (numero !== numeroBusqueda) return;

    ultimosResultados = datos;

    mostrarEstado("");

    mostrarAvisos(datos.avisos);

    mostrarResultados();

    // Actualizamos el contador después de cada búsqueda.
    await actualizarContadorBusquedas();

    if (haySesion()) {
      cargarHistorial();
    }

  } catch (error) {

    if (numero !== numeroBusqueda) return;

    if (error.estado === 429) {

      // Actualizamos las búsquedas restantes.
      await actualizarContadorBusquedas();

      mostrarEstado("");

      // El mensaje viene directamente del backend.
      const mensaje =
        error.datos?.error?.mensaje ||
        error.datos?.detail ||
        error.message ||
        "Has alcanzado el límite de búsquedas de hoy.";

      mostrarAvisoPremium(mensaje);

    } else {

      mostrarEstado(
        error.message || "No se pudo completar la búsqueda.",
        "error"
      );

    }

  } finally {

    if (boton && numero === numeroBusqueda) {
      boton.disabled = false;
    }

  }
}

// CAMBIO (backend): si la imagen de una tienda no carga (bloqueo, enlace roto o imagen de relleno),
// se cambia por el ícono 🛍️ en vez de mostrar el texto del nombre del producto.
// El evento "error" de una imagen no sube por el DOM, por eso se escucha en la fase de captura.
$("#productGrid")?.addEventListener("error", (event) => {
  const imagen = event.target;
  if (!(imagen instanceof HTMLImageElement)) return;
  const marco = imagen.parentElement;
  imagen.remove();
  if (marco && !marco.querySelector(".product-emoji")) {
    marco.insertAdjacentHTML("beforeend", '<span class="product-emoji">🛍️</span>');
  }
}, true);

// CAMBIO (backend): clic en «+ Carrito» o «Precio» de una tarjeta (una sola escucha para toda la cuadrícula).
$("#productGrid")?.addEventListener("click", (event) => {
  const boton = event.target.closest("[data-accion]");
  if (!boton || !ultimosResultados) return;
  const todas = [...ultimosResultados.viables, ...ultimosResultados.descartadas];
  const opcion = todas.find((o) => o.tienda + "|" + o.url === boton.dataset.clave);
  if (!opcion || typeof PicksyUI === "undefined") return;
  if (boton.dataset.accion === "carrito") PicksyUI.elegirCarrito(opcion);
  else PicksyUI.mostrarVariacion(opcion.url, opcion.nombre);
});

function limpiarBusqueda() {
  numeroBusqueda++; // cancela cualquier búsqueda en curso
  ultimosResultados = null;
  paginaActual = 1;
  $("#pagination")?.classList.add("hidden");
  $("#paginationNumbers")?.replaceChildren();
  $("#searchInput").value = "";
  $("#productGrid").innerHTML = "";
  $("#emptyState")?.classList.add("hidden");
  mostrarEstado("");
  mostrarAvisos([]);
  $("#resultsTitle").textContent = "Productos destacados";
  $("#resultsSubtitle").textContent = "Una selección para ayudarte a elegir mejor.";
  const boton = $("#searchForm button[type='submit']");
  if (boton) boton.disabled = false;
}

$("#clearSearch")?.addEventListener("click", limpiarBusqueda);

$("#searchForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  state.query = $("#searchInput").value.trim();

  // CAMBIO (backend): ahora hacen falta un producto (mínimo 2 caracteres) y un presupuesto.
  if (state.query.length < 2) {
    showToast("Escribe qué producto buscas.");
    $("#searchInput").focus();
    return;
  }
  // CAMBIO (backend): la validación y el guardado del presupuesto están en validarPresupuesto()
  // (sección "PRESUPUESTO DEL USUARIO", más abajo). Devuelve el número, o null si no es válido.
  const presupuesto = validarPresupuesto();
  if (presupuesto === null) {
    budgetInput.focus();
    return;
  }

  // CAMBIO (backend): con sesión iniciada el historial lo guarda el backend (se recarga al terminar la búsqueda);
  // como visitante sigue guardándose solo en esta visita.
  if (!haySesion()) recordSearch(state.query, presupuesto);
  setView("buscar");
  $("#searchView")?.scrollIntoView({ behavior: "smooth", block: "start" });
  await buscarEnBackend(state.query, presupuesto);
});

document.querySelectorAll(".search-chip").forEach((button) => {
  button.addEventListener("click", () => {
    $("#searchInput").value = button.dataset.query;
    $("#searchForm").requestSubmit();
  });
});

// ============================================
// PRESUPUESTO DEL USUARIO - PICKSY
// ============================================

// Clave con la que guardamos el presupuesto en el navegador.
// Puedes buscar "picksyPresupuesto" para localizar este dato.
const CLAVE_PRESUPUESTO = "picksyPresupuesto";

// Recuperamos los elementos del buscador de index.html.
const searchForm = document.getElementById("searchForm");
const searchInput = document.getElementById("searchInput");
const budgetInput = document.getElementById("budgetInput");
const searchFeedback = document.getElementById("searchFeedback");

// Al cargar la página, recuperamos el presupuesto guardado.
const presupuestoGuardado = localStorage.getItem(CLAVE_PRESUPUESTO);

if (presupuestoGuardado !== null) {
  budgetInput.value = presupuestoGuardado;
}

// Cuando el usuario pulsa "Buscar", leemos ambos campos.
// CAMBIO (backend): antes esto era un segundo manejador del evento "submit". Ahora es una función
// que el manejador de arriba (el que llama al backend) usa para validar y guardar el presupuesto;
// así el formulario tiene un solo manejador y no se hacen dos cosas a la vez.
function validarPresupuesto() {

  const producto = searchInput.value.trim();

  const presupuestoTexto = budgetInput.value.trim();

  // Quitamos los separadores de miles y cualquier carácter no numérico.
  const presupuestoLimpio = presupuestoTexto.replace(/\D/g, "");

  // Validamos que el presupuesto sea un número positivo.
  if (
    presupuestoTexto !== "" &&
    (
      !presupuestoLimpio ||
      !Number.isFinite(Number(presupuestoLimpio)) ||
      Number(presupuestoLimpio) <= 0
    )
  ) {

    searchFeedback.textContent =
      "Ingresa un presupuesto mayor que cero.";

    return null;
  }

  if (presupuestoTexto === "") {

    localStorage.removeItem(CLAVE_PRESUPUESTO);

    searchFeedback.textContent =
      "Escribe tu presupuesto en pesos, por ejemplo 300000.";

    return null;
  }

  // El valor se convierte correctamente a número.
  const presupuesto = Number(presupuestoLimpio);

  // Guardamos el presupuesto numérico para futuras búsquedas.
  localStorage.setItem(
    CLAVE_PRESUPUESTO,
    String(presupuesto)
  );

  console.log("Producto buscado:", producto);

  console.log("Presupuesto máximo:", presupuesto);

  searchFeedback.textContent =
    `Presupuesto establecido: $${presupuesto.toLocaleString("es-CO")}.`;

  return presupuesto;
}

document.querySelectorAll(".nav-link").forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.view));
});

document.querySelectorAll(".category-pill").forEach((button) => {
  button.addEventListener("click", () => {
    state.category = button.dataset.category;
    document.querySelectorAll(".category-pill").forEach((pill) => {
      pill.classList.toggle("active", pill === button);
    });
    // CAMBIO (backend): el backend todavía no filtra por categoría.
    if (state.category !== "Todos") {
      showToast("Por ahora las categorías no filtran los resultados.");
    }
  });
});

$("#sortSelect")?.addEventListener("change", () => {
  // CAMBIO (backend): con resultados reales se reordenan sin volver a consultar al backend.
  if (!ultimosResultados) {
    showToast("El ordenamiento estará disponible cuando haya productos.");
    return;
  }
  paginaActual = 1;
  mostrarResultados();
});

$("#clearHistory")?.addEventListener("click", async () => {
  // CAMBIO (backend): con sesión también se borra en el servidor.
  if (haySesion()) {
    try {
      await PicksyAPI.borrarHistorial();
    } catch (error) {
      showToast(error.message || "No se pudo borrar el historial.");
      return;
    }
  }
  state.history = [];
  renderHistory();
});

$("#backToSearch")?.addEventListener("click", () => setView("buscar"));

$("#bannerSearch")?.addEventListener("click", () => {
  setView("buscar");
  $("#searchInput")?.focus();
});

$("#historyList")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-research]");
  if (!button) return;
  $("#searchInput").value = button.dataset.research;
  // CAMBIO (backend): también se recupera el presupuesto de esa búsqueda.
  if (button.dataset.budget && $("#budgetInput")) $("#budgetInput").value = Number(button.dataset.budget);
  $("#searchForm").requestSubmit();
});

renderHistory();

// CAMBIO (backend): historial guardado en el backend (solo con sesión iniciada).
function haySesion() {
  return typeof PicksyAPI !== "undefined" && PicksyAPI.hayToken();
}

async function cargarHistorial() {
  if (!haySesion()) return;
  try {
    const filas = await PicksyAPI.listarHistorial(1, 15);   // CAMBIO (paginación): las 15 más recientes; filas.total trae el total guardado
    state.history = filas.map((fila) => ({
      query: fila.termino,
      presupuesto: fila.presupuesto,
      date: new Date(fila.creado_en).toLocaleString("es-CO", { dateStyle: "short", timeStyle: "short" }),
    }));
    renderHistory();
  } catch {
    // Si falla (sesión vencida o sin conexión), se deja el historial de esta visita.
  }
}

function abrirModalLogout() {
  const modal = $("#logoutModal");

  if (!modal) {
    showToast("No se encontró la ventana de cierre de sesión.");
    return;
  }

  modal.classList.remove("hidden");
  $("#cancelLogout")?.focus();
}

function cerrarModalLogout() {
  $("#logoutModal")?.classList.add("hidden");
  $(".avatar")?.focus();
}

$("#closeLogoutModal")?.addEventListener("click", cerrarModalLogout);

$("#cancelLogout")?.addEventListener("click", cerrarModalLogout);

$("#logoutModal")?.addEventListener("click", (event) => {
  if (event.target.id === "logoutModal") {
    cerrarModalLogout();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("#logoutModal")?.classList.contains("hidden")) {
    cerrarModalLogout();
  }
});

$("#confirmLogout")?.addEventListener("click", async () => {
  const boton = $("#confirmLogout");

  if (boton) {
    boton.disabled = true;
    boton.textContent = "Cerrando sesión...";
  }

  try {
    await PicksyAPI.cerrarSesion();
    window.location.replace("login.html");
  } catch (error) {
    showToast(error.message || "No se pudo cerrar la sesión.");

    if (boton) {
      boton.disabled = false;
      boton.textContent = "Cerrar sesión";
    }
  }
});

async function cargarSesion() {

  const saludo = document.querySelector(".user-greeting");
  const avatar = document.querySelector(".avatar");

  if (!saludo || !avatar || typeof PicksyAPI === "undefined") {
    return;
  }

  try {

    const usuario = await PicksyAPI.usuarioActual();

    if (!usuario) {

      window.location.replace("login.html");

      return;
    }

    // Nombre mostrado en el encabezado.
    const nombre = usuario.correo.split("@")[0];

    saludo.textContent = `¡Hola, ${nombre}!`;

    // Indicadores de membresía y búsquedas.
    actualizarIndicadoresCuenta(usuario);

    // Mostrar las opciones según el rol recibido desde /auth/me.
    const rol = usuario.rol;

    $("#enlaceAdmin")?.classList.toggle(
      "hidden",
      rol !== "admin"
    );

    $("#enlaceSoporte")?.classList.toggle(
      "hidden",
      !["soporte", "admin"].includes(rol)
    );

    $("#enlaceAnalista")?.classList.toggle(
      "hidden",
      !["analista", "admin"].includes(rol)
    );

    $("#enlaceModeracion")?.classList.toggle(
      "hidden",
      !["moderador_tiendas", "admin"].includes(rol)
    );


    // Historial del usuario.
    cargarHistorial();

    avatar.textContent = nombre.charAt(0).toUpperCase();

    avatar.title = "Cerrar sesión";

    avatar.setAttribute("aria-label", "Cerrar sesión");

    avatar.addEventListener("click", (event) => {

      event.preventDefault();

      abrirModalLogout();

    });

  } catch (error) {

    console.error("No se pudo cargar la sesión:", error);

  }
}

cargarSesion();

// CAMBIO (backend): si se entró con un código de recuperación, verificar-2fa.js deja un aviso para mostrarlo aquí.
try {
  const avisoPendiente = sessionStorage.getItem("picksyAviso");
  if (avisoPendiente) {
    sessionStorage.removeItem("picksyAviso");
    window.setTimeout(() => showToast(avisoPendiente), 600);
  }
} catch { /* sin almacenamiento */ }

if (budgetInput) {
  budgetInput.addEventListener("input", () => {
    // Obtener únicamente los números escritos
    const valor = budgetInput.value.replace(/\D/g, "");

    // Si el campo está vacío, no hacer nada
    if (!valor) {
      budgetInput.value = "";
      return;
    }

    // Formatear con separadores de miles colombianos
    budgetInput.value = Number(valor).toLocaleString("es-CO");
  });
}
